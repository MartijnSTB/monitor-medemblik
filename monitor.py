import json, hashlib, re, os, datetime, urllib.parse
from pathlib import Path
import requests
import time
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
def main():
 DB.parent.mkdir(exist_ok=True); OUT.parent.mkdir(exist_ok=True)
 db=json.loads(DB.read_text()) if DB.exists() else {'items':{},'status':{}}
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
 # Cap dataset to avoid endless Git history growth.
 items=sorted(db['items'].items(),key=lambda kv:kv[1]['updated'],reverse=True)[:3000]
 db['items']=dict(items)
 DB.write_text(json.dumps(db,ensure_ascii=False,indent=2)+'\n')
 payload=json.dumps({'items':[v for _,v in items],'status':db['status']},ensure_ascii=False).replace('</','<\\/')
 html='''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Medemblik Monitor</title><style>body{font:16px system-ui;margin:0;background:#f4f7fb;color:#172437}header{background:#123657;color:white;padding:24px}main{max-width:1050px;margin:24px auto;padding:0 16px}.panel{background:white;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 6px #0001}input,select{padding:12px;border:1px solid #aab8c6;border-radius:8px;max-width:100%;margin:5px}a{color:#075a9c}small{color:#536577}.error{color:#a52d2d}.ok{color:#177147}li{margin:14px 0}button{padding:10px;border-radius:8px;cursor:pointer}</style></head><body><header><h1>Medemblik Monitor</h1><p>Openbare publicaties en wijzigingen · experimentele monitor</p></header><main><section class="panel"><strong id="count"></strong><p>Dit systeem detecteert wat het kan ophalen. Geen garantie op volledigheid of directe meldingen. Eerste waarneming is niet de officiële publicatiedatum.</p><input id="q" placeholder="Zoeken in titels"><select id="source"><option value="">Alle bronnen</option></select><select id="kind"><option value="">Alle</option><option value="changed">Gewijzigd</option></select></section><section class="panel"><h2>Bronstatus</h2><div id="status"></div></section><section class="panel"><h2>Publicaties</h2><div id="results"></div></section></main><script>const DATA=__DATA__;const $=x=>document.getElementById(x);const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const sources=[...new Set(DATA.items.map(x=>x.source))];sources.forEach(s=>{let o=document.createElement('option');o.value=s;o.textContent=s;$('source').appendChild(o)});$('status').innerHTML=Object.entries(DATA.status).map(([s,v])=>`<div class="${v.ok?'ok':'error'}">${esc(s)}: ${v.ok?'OK':'FOUT'} · ${esc(v.checked)} ${v.error?esc(v.error):''}</div>`).join('');function render(){let q=$('q').value.toLowerCase(),src=$('source').value,k=$('kind').value;let a=DATA.items.filter(x=>(!src||x.source===src)&&(!k||x.revisions>1)&&(x.title+' '+x.excerpt).toLowerCase().includes(q));$('count').textContent=a.length+' resultaten';$('results').innerHTML='<ul>'+a.slice(0,500).map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a><br><small>${esc(x.source)} · eerst gezien: ${esc(x.first_seen)} · laatst gewijzigd: ${esc(x.updated)} · versies: ${x.revisions}</small></li>`).join('')+'</ul>'}['q','source','kind'].forEach(id=>$(id).addEventListener('input',render));render();</script></body></html>'''
 OUT.write_text(html.replace('__DATA__',payload))
 print('Items:',len(items),'Sources:',db['status'])
if __name__=='__main__':main()
