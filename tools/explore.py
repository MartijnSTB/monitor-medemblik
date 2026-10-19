import requests, re, json
H = {'User-Agent': 'AlkmaarPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://dijkenwaard.bestuurlijkeinformatie.nl'
r = requests.get(B + '/Calendar', headers=H, timeout=30)
print('calendar', r.status_code)
print('types:', sorted(set(re.findall(r'(?:agendatypeId|data-agendatypeid|value)="?(\d{6,})"?[^>]*>\s*([^<]{2,80})', r.text)))[:40])
r = requests.get(B + '/', headers=H, timeout=30)
print('home links:', sorted(set(re.findall(r'href="(/[A-Za-z]+(?:/[A-Za-z]+)?)[/"?]', r.text)))[:40])
print('home agendatypes:', sorted(set(re.findall(r'/Agenda/Index/[^"]*"[^>]*>([^<]{0,80})', r.text)))[:10])
r = requests.get(B + '/Reports', headers=H, timeout=30)
print('reports', r.status_code, sorted(set(re.findall(r'/Reports/Details/([0-9a-f-]{36})[^>]*>\s*([^<]{2,80})', r.text)))[:40])
for y in [2026]:
    for tid in sorted(set(re.findall(r'agendatypeId=(\d+)', requests.get(B + '/Calendar', headers=H, timeout=30).text))) or []:
        pass
# Try agenda listing for found types
cal = requests.get(B + '/Calendar', headers=H, timeout=30).text
ids = sorted(set(re.findall(r'\b(1000\d{5})\b', cal)))
print('ids in calendar:', ids[:30])
for tid in ids[:15]:
    try:
        x = requests.get(B + '/Agenda/RetrieveAgendasForYear', params={'agendatypeId': tid, 'year': 2026}, headers=H, timeout=30)
        j = x.json() if x.ok else None
        print('type', tid, x.status_code, (json.dumps(j, ensure_ascii=False)[:300] if j else x.text[:100]))
    except Exception as e: print(tid, e)
# ORI newest
for sort in ['date_modified', 'last_discussed_at', 'start_date']:
    q = {'size': 3, 'sort': [{sort: {'order': 'desc', 'unmapped_type': 'date'}}], '_source': ['name', '@type', sort]}
    x = requests.post('https://api.openraadsinformatie.nl/v1/elastic/ori_dijk_en_waard_*/_search', json=q, headers=H, timeout=30)
    print('ORI', sort, json.dumps([h['_source'] for h in x.json()['hits']['hits']], ensure_ascii=False)[:400])
# News page
n = requests.get('https://www.dijkenwaard.nl/actueel/nieuws', headers=H, timeout=30).text
i = n.find('/actueel/nieuws/')
print('news snippet:', re.sub(r'\s+', ' ', n[i-600:i+1400]))
print('feeds:', re.findall(r'[^"\s]*(?:rss|feed|atom)[^"\s]*', n, re.I)[:10])
