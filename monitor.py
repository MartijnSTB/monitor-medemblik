import json, hashlib, re, os, datetime, urllib.parse
from pathlib import Path
import requests
import time
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

ROOT=Path(__file__).parent
DB=ROOT/'data'/'items.json'
OUT=ROOT/'docs'/'index.html'
SOURCES={
 'Nieuws':'https://www.medemblik.nl/nieuws',
 'Collegebesluiten':'https://www.medemblik.nl/raad-bestuur-en-organisatie/college-van-bw/collegebesluiten',
 'Openbare informatie':'https://www.medemblik.nl/raad-bestuur-en-organisatie/klacht-bezwaar-en-informatieverzoek/openbare-informatie',
 'Raadsportaal':'https://medemblik.bestuurlijkeinformatie.nl/',
 'Bekendmakingen':'https://www.medemblik.nl/raad-bestuur-en-organisatie/bekendmakingen/koop/pagina/2',
}
HEADERS={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def collect_official(db):
 """Collect recent Medemblik publications through the KOOP SRU 2.0 endpoint.

 Fail visibly on unexpected XML or diagnostics. Only records with an exact
 Medemblik creator match are accepted. Results are a rolling window, not a
 complete historical archive.
 """
 source='Officiele bekendmakingen (KOOP)'
 now=utc()
 try:
  params={
   'operation':'searchRetrieve','version':'2.0',
   'query':'c.product-area=="officielepublicaties" AND dt.creator=="Medemblik"',
   'maximumRecords':'100','startRecord':'1',
  }
  response=requests.get('https://repository.overheid.nl/sru',params=params,headers=HEADERS,timeout=35)
  response.raise_for_status()
  root=ET.fromstring(response.content)
  if root.findall('.//{*}diagnostic'):
   raise ValueError('SRU diagnostic: '+clean(' '.join(root.itertext()))[:250])
  records=root.findall('.//{*}recordData')
  if not records:
   raise ValueError('Geen recordData gevonden; controleer SRU query en XML structuur')
  added=0
  for record in records:
   def values(name):
    return [clean(e.text) for e in record.iter() if e.tag.rsplit('}',1)[-1]==name and e.text and clean(e.text)]
   creators=values('creator')
   if not any(c.casefold()=='medemblik' for c in creators):
    continue
   title=(values('title') or ['Publicatie zonder titel'])[0]
   ids=values('identifier')
   urls=[x for x in ids if x.startswith('https://') or x.startswith('http://')]
   ident=next((x for x in ids if re.search(r'(?:gmb|stcrt|bgr|prb|wsb)-\d{4}-\d+',x)),None)
   if not urls and ident:
    m=re.search(r'(?:gmb|stcrt|bgr|prb|wsb)-\d{4}-\d+',ident)
    urls=['https://zoek.officielebekendmakingen.nl/'+m.group()+'.html'] if m else []
   if not urls:
    continue
   url=urls[0]
   key=hashlib.sha256((source+'|'+url).encode()).hexdigest()
   dates=values('date')
   if key not in db['items']:
    db['items'][key]={'title':title,'url':url,'source':source,'first_seen':now,
      'updated':now,'hash':hashlib.sha256((title+'|'+str(dates)).encode()).hexdigest(),
      'revisions':1,'publication_date':(dates[0] if dates else None),
       'excerpt':'Officiele bekendmaking; publicatiedatum: '+(dates[0] if dates else 'onbekend')}
    added+=1
  db['status'][source]={'ok':True,'checked':now,'count':len(records),'new':added,
    'note':'Maximaal 100 recente resultaten; niet gegarandeerd volledig. Alleen exacte Medemblik creator.'}
 except Exception as exc:
  db['status'][source]={'ok':False,'checked':now,'error':str(exc)[:250]}

MAANDEN={'januari':1,'februari':2,'maart':3,'april':4,'mei':5,'juni':6,'juli':7,
 'augustus':8,'september':9,'oktober':10,'november':11,'december':12}
def meeting_date(text):
 """'Collegebesluiten 29 september 2026' -> '2026-09-29', anders None."""
 m=re.search(r'(\d{1,2})\s+([a-z]+)\s+(\d{4})',text.casefold())
 if not m or m.group(2) not in MAANDEN: return None
 try: return datetime.date(int(m.group(3)),MAANDEN[m.group(2)],int(m.group(1))).isoformat()
 except ValueError: return None

def parse_college(main):
 """Split the college page into decisions: [{'date','title','body'}].

 Walks all text in document order, so it also works when headings sit inside
 wrapper divs. Only h2 (date) and h3 (decision) start a new block."""
 from bs4 import NavigableString, Comment
 decisions=[]; date=None; current=None
 for node in main.descendants:
  name=getattr(node,'name',None)
  if name=='h2':
   date=meeting_date(clean(node.get_text(' ',strip=True)))
   current=None  # h2 zonder datum (bijv. 'Oudere collegebesluiten') sluit het blok af
  elif name=='h3':
   current=None
   if date:
    current={'date':date,'title':clean(node.get_text(' ',strip=True)),'parts':[]}
    decisions.append(current)
  elif isinstance(node,NavigableString) and not isinstance(node,Comment) and current is not None:
   if node.find_parent(['h2','h3']): continue
   text=clean(str(node))
   if text: current['parts'].append(text)
 for d in decisions: d['body']=clean(' '.join(d.pop('parts')))[:8000]
 return [d for d in decisions if d['title'] and d['body']]

def collect_college(db,main,url):
 source='Collegebesluiten'
 seen={}
 for d in parse_college(main):
  # Unieke sleutel: vergaderdatum + besluittitel (+ volgnummer bij dubbele titel op dezelfde datum)
  base=d['date']+'|'+d['title'].casefold().rstrip(' .:')
  seen[base]=seen.get(base,0)+1
  ident=base+('#'+str(seen[base]) if seen[base]>1 else '')
  key=hashlib.sha256((source+'|'+ident).encode()).hexdigest()
  fingerprint=hashlib.sha256(d['body'].encode()).hexdigest()
  status=re.findall(r'\b(Conform besloten|Aangepast besloten|Niet besloten|Aangehouden|Conform)\b',d['body'])
  old=db['items'].get(key)
  now=utc()
  if old is None:
   db['items'][key]={'title':d['title'],'url':url,'source':source,'kind':'collegebesluit',
     'meeting_date':d['date'],'publication_date':None,'first_seen':now,'updated':now,
     'hash':fingerprint,'revisions':1,'besluit_status':status[-1] if status else None,
     'excerpt':d['body'][:400]}
  elif old['hash']!=fingerprint:
   # Alleen een revisie bij een aantoonbaar andere tekst van precies dit besluit.
   old.update(hash=fingerprint,updated=now,revisions=old['revisions']+1,
     change_type='Besluittekst gewijzigd',excerpt=d['body'][:400],
     besluit_status=status[-1] if status else old.get('besluit_status'))

def archive_legacy_college(db):
 """Versie 3 sloeg kopjes als 'Samenvatting' en 'Besluit:' op als besluiten.
 Die items worden niet gewist maar naar db['archief'] verplaatst, met reden."""
 archive=db.setdefault('archief',{})
 for key,item in list(db['items'].items()):
  if item.get('source')=='Collegebesluiten' and item.get('kind')!='collegebesluit' \
     and item.get('url','').rstrip('/')==SOURCES['Collegebesluiten'].rstrip('/'):
   item['archived']=utc()
   item['archived_reason']='Foutieve identificatie in versie 3 (kopje als besluit); revisietelling onbetrouwbaar'
   archive[key]=db['items'].pop(key)

def main():
 DB.parent.mkdir(exist_ok=True); OUT.parent.mkdir(exist_ok=True)
 db=json.loads(DB.read_text()) if DB.exists() else {'items':{},'status':{}}
 archive_legacy_college(db)
 collect_official(db)
 for source,url in SOURCES.items():
  try:
   r=requests.get(url,headers=HEADERS,timeout=25);r.raise_for_status()
   soup=BeautifulSoup(r.text,'html.parser')
   for t in soup(['script','style','nav','footer','header','form']):t.decompose()
   main=soup.select_one('main') or soup.select_one('article') or soup
   # Extract linked articles and files. Avoid generic navigation links.
   candidates=[]
   for a in main.select('a[href]'):
    title=clean(a.get_text(' ',strip=True)); href=urllib.parse.urljoin(url,a['href'])
    if len(title)<12 or len(title)>240 or not href.startswith('https://'):continue
    if not any(href.startswith(x) for x in ['https://www.medemblik.nl/','https://medemblik.bestuurlijkeinformatie.nl/']):continue
    if href.rstrip('/')==url.rstrip('/'):continue
    candidates.append((title,href))
   # College page: decisions have no own links. Structure: h2 = meeting date, h3 = decision,
   # h4 = 'Samenvatting'/'Besluit' (part of the decision text, never an item of its own).
   if source=='Collegebesluiten':
    collect_college(db,main,url)
   for title,href in candidates:
    key=hashlib.sha256((source+'|'+href).encode()).hexdigest()
    if key not in db['items']:
     db['items'][key]={'title':title,'url':href,'source':source,'first_seen':utc(),'updated':utc(),'hash':hashlib.sha256(title.encode()).hexdigest(),'revisions':1,'excerpt':''}
   db['status'][source]={'ok':True,'checked':utc(),'count':len(candidates)}
  except Exception as e:
   db['status'][source]={'ok':False,'checked':utc(),'error':str(e)[:180]}
 # Check a limited rotating batch of already discovered documents for content changes.
 # This is best-effort and deliberately rate-limited; it is not a full document archive.
 checked_docs=0
 failures=0
 # Overzichtspagina's (zoals de collegebesluitenpagina) niet als 'document' controleren:
 # die veranderen bij elk nieuw besluit, waardoor alle items op die URL onterecht een revisie kregen.
 overview=set(u.rstrip('/') for u in SOURCES.values())
 eligible=[(k,v) for k,v in db['items'].items() if v.get('url','').startswith((
  'https://www.medemblik.nl/', 'https://medemblik.bestuurlijkeinformatie.nl/'))
  and v.get('url','').rstrip('/') not in overview and v.get('kind')!='collegebesluit']
 eligible.sort(key=lambda pair: pair[1].get('content_checked',''))
 for key,item in eligible[:15]:
  try:
   response=requests.get(item['url'],headers=HEADERS,timeout=18)
   response.raise_for_status()
   if len(response.content)>8_000_000: raise ValueError('Document te groot')
   content_type=response.headers.get('Content-Type','').lower()
   if 'pdf' in content_type or response.content[:4]==b'%PDF':
    normalized=response.content
   elif 'html' in content_type or b'<html' in response.content[:500].lower():
    page=BeautifulSoup(response.text,'html.parser')
    for tag in page(['script','style','nav','footer','header','form']):tag.decompose()
    area=page.select_one('main') or page.select_one('article') or page
    normalized=clean(area.get_text(' ',strip=True)).encode('utf-8')
   else:
    normalized=response.content
   digest=hashlib.sha256(normalized).hexdigest()
   previous=item.get('content_hash')
   if previous and previous!=digest:
    item['updated']=utc()
    item['revisions']=item.get('revisions',1)+1
    item['change_type']='Inhoud gewijzigd'
   item['content_hash']=digest
   item['content_checked']=utc()
   item.pop('content_error',None)
   checked_docs+=1
  except Exception as exc:
   failures+=1
   item['content_checked']=utc()
   item['content_error']=str(exc)[:120]
 db['status']['Documentcontrole']={'ok':failures==0,'checked':utc(),
   'count':checked_docs,'errors':failures,
   'note':'Maximaal 15 documenten per uitvoering; inhoudswijzigingen worden vanaf de tweede succesvolle controle herkend.'}
  # Recover original publication dates for KOOP items already stored by version 3.
 for item in db['items'].values():
  if item.get('source')=='Officiele bekendmakingen (KOOP)' and not item.get('publication_date'):
   match=re.search(r'publicatiedatum:\s*(\d{4}-\d{2}-\d{2})',item.get('excerpt',''))
   if match:
    item['publication_date']=match.group(1)
 # Cap dataset to avoid endless Git history growth.
 items=sorted(db['items'].items(),key=lambda kv:kv[1]['updated'],reverse=True)[:3000]
 db['items']=dict(items)
 DB.write_text(json.dumps(db,ensure_ascii=False,indent=2)+'\n')
 payload=json.dumps({'items':[v for _,v in items],'status':db['status']},ensure_ascii=False).replace('</','<\\/')
 html='''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Medemblik Monitor</title><style>body{font:16px system-ui;margin:0;background:#f4f7fb;color:#172437}header{background:#123657;color:white;padding:24px}main{max-width:1050px;margin:24px auto;padding:0 16px}.panel{background:white;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 6px #0001}input,select{padding:12px;border:1px solid #aab8c6;border-radius:8px;max-width:100%;margin:5px}a{color:#075a9c}small{color:#536577}.error{color:#a52d2d}.ok{color:#177147}li{margin:14px 0}button{padding:10px;border-radius:8px;cursor:pointer}</style></head><body><header><h1>Medemblik Monitor</h1><p>Openbare publicaties en wijzigingen · experimentele monitor</p></header><main><section class="panel"><strong id="count"></strong><p>Dit systeem detecteert wat het kan ophalen. Geen garantie op volledigheid of directe meldingen. Eerste waarneming is niet de officiële publicatiedatum.</p><input id="q" placeholder="Zoeken in titels"><select id="source"><option value="">Alle bronnen</option></select><select id="kind"><option value="">Alle</option><option value="changed">Gewijzigd</option></select></section><section class="panel"><h2>Bronstatus</h2><div id="status"></div></section><section class="panel"><h2>Publicaties</h2><div id="results"></div></section></main><script>const DATA=__DATA__;const $=x=>document.getElementById(x);const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const sources=[...new Set(DATA.items.map(x=>x.source))];sources.forEach(s=>{let o=document.createElement('option');o.value=s;o.textContent=s;$('source').appendChild(o)});$('status').innerHTML=Object.entries(DATA.status).map(([s,v])=>`<div class="${v.ok?'ok':'error'}">${esc(s)}: ${v.ok?'OK':'FOUT'} · ${esc(v.checked)} ${v.error?esc(v.error):''}</div>`).join('');function render(){let q=$('q').value.toLowerCase(),src=$('source').value,k=$('kind').value;let a=DATA.items.filter(x=>(!src||x.source===src)&&(!k||x.revisions>1)&&(x.title+' '+x.excerpt).toLowerCase().includes(q));$('count').textContent=a.length+' resultaten';$('results').innerHTML='<ul>'+a.slice(0,500).map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><br><small>${esc(x.source)} · ${x.meeting_date ? 'collegevergadering: '+esc(x.meeting_date)+(x.besluit_status ? ' ('+esc(x.besluit_status)+')' : '') : 'publicatiedatum: '+esc(x.publication_date || 'onbekend')} · ontdekt door monitor: ${esc(x.first_seen ? new Date(x.first_seen).toLocaleDateString('nl-NL') : 'onbekend')} · laatste geregistreerde wijziging: ${esc(x.updated ? new Date(x.updated).toLocaleDateString('nl-NL') : 'onbekend')} · versies: ${x.revisions}</small></li>`).join('')+'</ul>'}['q','source','kind'].forEach(id=>$(id).addEventListener('input',render));render();</script></body></html>'''
 OUT.write_text(html.replace('__DATA__',payload))
 print('Items:',len(items),'Sources:',db['status'])
if __name__=='__main__':main()
