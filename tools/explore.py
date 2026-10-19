import json, sys, re, requests
sys.path.insert(0, '.')
import monitor as m
from bs4 import BeautifulSoup
H = m.HEADERS
print('=== People pagina Medemblik')
for g in ['medemblik', 'opmeer']:
    r = requests.get(m.GEMEENTEN[g]['ibabs'] + '/People', headers=H, timeout=20)
    soup = BeautifulSoup(r.text, 'html.parser')
    main = soup.select_one('main') or soup
    txt = re.sub(r'\s+', ' ', main.get_text(' ', strip=True))
    print(g, txt[:1500])
    links = [(a.get_text(' ', strip=True)[:50], a['href']) for a in main.select('a[href]') if '/People/' in a['href']][:15]
    print(links)
print('\n=== CBS')
for tid in ['86358NED', '86165NED', '85984NED']:
    r = requests.get(f'https://opendata.cbs.nl/ODataApi/odata/{tid}/TypedDataSet', params={'$format': 'json', '$filter': "startswith(WijkenEnBuurten,'WK0420')", '$top': '3'}, headers=H, timeout=40)
    print(tid, r.status_code)
    try:
        rows = r.json()['value']
        print(len(rows))
        if rows:
            filled = {k: v for k, v in rows[0].items() if v not in (None, '', '.')}
            print(len(rows[0]), 'velden,', len(filled), 'gevuld'); print(json.dumps(filled, ensure_ascii=False)[:1800])
    except Exception as e:
        print(r.text[:300])
r = requests.get('https://opendata.cbs.nl/ODataApi/odata/85984NED/DataProperties', params={'$format': 'json'}, headers=H, timeout=40)
print('\nvelden 2024:', [(p.get('Key'), p.get('Title')) for p in r.json()['value'] if p.get('Key')][:140])
r = requests.get('https://opendata.cbs.nl/ODataApi/odata/85984NED/WijkenEnBuurten', params={'$format': 'json', '$filter': "startswith(Key,'WK0420') or startswith(Key,'WK1598') or startswith(Key,'WK0432') or Key eq 'GM0420' or Key eq 'GM1598' or Key eq 'GM0432'"}, headers=H, timeout=40)
print('\nwijken:', [(w['Key'], w['Title']) for w in r.json()['value']])
