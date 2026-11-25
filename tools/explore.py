import requests, re
H = {'User-Agent': 'HoornPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://hoorn.bestuurlijkeinformatie.nl'
cal = requests.get(B + '/Calendar', headers=H, timeout=30).text
for tid in sorted(set(re.findall(r'\b(1000\d{5})\b', cal))):
    i = cal.find(tid); naam = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', cal[i-10:i+200]))[:90]
    x = requests.get(B + '/Agenda/RetrieveAgendasForYear', params={'agendatypeId': tid, 'year': 2026}, headers=H, timeout=30)
    labels = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', l)).strip() for l in re.findall(r'/Agenda/Index/[^"]*"[^>]*>(.*?)</a>', x.text, re.S)]
    print(tid, '|', naam, '|', len(labels), labels[:2])
r = requests.get(B + '/Reports', headers=H, timeout=30)
print('reports:', sorted(set(re.findall(r'/Reports/Details/([0-9a-f-]{36})[^>]*>\s*([^<]{2,80})', r.text)))[:30])
x = requests.get('https://www.hoorn.nl/rss.rss', headers=H, timeout=30).text
print('RSS:', re.findall(r'<pubDate>([^<]+)</pubDate>', x)[:3], re.findall(r'<title>([^<]+)</title>', x)[1:4])
