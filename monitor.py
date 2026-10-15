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
}
# Wat elke bron wel en niet dekt; staat bij de bronstatus op het dashboard.
SOURCE_NOTES={
 'Nieuws':'Alleen de eerste nieuwspagina (de 12 nieuwste berichten).',
 'Collegebesluiten':'Alleen de besluiten op de huidige pagina; het archief met oudere besluiten niet.',
 'Openbare informatie':'Alleen de links op deze pagina.',
 'Raadsportaal':'Startpagina: de 10 nieuwste overzichtsitems (raadsvragen, informatienota\u2019s, moties e.d.) en de vergaderingen. Oudere overzichtsitems niet.',
}
# KOOP: vanaf deze datum halen we alle bekendmakingen op (maand voor maand, zie koop_backfill).
KOOP_START='2026-01-01'
# Elke run: alles wat in de laatste zoveel dagen is gepubliceerd opnieuw ophalen.
KOOP_RECENT_DAYS=30
HEADERS={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
# Alleen de dag: zo verandert 'last_seen' maar één keer per dag en blijft de Git-historie klein.
def today(): return datetime.datetime.now(datetime.timezone.utc).date().isoformat()
def clean(s): return re.sub(r'\s+',' ',s or '').strip()

KOOP_SOURCE='Officiele bekendmakingen (KOOP)'
KOOP_BASE='c.product-area=="officielepublicaties" AND dt.creator=="Medemblik"'

def koop_fetch(date_filter):
 """Haal ALLE records op voor een datumfilter, met paginering (max 1000 per verzoek).

 Geeft (records, totaal_volgens_koop). Gecontroleerd 15 okt 2026: het filter
 dt.available>=JJJJ-MM-DD werkt; zonder filter levert KOOP de records in willekeurige
 volgorde (de oude code kreeg daardoor 100 vooral oude stukken)."""
 records=[]; start=1; total=None
 while True:
  params={'operation':'searchRetrieve','version':'2.0','query':KOOP_BASE+' AND '+date_filter,
   'maximumRecords':'1000','startRecord':str(start)}
  r=requests.get('https://repository.overheid.nl/sru',params=params,headers=HEADERS,timeout=90)
  r.raise_for_status()
  root=ET.fromstring(r.content)
  if root.findall('.//{*}diagnostic'):
   raise ValueError('SRU diagnostic: '+clean(' '.join(root.itertext()))[:250])
  if total is None:
   n=root.find('.//{*}numberOfRecords')
   total=int(n.text) if n is not None and n.text else 0
  batch=root.findall('.//{*}recordData')
  records+=batch
  nxt=root.find('.//{*}nextRecordPosition')
  if not batch or nxt is None or not (nxt.text or '').strip().isdigit(): break
  start=int(nxt.text)
  if start>20000: raise ValueError('Paginering loopt uit de hand; gestopt bij 20000')
 return records,total

def koop_store(db,records):
 """Sla KOOP-records op. Geeft het aantal nieuwe items."""
 now=utc(); added=0
 for record in records:
  def values(name):
   return [clean(e.text) for e in record.iter() if e.tag.rsplit('}',1)[-1]==name and e.text and clean(e.text)]
  first=lambda name:(values(name) or [None])[0]
  if not any(c.casefold()=='medemblik' for c in values('creator')):
   continue
  title=first('title') or 'Publicatie zonder titel'
  ids=values('identifier')
  m=next((re.search(r'(?:gmb|stcrt|bgr|prb|wsb)-\d{4}-\d+',x) for x in ids if re.search(r'(?:gmb|stcrt|bgr|prb|wsb)-\d{4}-\d+',x)),None)
  # Zelfde URL-opbouw als versie 3, zodat bestaande items dezelfde sleutel houden.
  url=('https://zoek.officielebekendmakingen.nl/'+m.group()+'.html') if m else first('preferredUrl')
  if not url: continue
  key=hashlib.sha256((KOOP_SOURCE+'|'+url).encode()).hexdigest()
  # Volgens de KOOP SRU-handleiding: dcterms:available = publicatie, dcterms:issued =
  # formele uitgifte, dcterms:date = aanmaak document.
  koop={'available':first('available'),'issued':first('issued'),'date':first('date')}
  koop={k:(v[:10] if v else None) for k,v in koop.items()}
  if koop['available']: doc_date,label=koop['available'],'publicatiedatum (KOOP)'
  elif koop['issued']: doc_date,label=koop['issued'],'uitgiftedatum (KOOP)'
  elif koop['date']: doc_date,label=koop['date'],'documentdatum (KOOP)'
  else: doc_date,label=None,None
  item=db['items'].get(key)
  if item is None:
   item=db['items'][key]={'title':title,'url':url,'source':KOOP_SOURCE,'first_seen':now,
     'updated':now,'last_change':None,'hash':hashlib.sha256((title+'|'+str(koop)).encode()).hexdigest(),
     'revisions':1}
   added+=1
  # Nieuwe versie bij KOOP (bijv. een rectificatie): versienummer of wijzigingsdatum anders.
  version=f"{first('hasVersion') or '1'}|{first('modified') or ''}"
  if item.get('koop_version') and item['koop_version']!=version:
   record_change(item,'Nieuwe versie bij KOOP',f"versiegegevens gewijzigd: {item['koop_version']} \u2192 {version}")
  item['koop_version']=version
  # Datums en kenmerken bijwerken is metadata, geen inhoudelijke revisie.
  types=[t for t in values('type') if '|' not in t]
  item.update(koop_dates=koop,doc_date=doc_date,doc_date_label=label,
    publication_date=koop['available'] or koop['issued'],last_seen=today(),
    koop_type=(types or values('type') or [None])[0],locatie=first('geometrielabel'),
    publicatie=first('publicatienaam'),
    excerpt=first('abstract') or ('Officiele bekendmaking; '+(label+': '+doc_date if doc_date else 'datum onbekend')))
 return added

def collect_official(db):
 """KOOP in twee delen:
 1. recent: elke run alles van de laatste KOOP_RECENT_DAYS dagen (vangt nieuwe stukken);
 2. backfill: per run één kalendermaand vanaf KOOP_START, tot de huidige maand is bereikt.
 Per deel wordt gecontroleerd of het aantal opgehaalde records gelijk is aan het
 totaal dat KOOP opgeeft. KOOP noemt dat totaal zelf een schatting."""
 now=utc(); state=db.setdefault('state',{})
 try:
  since=(datetime.date.today()-datetime.timedelta(days=KOOP_RECENT_DAYS)).isoformat()
  records,total=koop_fetch('dt.available>='+since)
  added=koop_store(db,records)
  note=f'Laatste {KOOP_RECENT_DAYS} dagen: {len(records)} van {total} opgehaald.'
  ok=len(records)>=total
  # Backfill: één maand per run.
  month=state.get('koop_backfill_month',KOOP_START[:7])
  current=datetime.date.today().strftime('%Y-%m')
  if month<current:
   y,mo=map(int,month.split('-'))
   nxt=f'{y+(mo==12)}-{(mo%12)+1:02d}'
   recs,tot=koop_fetch(f'dt.available>={month}-01 AND dt.available<{nxt}-01')
   added+=koop_store(db,recs)
   if len(recs)>=tot:
    state['koop_backfill_month']=nxt
    note+=f' Archief {month}: {len(recs)} van {tot} opgehaald.'
   else:
    ok=False
    note+=f' Archief {month}: slechts {len(recs)} van {tot}; volgende run opnieuw.'
  state['koop_complete_since']=KOOP_START if state.get('koop_backfill_month',KOOP_START[:7])>=current else None
  cover=('Volledig vanaf '+KOOP_START) if state['koop_complete_since'] else ('Archief bijgewerkt t/m '+state.get('koop_backfill_month',KOOP_START[:7])+' (nog bezig)')
  db['status'][KOOP_SOURCE]={'ok':ok,'checked':now,'count':len(records),'new':added,
    'note':note+' Dekking: '+cover+'. Ouder dan '+KOOP_START+' wordt niet opgehaald.'}
 except Exception as exc:
  db['status'][KOOP_SOURCE]={'ok':False,'checked':now,'error':str(exc)[:250]}

MAANDEN={'januari':1,'februari':2,'maart':3,'april':4,'mei':5,'juni':6,'juli':7,
 'augustus':8,'september':9,'oktober':10,'november':11,'december':12}
def parse_nl_date(text):
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
   date=parse_nl_date(clean(node.get_text(' ',strip=True)))
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
   old=db['items'][key]={'title':d['title'],'url':url,'source':source,'kind':'collegebesluit',
     'meeting_date':d['date'],'publication_date':None,'first_seen':now,'updated':now,
     'last_change':None,'hash':fingerprint,'revisions':1,
     'besluit_status':status[-1] if status else None,'excerpt':d['body'][:400]}
  # Alleen een revisie bij een aantoonbaar andere tekst van precies dit besluit,
  # met per zin wat er veranderde. De eerste keer is een nulmeting.
  compare_text(key,old,to_lines(d['body']),'Besluittekst gewijzigd')
  old.update(hash=fingerprint,excerpt=d['body'][:400],
    besluit_status=status[-1] if status else old.get('besluit_status'))
  old.update(doc_date=d['date'],doc_date_label='vergaderdatum college',last_seen=today())

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

def page_date(text,url):
 """Haal de datum uit de tekst van een opgehaalde pagina. Geeft (datum, label) of (None, None).

 Gecontroleerd op de echte pagina's (15 okt 2026):
 - nieuws op medemblik.nl:  'Publicatiedatum: Woensdag 7 oktober 2026'
 - raadsvragen in iBabs:    'Datum vraag 15-10-2026'"""
 m=re.search(r'publicatiedatum\s*:?\s*(?:[a-z]+dag\s+)?(\d{1,2}\s+[a-z]+\s+\d{4})',text.casefold())
 if m and parse_nl_date(m.group(1)): return parse_nl_date(m.group(1)),'publicatiedatum'
 if 'bestuurlijkeinformatie.nl/reports/item' in url.casefold():
  for label in ('Datum vraag','Datum ontvangst','Datum brief','Datum publicatie','Datum'):
   m=re.search(re.escape(label)+r'\s*:?\s*(\d{1,2})-(\d{1,2})-(\d{4})\b',text)
   if m:
    try: return datetime.date(int(m.group(3)),int(m.group(2)),int(m.group(1))).isoformat(),label.lower()
    except ValueError: pass
 return None,None

def is_navigation(title,href):
 """Menuknoppen van het raadsportaal ('Bekijk kalender', 'Bekijk overzichten') zijn geen publicaties."""
 path=urllib.parse.urlparse(href).path.rstrip('/').casefold()
 return title.casefold().startswith('bekijk ') or path in ('/calendar','/reports','/agenda')

def news_title_date(item):
 """Nieuwslinks heten bijv. 'Eerste paal Bries Medemblik geslagen Datum vrijdag 25 september 2026'.
 Haal de datum uit de titel en maak de titel schoon. De publicatiedatum op de pagina zelf
 (via de documentcontrole) is gelijk of nauwkeuriger en mag deze later overschrijven."""
 if item.get('source')!='Nieuws': return
 m=re.search(r'\s+Datum\s+(?:[A-Za-z]+dag\s+)?(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*$',item['title'])
 if not m or not parse_nl_date(m.group(1)): return
 item['title']=item['title'][:m.start()].strip()
 if not item.get('doc_date'):
  item['doc_date'],item['doc_date_label']=parse_nl_date(m.group(1)),'publicatiedatum'
  item['publication_date']=item['doc_date']

def migrate_dates(db):
 """Fase 2: vul de vaste datumvelden voor alle items, zonder bestaande gegevens te wissen.

   doc_date + doc_date_label  de datum van het stuk zelf en wat die datum betekent
   first_seen                 wanneer de monitor het item voor het eerst zag
   last_change                alleen gevuld bij een echte inhoudswijziging
   last_seen                  laatste dag dat het item nog in de bron stond
   content_checked            laatste inhoudscontrole van het document"""
 archive=db.setdefault('archief',{})
 for key,item in list(db['items'].items()):
  if is_navigation(item.get('title',''),item.get('url','')):
   item['archived']=utc(); item['archived_reason']='Menuknop, geen publicatie'
   archive[key]=db['items'].pop(key)
 db['status'].pop('Bekendmakingen',None)
 # Raadsdocumenten: echte bestandslink toevoegen en de foute nulmeting (viewerpagina) weggooien.
 for key,item in db['items'].items():
  if item.get('kind')=='raadsdocument' and 'file_url' not in item:
   q=urllib.parse.parse_qs(urllib.parse.urlparse(item['url']).query)
   doc_id=(q.get('documentId') or [item['url'].rstrip('/').rsplit('/',1)[-1]])[0]
   for k in ('text_hash','file_hash','content_checked','content_error'): item.pop(k,None)
   if text_path(key).exists(): text_path(key).unlink()
   item['file_url']=IBABS+'/Document/View/'+doc_id  # bron verwijderd: leverde 0 resultaten, KOOP dekt dit
 for item in db['items'].values():
  news_title_date(item)
  if 'last_change' not in item:
   item['last_change']=item.get('updated') if item.get('revisions',1)>1 else None
  if item.get('doc_date'): continue
  if item.get('meeting_date'):
   item['doc_date'],item['doc_date_label']=item['meeting_date'],'vergaderdatum college'
  elif item.get('source')=='Officiele bekendmakingen (KOOP)' and item.get('publication_date'):
   # Opgeslagen door versie 3 uit dcterms:date (aanmaakdatum). Wordt bij de volgende
   # KOOP-ophaalronde vervangen door de echte publicatiedatum als het record terugkomt.
   item['doc_date'],item['doc_date_label']=item['publication_date'],'documentdatum (KOOP)'
   item['publication_date']=None
   item['excerpt']='Officiele bekendmaking; documentdatum (KOOP): '+item['doc_date']
  elif '/Agenda/Index/' in item.get('url','') and parse_nl_date(item.get('title','')):
   item['doc_date'],item['doc_date_label']=parse_nl_date(item['title']),'vergaderdatum'

IBABS='https://medemblik.bestuurlijkeinformatie.nl'
# Vergadertypes in het raadsportaal (ids uit /Calendar, gecontroleerd 15 okt 2026).
IBABS_TYPES={0:'Gemeenteraad',100063720:'Raadscommissie',1:'Presidium',11:'Auditcommissie',
 100099145:'Informatiebijeenkomst',100067792:'Themabijeenkomst'}
MEETING_WINDOW_PAST=60    # dagen terug
MEETING_WINDOW_AHEAD=45   # dagen vooruit
MEETINGS_PER_RUN=10       # zoveel vergaderpagina's per run, om de site te ontzien
DOCS_SOURCE='Raadsstukken'

def ibabs_list_meetings(db):
 """Eén keer per dag: de jaarlijst per vergadertype ophalen."""
 state=db.setdefault('state',{}); meetings=state.setdefault('meetings',{})
 if state.get('meetings_listed')==today(): return None
 years={datetime.date.today().year}
 if datetime.date.today().month<=2: years.add(datetime.date.today().year-1)
 errors=[]
 for type_id,type_name in IBABS_TYPES.items():
  for year in sorted(years):
   try:
    r=requests.get(IBABS+'/Agenda/RetrieveAgendasForYear',params={'agendatypeId':type_id,'year':year},headers=HEADERS,timeout=30)
    r.raise_for_status()
    for a in BeautifulSoup(r.text,'html.parser').select('a[href*="/Agenda/Index/"]'):
     mid=a['href'].rstrip('/').rsplit('/',1)[-1]
     date=parse_nl_date(clean(a.get_text(' ',strip=True)))
     if not date: continue
     m=meetings.setdefault(mid,{'checked':''})
     m.update(type=type_name,date=date,label=clean(a.get_text(' ',strip=True)))
   except Exception as exc:
    errors.append(f'{type_name} {year}: {str(exc)[:60]}')
 state['meetings_listed']=today()
 return errors

def ibabs_parse_meeting(html):
 """Geeft [(titel, url, agendapunt)] voor alle documenten op een vergaderpagina."""
 page=BeautifulSoup(html,'html.parser')
 docs=[]; seen=set()
 for a in page.select('a[href*="/Agenda/Document/"], a[href*="/Document/View/"]'):
  href=urllib.parse.urljoin(IBABS,a['href'])
  if href in seen: continue
  seen.add(href)
  for badge in a.select('.badge'): badge.extract()
  title=clean(a.get_text(' ',strip=True))
  item=a.find_parent('div',class_='agenda-item')
  punt=None
  if item:
   pid=item.select_one('.panel-id'); lab=item.select_one('.panel-title-label')
   punt=clean(((pid.get_text(strip=True)+' ') if pid else '')+(lab.get_text(' ',strip=True) if lab else ''))
   punt=re.sub(r'\s*-\s*\d{1,2}:\d{2}$','',punt) or None
  if title: docs.append((title,href,punt))
 return docs

def collect_meetings(db):
 now=utc(); state=db.setdefault('state',{}); meetings=state.setdefault('meetings',{})
 try:
  errors=ibabs_list_meetings(db) or []
  lo=(datetime.date.today()-datetime.timedelta(days=MEETING_WINDOW_PAST)).isoformat()
  hi=(datetime.date.today()+datetime.timedelta(days=MEETING_WINDOW_AHEAD)).isoformat()
  window=[(mid,m) for mid,m in meetings.items() if lo<=m['date']<=hi]
  window.sort(key=lambda p:p[1].get('checked',''))
  added=0; fetched=0
  for mid,m in window[:MEETINGS_PER_RUN]:
   url=IBABS+'/Agenda/Index/'+mid
   try:
    r=requests.get(url,headers=HEADERS,timeout=30); r.raise_for_status()
   except Exception as exc:
    errors.append(f'{m["type"]} {m["date"]}: {str(exc)[:60]}'); m['checked']=now; continue
   fetched+=1; m['checked']=now
   meeting_title=f'{m["type"]} {m["label"]}'
   # De vergadering zelf (zelfde sleutel als de links van de startpagina).
   mkey=hashlib.sha256(('Raadsportaal|'+url).encode()).hexdigest()
   mitem=db['items'].setdefault(mkey,{'title':meeting_title,'url':url,'source':'Raadsportaal',
     'first_seen':now,'updated':now,'last_change':None,'hash':'','revisions':1,'excerpt':''})
   mitem.update(kind='vergadering',doc_date=m['date'],doc_date_label='vergaderdatum',last_seen=today())
   docs=ibabs_parse_meeting(r.text)
   m['documents']=len(docs)
   for title,href,punt in docs:
    q=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    doc_id=(q.get('documentId') or [href.rstrip('/').rsplit('/',1)[-1]])[0]
    key=hashlib.sha256((DOCS_SOURCE+'|'+doc_id).encode()).hexdigest()
    item=db['items'].get(key)
    if item is None:
     item=db['items'][key]={'title':title,'url':href,'source':DOCS_SOURCE,'kind':'raadsdocument',
       'first_seen':now,'updated':now,'last_change':None,'hash':'','revisions':1}
     added+=1
    # Eén document kan in meerdere vergaderingen staan (eerst commissie, dan raad).
    # Bewaar ze allemaal; datum en hoofdvergadering = de vroegste.
    seen_in=item.setdefault('meetings',[])
    entry={'date':m['date'],'meeting':meeting_title,'agendapunt':punt}
    if entry not in seen_in: seen_in.append(entry); seen_in.sort(key=lambda e:e['date'])
    eerste=seen_in[0]
    # De link in de lijst opent een viewerpagina (HTML met de hele vergadering).
    # Het bestand zelf staat op /Document/View/<documentId> (gecontroleerd 15 okt 2026).
    if 'file_url' not in item:
     # Eerdere controle vergeleek per ongeluk de viewerpagina: die nulmeting weggooien.
     for k in ('text_hash','file_hash','content_checked','content_error'): item.pop(k,None)
     if text_path(key).exists(): text_path(key).unlink()
     item['file_url']=IBABS+'/Document/View/'+doc_id
    item.update(doc_date=eerste['date'],doc_date_label='vergaderdatum',meeting_title=eerste['meeting'],
      agendapunt=eerste['agendapunt'],last_seen=today(),
      excerpt=eerste['meeting']+(' · agendapunt '+eerste['agendapunt'] if eerste['agendapunt'] else ' · vergaderdocumenten')
        +(f' · ook in {len(seen_in)-1} andere vergadering(en)' if len(seen_in)>1 else ''))
  total_docs=sum(1 for v in db['items'].values() if v.get('kind')=='raadsdocument')
  db['status'][DOCS_SOURCE]={'ok':not errors,'checked':now,'count':fetched,'new':added,
    'error':'; '.join(errors)[:250] if errors else None,
    'note':f'{fetched} van {len(window)} vergaderingen in venster bijgewerkt; {total_docs} documenten bekend. '
           f'Dekking: vergaderingen van {lo} t/m {hi} ({", ".join(IBABS_TYPES.values())}). Oudere vergaderingen niet.'}
 except Exception as exc:
  db['status'][DOCS_SOURCE]={'ok':False,'checked':now,'error':str(exc)[:250]}

# ---------------------------------------------------------------------------
# Fase 4: documentwijzigingen inhoudelijk volgen
# ---------------------------------------------------------------------------
TEXT_DIR=ROOT/'data'/'text'   # vorige tekstversie per document, nodig om te kunnen vergelijken
DOCS_PER_RUN=25
MAX_DOC_BYTES=15_000_000      # groter: alleen bestandskenmerken vergelijken, niet downloaden
TEXT_CAP=300_000              # maximaal aantal tekens tekst dat we per document bewaren
MAX_CHANGES=10                # zoveel wijzigingen per document bewaren

def check_interval(item):
 """Hoe vaak een document opnieuw wordt gecontroleerd, op basis van de leeftijd van het stuk.
 Verse stukken worden vaker aangepast (bijlage vervangen, tekst gecorrigeerd)."""
 ref=item.get('doc_date') or (item.get('first_seen') or '')[:10]
 try: age=(datetime.date.today()-datetime.date.fromisoformat(ref)).days
 except ValueError: age=0
 if age<=14: return datetime.timedelta(hours=6)
 if age<=60: return datetime.timedelta(days=1)
 if age<=180: return datetime.timedelta(days=7)
 return datetime.timedelta(days=30)

def is_due(item,now_dt):
 last=item.get('content_checked')
 if not last: return True
 try: return datetime.datetime.fromisoformat(last)+check_interval(item)<=now_dt
 except ValueError: return True

def to_lines(text):
 """Tekst in zinnen/regels knippen, zodat een wijziging per zin te tonen is."""
 text=(text or '')[:TEXT_CAP]
 parts=re.split(r'\n+|(?<=[.!?;])\s+(?=[A-Z0-9“"(])',text)
 return [clean(p) for p in parts if clean(p)]

def pdf_text(data):
 import io
 from pypdf import PdfReader
 reader=PdfReader(io.BytesIO(data))
 out=[]
 for page in reader.pages[:300]:
  try: out.append(page.extract_text() or '')
  except Exception: out.append('')
 return '\n'.join(out)

def text_path(key): return TEXT_DIR/(key[:24]+'.txt')

def record_change(item,kind,summary,added=(),removed=()):
 now=utc()
 change={'at':now,'type':kind,'summary':summary,
   'added':[a[:220] for a in added[:3]],'removed':[r[:220] for r in removed[:3]]}
 item.setdefault('changes',[]).append(change)
 item['changes']=item['changes'][-MAX_CHANGES:]
 item.update(updated=now,last_change=now,revisions=item.get('revisions',1)+1,change_type=kind)

def compare_text(key,item,lines,kind='Tekst gewijzigd'):
 """Vergelijk met de vorige tekstversie. De eerste keer is alleen een nulmeting."""
 import difflib
 digest=hashlib.sha256('\n'.join(lines).encode()).hexdigest()
 path=text_path(key)
 previous=item.get('text_hash')
 if previous and previous!=digest:
  old=path.read_text(encoding='utf-8').split('\n') if path.exists() else []
  sm=difflib.SequenceMatcher(None,old,lines,autojunk=False)
  added=[l for tag,i1,i2,j1,j2 in sm.get_opcodes() if tag in('insert','replace') for l in lines[j1:j2]]
  removed=[l for tag,i1,i2,j1,j2 in sm.get_opcodes() if tag in('delete','replace') for l in old[i1:i2]]
  if not old: summary='tekst gewijzigd (vorige versie niet bewaard)'
  else: summary=f'{len(added)} zin(nen) toegevoegd of aangepast, {len(removed)} verwijderd of vervangen'
  record_change(item,kind,summary,added,removed)
 if previous!=digest:
  TEXT_DIR.mkdir(parents=True,exist_ok=True)
  path.write_text('\n'.join(lines),encoding='utf-8')
 item['text_hash']=digest

def compare_file(item,fingerprint,why):
 """Voor bestanden zonder leesbare tekst (scans, video): alleen zien dát het bestand veranderde."""
 previous=item.get('file_hash')
 if previous and previous!=fingerprint:
  record_change(item,'Bestand gewijzigd','bestand vervangen ('+why+'); inhoud niet als tekst te vergelijken')
 item['file_hash']=fingerprint

def check_documents(db):
 now_dt=datetime.datetime.now(datetime.timezone.utc)
 overview=set(u.rstrip('/') for u in SOURCES.values())
 tracked=[(k,v) for k,v in db['items'].items() if v.get('url','').startswith((
   'https://www.medemblik.nl/','https://medemblik.bestuurlijkeinformatie.nl/'))
   and v.get('url','').rstrip('/') not in overview
   # Collegebesluiten en vergaderingen hebben hun eigen vergelijking.
   and v.get('kind') not in ('collegebesluit','vergadering') and '/Agenda/Index/' not in v.get('url','')]
 due=[(k,v) for k,v in tracked if is_due(v,now_dt)]
 # Nooit gecontroleerd eerst, daarna wie het langst over tijd is.
 due.sort(key=lambda p:p[1].get('content_checked') or '')
 checked=failures=pdf_count=noscan=0
 for key,item in due[:DOCS_PER_RUN]:
  try:
   head=requests.get(item.get('file_url') or item['url'],headers=HEADERS,timeout=30,stream=True)
   if head.status_code in (404,410):
    head.close()
    item['missing_count']=item.get('missing_count',0)+1
    # Twee keer achter elkaar weg: dan pas melden (één keer kan een storing zijn).
    if item['missing_count']>=2 and not item.get('removed'):
     item['removed']=utc()
     record_change(item,'Niet meer bereikbaar',f'document geeft HTTP {head.status_code}: verwijderd of verplaatst')
    item['content_checked']=utc(); checked+=1; continue
   head.raise_for_status()
   if item.pop('removed',None):
    record_change(item,'Weer bereikbaar','document is weer online')
   item['missing_count']=0
   size=int(head.headers.get('Content-Length') or 0)
   content_type=head.headers.get('Content-Type','').lower()
   if size>MAX_DOC_BYTES:
    head.close()
    compare_file(item,f"{size}|{head.headers.get('Last-Modified','')}|{head.headers.get('ETag','')}",'groot bestand')
   else:
    # Inlezen tot het maximum; sommige bestanden (video) sturen geen grootte mee.
    buf=bytearray()
    for chunk in head.iter_content(256*1024):
     buf+=chunk
     if len(buf)>MAX_DOC_BYTES: break
    head.close(); data=bytes(buf)
    if len(data)>MAX_DOC_BYTES:
     compare_file(item,f"groot|{head.headers.get('Content-Disposition','')}|{hashlib.sha256(data[:1_000_000]).hexdigest()}",'groot bestand')
    elif 'pdf' in content_type or data[:4]==b'%PDF':
     pdf_count+=1
     text=pdf_text(data)
     if len(clean(text))>=80: compare_text(key,item,to_lines(text))
     else:
      noscan+=1; compare_file(item,hashlib.sha256(data).hexdigest(),'pdf zonder leesbare tekst')
    elif 'html' in content_type or b'<html' in data[:500].lower():
     page=BeautifulSoup(data.decode(head.encoding or 'utf-8',errors='replace'),'html.parser')
     for tag in page(['script','style','nav','footer','header','form']):tag.decompose()
     area=page.select_one('main') or page.select_one('article') or page
     area_text=clean(area.get_text(' ',strip=True))
     # Datum van het stuk zelf uitlezen (nieuws: publicatiedatum, raadsvragen: datum vraag).
     if not item.get('doc_date') or item.get('doc_date_label') in ('publicatiedatum','datum vraag','datum ontvangst','datum brief','datum publicatie','datum'):
      found,label=page_date(area_text,item['url'])
      if not found: found,label=page_date(clean(page.get_text(' ',strip=True)),item['url'])
      if found:
       item['doc_date'],item['doc_date_label']=found,label
       if label=='publicatiedatum': item['publication_date']=found
     compare_text(key,item,to_lines(area.get_text('\n',strip=True)))
    else:
     compare_file(item,hashlib.sha256(data).hexdigest(),content_type or 'onbekend bestandstype')
   item['content_checked']=utc(); item.pop('content_error',None); checked+=1
  except Exception as exc:
   failures+=1
   item['content_checked']=utc(); item['content_error']=str(exc)[:120]
 backlog=max(0,len(due)-DOCS_PER_RUN)
 db['status']['Documentcontrole']={'ok':failures==0,'checked':utc(),'count':checked,'errors':failures,
   'note':f'{checked} documenten gecontroleerd ({pdf_count} pdf), {len(tracked)} gevolgd, {backlog} wachten nog. '
          'Controle: stukken tot 14 dagen oud elke 6 uur, tot 60 dagen dagelijks, tot 180 dagen wekelijks, ouder maandelijks. '
          'Wijzigingen worden per zin getoond; de eerste controle is een nulmeting. '
          'Pdf’s zonder leesbare tekst (scans) en grote bestanden: alleen te zien dát ze veranderden. '
          'KOOP-bekendmakingen via hun versiegegevens.'+(f' {noscan} pdf zonder tekst deze run.' if noscan else '')}

def main():
 DB.parent.mkdir(exist_ok=True); OUT.parent.mkdir(exist_ok=True)
 db=json.loads(DB.read_text()) if DB.exists() else {'items':{},'status':{}}
 archive_legacy_college(db)
 migrate_dates(db)
 collect_official(db)
 collect_meetings(db)
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
    if is_navigation(title,href):continue
    candidates.append((title,href))
   # College page: decisions have no own links. Structure: h2 = meeting date, h3 = decision,
   # h4 = 'Samenvatting'/'Besluit' (part of the decision text, never an item of its own).
   if source=='Collegebesluiten':
    collect_college(db,main,url)
   for title,href in candidates:
    key=hashlib.sha256((source+'|'+href).encode()).hexdigest()
    if key not in db['items']:
     db['items'][key]={'title':title,'url':href,'source':source,'first_seen':utc(),'updated':utc(),'last_change':None,'hash':hashlib.sha256(title.encode()).hexdigest(),'revisions':1,'excerpt':''}
     # Vergaderingen in het raadsportaal hebben de datum in de titel.
     if '/Agenda/Index/' in href and parse_nl_date(title):
      db['items'][key].update(doc_date=parse_nl_date(title),doc_date_label='vergaderdatum')
    news_title_date(db['items'][key])
    db['items'][key]['last_seen']=today()
   db['status'][source]={'ok':True,'checked':utc(),'count':len(candidates),'note':SOURCE_NOTES.get(source)}
  except Exception as e:
   db['status'][source]={'ok':False,'checked':utc(),'error':str(e)[:180]}
 check_documents(db)
 # Cap dataset to avoid endless Git history growth: keep the most recently active items.
 items=sorted(db['items'].items(),key=lambda kv:kv[1].get('last_change') or kv[1]['first_seen'],reverse=True)[:3000]
 db['items']=dict(items)
 DB.write_text(json.dumps(db,ensure_ascii=False,indent=2)+'\n')
 payload=json.dumps({'items':[v for _,v in items],'status':db['status']},ensure_ascii=False).replace('</','<\\/')
 html='''<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Medemblik Monitor</title><style>body{font:16px system-ui;margin:0;background:#f4f7fb;color:#172437}header{background:#123657;color:white;padding:24px}main{max-width:1050px;margin:24px auto;padding:0 16px}.panel{background:white;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 6px #0001}input,select{padding:12px;border:1px solid #aab8c6;border-radius:8px;max-width:100%;margin:5px}a{color:#075a9c}small{color:#536577}.error{color:#a52d2d}.ok{color:#177147}li{margin:14px 0}button{padding:10px;border-radius:8px;cursor:pointer}.tag{font-size:12px;padding:2px 8px;border-radius:9px;margin-left:6px;white-space:nowrap}.t-nieuw{background:#d6f0df;color:#145c37}.t-gewijzigd{background:#fde8c8;color:#7a4a00}.t-historisch{background:#ececec;color:#555}.t-gepland{background:#e3e0f7;color:#3d3480}.st{margin:8px 0}.t-verwijderd{background:#f6e1e1;color:#8a2c2c}.chg{display:block;margin-top:4px;padding:6px 10px;border-left:3px solid #e0a040;background:#fff8ee;font-size:14px}.chg details{margin-top:4px}.chg .plus{color:#145c37}.chg .min{color:#8a2c2c;text-decoration:line-through}.t-onbekend{background:#f6e1e1;color:#8a2c2c}</style></head><body><header><h1>Medemblik Monitor</h1><p>Openbare publicaties en wijzigingen · experimentele monitor</p></header><main><section class="panel"><strong id="count"></strong><p>Dit systeem detecteert wat het kan ophalen. Geen garantie op volledigheid of directe meldingen. Gesorteerd op de datum van het stuk zelf. Een oud stuk dat de monitor pas net vond, staat op zijn eigen datum met het label historisch.</p><input id="q" placeholder="Zoeken in titels"><select id="source"><option value="">Alle bronnen</option></select><select id="kind"><option value="">Alle</option><option value="nieuw">Nieuw</option><option value="gewijzigd">Gewijzigd</option><option value="verwijderd">Niet meer bereikbaar</option><option value="historisch">Historisch</option><option value="gepland">Gepland</option><option value="onbekend">Datum onbekend</option></select></section><section class="panel"><h2>Bronstatus</h2><div id="status"></div></section><section class="panel"><h2>Komende vergaderingen</h2><div id="upcoming"></div></section><section class="panel"><h2>Publicaties</h2><p><small>Nieuwste bovenaan, op datum van het stuk. Stukken zonder datum staan onderaan.</small></p><div id="results"></div></section></main><script>const DATA=__DATA__;const $=x=>document.getElementById(x);const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const sources=[...new Set(DATA.items.map(x=>x.source))];sources.forEach(s=>{let o=document.createElement('option');o.value=s;o.textContent=s;$('source').appendChild(o)});$('status').innerHTML=Object.entries(DATA.status).map(([s,v])=>`<div class="st"><span class="${v.ok?'ok':'error'}">${esc(s)}: ${v.ok?'OK':'LET OP'}</span> <small>· ${v.checked?new Date(v.checked).toLocaleString('nl-NL',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):''}${v.new?' · '+v.new+' nieuw':''}</small>${v.note?`<br><small>${esc(v.note)}</small>`:''}${v.error?`<br><small class="error">${esc(v.error)}</small>`:''}</div>`).join('');const TODAY=new Date().toISOString().slice(0,10);const day=s=>s?String(s).slice(0,10):'';const nl=s=>s?new Date(day(s)+'T12:00:00').toLocaleDateString('nl-NL',{day:'numeric',month:'long',year:'numeric'}):'onbekend';const diff=(a,b)=>(new Date(a)-new Date(b))/864e5;function kinds(x){let t=[],f=day(x.first_seen);if(!x.doc_date)t.push('onbekend');else if(x.doc_date>TODAY)t.push('gepland');else if(diff(f,x.doc_date)>30)t.push('historisch');else if(diff(TODAY,f)<=7)t.push('nieuw');if(x.last_change)t.push('gewijzigd');if(x.removed)t.push('verwijderd');return t}const LABEL={onbekend:'datum onbekend'};DATA.items.sort((a,b)=>(!!b.doc_date-!!a.doc_date)||(b.doc_date||day(b.first_seen)).localeCompare(a.doc_date||day(a.first_seen))||a.title.localeCompare(b.title));function li(x){return `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>${kinds(x).filter(t=>t!=='gepland').map(t=>`<span class="tag t-${t}">${LABEL[t]||t}</span>`).join('')}<br><small>${esc(x.source)} · ${x.doc_date?esc(x.doc_date_label||'datum')+': '+nl(x.doc_date):'datum van het stuk onbekend'}${x.besluit_status?' ('+esc(x.besluit_status)+')':''}${x.koop_type?' · '+esc(x.koop_type):''}${x.locatie?' · '+esc(x.locatie):''}${x.meeting_title?' · '+esc(x.meeting_title):''}${x.agendapunt?' · agendapunt '+esc(x.agendapunt):''}${x.meetings&&x.meetings.length>1?' · ook in '+(x.meetings.length-1)+' andere vergadering(en)':''} · ontdekt door monitor: ${nl(x.first_seen)}${x.last_change?' · inhoud gewijzigd: '+nl(x.last_change):''}${x.revisions>1?' · versies: '+x.revisions:''}</small>${chg(x)}</li>`}function chg(x){const c=(x.changes||[]).slice(-1)[0];if(!c)return '';const more=(x.changes.length>1?` · ${x.changes.length} wijzigingen geregistreerd`:'');const lines=[...(c.added||[]).map(l=>`<div class="plus">+ ${esc(l)}</div>`),...(c.removed||[]).map(l=>`<div class="min">\u2212 ${esc(l)}</div>`)].join('');return `<span class="chg"><strong>${esc(c.type)}</strong> op ${nl(c.at)}: ${esc(c.summary)}${more}${lines?`<details><summary>Wat is er veranderd</summary>${lines}</details>`:''}</span>`}function render(){let q=$('q').value.toLowerCase(),src=$('source').value,k=$('kind').value;let a=DATA.items.filter(x=>(!src||x.source===src)&&(!k||kinds(x).includes(k))&&(x.title+' '+(x.excerpt||'')).toLowerCase().includes(q));let up=a.filter(x=>kinds(x).includes('gepland')).sort((x,y)=>x.doc_date.localeCompare(y.doc_date));let rest=a.filter(x=>!kinds(x).includes('gepland'));$('count').textContent=a.length+' resultaten';$('upcoming').innerHTML=up.length?'<ul>'+up.map(li).join('')+'</ul>':'<p><small>Geen komende vergaderingen in deze selectie.</small></p>';$('results').innerHTML='<ul>'+rest.slice(0,500).map(li).join('')+'</ul>'}['q','source','kind'].forEach(id=>$(id).addEventListener('input',render));render();</script></body></html>'''
 OUT.write_text(html.replace('__DATA__',payload))
 print('Items:',len(items),'Sources:',db['status'])
if __name__=='__main__':main()
