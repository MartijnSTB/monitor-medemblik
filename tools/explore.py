import sys, re, requests
sys.path.insert(0, '.')
import monitor as m
from bs4 import BeautifulSoup
H = m.HEADERS
for u in ['https://raad.alkmaar.nl/', 'https://alkmaar.raadsinformatie.nl/', 'https://gemeenteraad.alkmaar.nl/', 'https://alkmaar.notubiz.nl/', 'https://www.alkmaar.nl/bestuur-organisatie/', 'https://www.alkmaar.nl/bestuur-organisatie/gemeenteraad/']:
    try:
        r = requests.get(u, headers=H, timeout=25, allow_redirects=True)
        soup = BeautifulSoup(r.text, 'html.parser')
        print(u, r.status_code, r.url, (soup.title.get_text(strip=True)[:80] if soup.title else ''), 'beveiliging' if 'Beveiligingscontrole' in r.text else '')
        if 'alkmaar.nl/bestuur' in u:
            print('   ', sorted({a['href'] for a in soup.select('a[href]') if re.search(r'raad|notubiz|ibabs|vergader', a['href'], re.I)})[:30])
    except Exception as e: print(u, 'FOUT', str(e)[:100])
r = requests.get('https://api.openraadsinformatie.nl/v1/elastic/_cat/indices?format=json', headers=H, timeout=30)
try: print('ORI:', sorted(i['index'] for i in r.json() if 'alkmaar' in i['index']))
except Exception as e: print('ORI', r.status_code, r.text[:200])
