import requests, re, json
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
SRU = 'https://repository.overheid.nl/sru'
def koop(q, n=10):
    r = requests.get(SRU, params={'query': q, 'maximumRecords': n, 'sortKeys': 'dt.modified,,0'}, headers=H, timeout=60)
    num = re.findall(r'numberOfRecords>(\d+)', r.text)
    recs = re.findall(r'<dcterms:identifier>([^<]+)</dcterms:identifier><dcterms:title>([^<]+)</dcterms:title>.*?<dcterms:creator[^>]*>([^<]+)</dcterms:creator><dcterms:modified>([^<]+)<', r.text, re.S)
    print('==', q[:200], r.status_code, num)
    for x in recs[:n]: print('   ', x[3], x[2], x[0], x[1][:110])
    if r.status_code != 200 or not num: print(r.text[:500])
koop('c.product-area==officielepublicaties AND (Medemblik OR Wognum OR Andijk) AND dt.modified>=2026-09-20 NOT dt.creator=="Medemblik"', 25)
koop('c.product-area==officielepublicaties AND (Koggenland OR Obdam OR Avenhorn OR Spierdijk) AND dt.modified>=2026-09-01 NOT dt.creator=="Koggenland"', 15)
koop('c.product-area==officielepublicaties AND (Opmeer OR Hoogwoud OR Spanbroek) AND dt.modified>=2026-09-01 NOT dt.creator=="Opmeer"', 15)
# TK recent with or-chain
TK = 'https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Document'
f = "(" + " or ".join(f"contains(Onderwerp,'{p}') or contains(Titel,'{p}')" for p in ['Medemblik','Koggenland','Opmeer','Wognum','Andijk','Westfriesland','West-Friesland']) + ") and Verwijderd eq false and Datum ge 2024-01-01"
r = requests.get(TK, params={'$filter': f, '$orderby': 'Datum desc', '$top': 10, '$select': 'Id,Soort,Onderwerp,Titel,Datum,DocumentNummer'}, headers=H, timeout=60)
print('TK', r.status_code); 
for v in r.json().get('value', []) if r.ok else []: print('   ', v['Datum'][:10], v['Soort'], v['DocumentNummer'], (v['Onderwerp'] or '')[:100])
if not r.ok: print(r.text[:400])
# Agenda HTML structure of a Medemblik meeting
cal = requests.get('https://medemblik.bestuurlijkeinformatie.nl/Agenda/RetrieveAgendasForYear', params={'agendatypeId': 0, 'year': 2026}, headers=H, timeout=30).text
ids = re.findall(r'/Agenda/Index/([0-9a-f-]{36})', cal)
print('meetings', len(ids))
for mid in ids[:2]:
    p = requests.get('https://medemblik.bestuurlijkeinformatie.nl/Agenda/Index/' + mid, headers=H, timeout=30).text
    items = re.findall(r'<div[^>]*class="[^"]*agenda-item[^"]*"', p)
    print('agenda-item divs', len(items))
    i = p.find('panel-title-label')
    print(re.sub(r'\s+', ' ', p[i-900:i+600]))
    break
