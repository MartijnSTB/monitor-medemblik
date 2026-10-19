import sys, json, requests
sys.path.insert(0, '.')
import monitor as m
H = m.HEADERS
E = 'https://api.openraadsinformatie.nl/v1/elastic/ori_alkmaar_*/_search'
for sort in ['last_discussed_at', 'start_date', 'date_modified']:
    try:
        r = requests.post(E, json={'size': 5, 'sort': [{sort: {'order': 'desc', 'unmapped_type': 'date'}}], '_source': ['name', '@type', 'start_date', 'last_discussed_at', 'date_modified', 'original_url', 'url']}, headers=H, timeout=40)
        print('==', sort, r.status_code)
        for h in r.json().get('hits', {}).get('hits', []): print('  ', json.dumps(h['_source'], ensure_ascii=False)[:300])
    except Exception as e: print(sort, e)
r = requests.post(E, json={'size': 0, 'aggs': {'t': {'terms': {'field': '@type.keyword', 'size': 20}}}}, headers=H, timeout=40)
print('types', r.status_code, r.text[:600])
for u in ['https://api.notubiz.nl/organisations?format=json', 'https://api.notubiz.nl/events?organisation_id=0&format=json']:
    try:
        r = requests.get(u, headers=H, timeout=30); print(u, r.status_code, r.headers.get('content-type'), r.text[:300].replace('\n',' '))
        if 'organisations' in u and r.ok:
            import re
            print([o for o in re.findall(r'.{0,120}Alkmaar.{0,80}', r.text)][:5])
    except Exception as e: print(u, e)
