import sys, re, requests
sys.path.insert(0, '.')
import monitor as m
from bs4 import BeautifulSoup
H = m.HEADERS
B = 'https://alkmaar.bestuurlijkeinformatie.nl'
r = requests.get(B + '/Calendar', headers=H, timeout=30)
soup = BeautifulSoup(r.text, 'html.parser')
ids = {}
for t in soup.select('[data-agendatype-id]'):
    ids[t['data-agendatype-id']] = re.sub(r'\s+', ' ', t.get_text(' ', strip=True))[:60]
for a in soup.select('a[href*="/Calendar/OpenCategory/"]'):
    ids.setdefault(a['href'].rsplit('/', 1)[-1], re.sub(r'\s+', ' ', a.get_text(' ', strip=True))[:60])
print(ids)
for i in ids:
    rr = requests.get(B + '/Calendar/OpenCategory/' + i, headers=H, timeout=30)
    s2 = BeautifulSoup(rr.text, 'html.parser')
    sub = {t['data-agendatype-id']: re.sub(r'\s+', ' ', t.get_text(' ', strip=True))[:60] for t in s2.select('[data-agendatype-id]')}
    print('cat', i, rr.status_code, (s2.title.get_text(strip=True) if s2.title else ''), sub)
    for j in list(sub) + [i]:
        y = requests.get(B + '/Agenda/RetrieveAgendasForYear', params={'agendatypeId': j, 'year': 2026}, headers=H, timeout=30)
        links = BeautifulSoup(y.text, 'html.parser').select('a[href*="/Agenda/Index/"]')
        print('   type', j, y.status_code, len(links), [l.get_text(' ', strip=True)[:50] for l in links[:3]])
for a in soup.select('a[href*="/Agenda/Index/"]'):
    print('agenda', a['href'], re.sub(r'\s+', ' ', a.get_text(' ', strip=True))[:80])
