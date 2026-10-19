import sys, re, requests
sys.path.insert(0, '.')
import monitor as m
from bs4 import BeautifulSoup
H = m.HEADERS
B = 'https://alkmaar.bestuurlijkeinformatie.nl'
print('== Calendar / agendatypes')
for path in ['/Calendar', '/', '/Agenda']:
    r = requests.get(B + path, headers=H, timeout=30)
    print(path, r.status_code, len(r.text))
    soup = BeautifulSoup(r.text, 'html.parser')
    for o in soup.select('option'):
        if o.get('value'): print('  option', o.get('value'), o.get_text(strip=True)[:60])
    ids = set(re.findall(r'agendatypeId=(\d+)[^"]*"[^>]*>([^<]{0,60})', r.text))
    print('  agendatypeId links', list(ids)[:20])
    print('  ids in tekst', sorted(set(re.findall(r'(?:agendatype|agendaType|AgendaType)\w*["\':= ]+(\d{1,12})', r.text)))[:30])
print('== Reports')
r = requests.get(B + '/Reports', headers=H, timeout=30)
print([(a.get_text(' ', strip=True)[:50], a['href'][-40:]) for a in BeautifulSoup(r.text, 'html.parser').select('a[href*="/Reports/Details/"]')])
print('== People'); r = requests.get(B + '/People', headers=H, timeout=30); print(r.status_code)
print('== alkmaar.nl')
for u in ['https://www.alkmaar.nl/', 'https://www.alkmaar.nl/nieuws', 'https://www.alkmaar.nl/nieuws.rss', 'https://www.alkmaar.nl/rss/content-list?type%5B%5D=news&sort_by=published_at&sort_order=DESC']:
    try:
        r = requests.get(u, headers=H, timeout=30)
        print(u, r.status_code, r.headers.get('content-type'), len(r.text))
        if 'xml' in (r.headers.get('content-type') or '') or u.endswith('rss'):
            print('   ', r.text[:400].replace('\n', ' '))
        else:
            soup = BeautifulSoup(r.text, 'html.parser')
            print('   rss:', [l.get('href') for l in soup.select('link[type*=rss], a[href*=rss]')][:5])
            print('   links:', sorted({a['href'] for a in soup.select('a[href]') if re.search(r'nieuws|college|besluit|woo|bekendmak|raad', a['href'], re.I)})[:40])
    except Exception as e: print(u, e)
print('== KOOP')
recs = m.koop_fetch('Alkmaar', 'dt.available>=2026-09-01')
print('KOOP sinds 1 sep:', len(recs))
print('== PDOK woonplaatsen')
r = requests.get('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free', params={'q': '*', 'fq': ['type:woonplaats', 'gemeentenaam:"Alkmaar"'], 'rows': 50, 'fl': 'woonplaatsnaam'}, headers=H, timeout=30)
print(sorted(d['woonplaatsnaam'] for d in r.json()['response']['docs']))
print('== CBS wijken Alkmaar')
r = requests.get('https://opendata.cbs.nl/ODataApi/odata/85984NED/WijkenEnBuurten', params={'$format': 'json', '$filter': "startswith(Key,'WK0361')"}, headers=H, timeout=60)
print([(w['Key'].strip(), w['Title']) for w in r.json()['value']])
print('== Google Nieuws test')
r = requests.get('https://news.google.com/rss/search', params={'q': 'Alkmaar when:2d', 'hl': 'nl', 'gl': 'NL', 'ceid': 'NL:nl'}, headers=H, timeout=30)
print(r.status_code, r.text.count('<item>'))
