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

def main():
 DB.parent.mkdir(exist_ok=True); OUT.parent.mkdir(exist_ok=True)
 db=json.loads(DB.read_text()) if DB.exists() else {'items':{},'status':{}}
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
   # College page: individual decisions often have no unique links; hash each heading and following text.
   if source=='Collegebesluiten':
    headings=main.find_all(['h2','h3','h4'])
    for h in headings:
     title=clean(h.get_text(' ',strip=True))
     if len(title)<8:continue
     parts=[]
     for sib in h.next_siblings:
      if getattr(sib,'name',None) in ('h2','h3','h4'):break
      if hasattr(sib,'get_text'):parts.append(sib.get_text(' ',strip=True))
     body=clean(' '.join(parts))[:8000]
     if not body:continue
     key=hashlib.sha256((source+'|'+title).encode()).hexdigest()
     fingerprint=hashlib.sha256(body.encode()).hexdigest()
     old=db['items'].get(key)
     if old is None: db['items'][key]={'title':title,'url':url,'source':source,'first_seen':utc(),'updated':utc(),'hash':fingerprint,'revisions':1,'excerpt':body[:400]}
     elif old['hash']!=fingerprint:old.update(hash=fingerprint,updated=utc(),revisions=old['revisions']+1,excerpt=body[:400])
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
 eligible=[(k,v) for k,v in db['items'].items() if v.get('url','').startswith((
  'https://www.medemblik.nl/', 'https://medemblik.bestuurlijkeinformatie.nl/'))]
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
 html='''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Medemblik Monitor</title><style>body{font:16px system-ui;margin:0;background:#f4f7fb;color:#172437}header{background:#123657;color:white;padding:24px}main{max-width:1050px;margin:24px auto;padding:0 16px}.panel{background:white;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 6px #0001}input,select{padding:12px;border:1px solid #aab8c6;border-radius:8px;max-width:100%;margin:5px}a{color:#075a9c}small{color:#536577}.error{color:#a52d2d}.ok{color:#177147}li{margin:14px 0}button{padding:10px;border-radius:8px;cursor:pointer}</style></head><body><header><h1>Medemblik Monitor</h1><p>Openbare publicaties en wijzigingen · experimentele monitor</p></header><main><section class="panel"><strong id="count"></strong><p>Dit systeem detecteert wat het kan ophalen. Geen garantie op volledigheid of directe meldingen. Eerste waarneming is niet de officiële publicatiedatum.</p><input id="q" placeholder="Zoeken in titels"><select id="source"><option value="">Alle bronnen</option></select><select id="kind"><option value="">Alle</option><option value="changed">Gewijzigd</option></select></section><section class="panel"><h2>Bronstatus</h2><div id="status"></div></section><section class="panel"><h2>Publicaties</h2><div id="results"></div></section></main><script>const DATA=__DATA__;const $=x=>document.getElementById(x);const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const sources=[...new Set(DATA.items.map(x=>x.source))];sources.forEach(s=>{let o=document.createElement('option');o.value=s;o.textContent=s;$('source').appendChild(o)});$('status').innerHTML=Object.entries(DATA.status).map(([s,v])=>`<div class="${v.ok?'ok':'error'}">${esc(s)}: ${v.ok?'OK':'FOUT'} · ${esc(v.checked)} ${v.error?esc(v.error):''}</div>`).join('');function render(){let q=$('q').value.toLowerCase(),src=$('source').value,k=$('kind').value;let a=DATA.items.filter(x=>(!src||x.source===src)&&(!k||x.revisions>1)&&(x.title+' '+x.excerpt).toLowerCase().includes(q));$('count').textContent=a.length+' resultaten';$('results').innerHTML='<ul>'+a.slice(0,500).map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><br><small>${esc(x.source)} · publicatiedatum: ${esc(x.publication_date || 'onbekend')} · ontdekt door monitor: ${esc(x.first_seen ? new Date(x.first_seen).toLocaleDateString('nl-NL') : 'onbekend')} · laatste geregistreerde wijziging: ${esc(x.updated ? new Date(x.updated).toLocaleDateString('nl-NL') : 'onbekend')} · versies: ${x.revisions}</small></li>`).join('')+'</ul>'}['q','source','kind'].forEach(id=>$(id).addEventListener('input',render));render();</script></body></html>'''
 OUT.write_text(html.replace('__DATA__',payload))
 print('Items:',len(items),'Sources:',db['status'])
if __name__=='__main__':main()
