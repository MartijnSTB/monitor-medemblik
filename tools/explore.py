import sys, re, io, csv, requests
sys.path.insert(0, '.')
import monitor as m
from bs4 import BeautifulSoup
H = m.HEADERS
B = 'https://data.overheid.nl/sites/default/files/dataset/09cf04e7-11ac-4b53-a2cc-baccf95e82fd/resources/'
for f in ['Raadzetels_GR2026.csv', 'GR2026.csv']:
    r = requests.get(B + f, headers=H, timeout=120)
    print('==', f, r.status_code, len(r.content))
    txt = r.content.decode('utf-8-sig', errors='replace')
    lines = txt.splitlines()
    print('kop:', lines[:2])
    hits = [l for l in lines if re.search(r'Medemblik|Koggenland|Opmeer', l)]
    print(len(hits))
    for l in hits[:60]: print('  ', l[:260])
print('\n== raadsleden')
for g, path in [('medemblik', '/People/Profiles/5320a26c-ce32-405d-be1c-85f32e811e19'), ('opmeer', '/People/Profiles/f5c576ce-c1e9-47eb-907d-b287f074b8be')]:
    r = requests.get(m.GEMEENTEN[g]['ibabs'] + path, headers=H, timeout=20)
    soup = BeautifulSoup(r.text, 'html.parser')
    main = soup.select_one('main') or soup
    print(g, r.status_code, re.sub(r'\s+', ' ', main.get_text(' ', strip=True))[:2500])
    print([(a.get_text(' ', strip=True)[:40], a['href']) for a in main.select('a[href*="/People/"]')][:8])
