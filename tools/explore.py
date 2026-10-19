import sys, re, requests
sys.path.insert(0, '.')
import monitor as m
from bs4 import BeautifulSoup
H = m.HEADERS
B = 'https://alkmaar.bestuurlijkeinformatie.nl'
r = requests.get(B + '/Calendar', headers=H, timeout=30)
soup = BeautifulSoup(r.text, 'html.parser')
print('hrefs:', sorted({a['href'] for a in soup.select('a[href]')})[:80])
print('scripts:', [s.get('src') for s in soup.select('script[src]')])
inline = ' '.join(s.get_text() for s in soup.select('script:not([src])'))
print('inline urls:', sorted(set(re.findall(r"['\"](/[A-Za-z]+/[A-Za-z]+[^'\"]{0,80})['\"]", inline)))[:40])
print('data-attrs:', sorted({k for t in soup.find_all(True) for k in t.attrs if k.startswith('data-')})[:40])
for path in ['/Calendar/GetAgendasForMonth?year=2026&month=10', '/Agenda/RetrieveAgendasForYear?year=2026', '/Calendar/Index?year=2026&month=9']:
    rr = requests.get(B + path, headers=H, timeout=30); print(path, rr.status_code, len(rr.text), rr.text[:300].replace('\n',' '))
print('== KOOP varianten')
import xml.etree.ElementTree as ET
for q in ['dt.creator=="Alkmaar"', 'dt.creator any "Alkmaar"', 'dt.creator=="Gemeente Alkmaar"', 'cql.textAndIndexes="Alkmaar" and c.product-area=="officielepublicaties" and dt.type=="gemeenteblad"']:
    try:
        rr = requests.get('https://repository.overheid.nl/sru', params={'query': q + ' and dt.available>=2026-09-01', 'maximumRecords': 5, 'httpAccept': 'application/xml'}, headers=H, timeout=60)
        n = re.search(r'numberOfRecords>(\d+)<', rr.text)
        creators = re.findall(r'creator[^>]*>([^<]+)<', rr.text)[:8]
        print(q, rr.status_code, n.group(1) if n else '?', creators)
    except Exception as e: print(q, e)
