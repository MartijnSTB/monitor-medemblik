import requests, re
H = {'User-Agent': 'AlkmaarPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://dijkenwaard.bestuurlijkeinformatie.nl'
cal = requests.get(B + '/Calendar', headers=H, timeout=30).text
for tid in sorted(set(re.findall(r'\b(1000\d{5})\b', cal))):
    i = cal.find(tid); print(tid, re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', cal[i-150:i+200]))[:200])
    x = requests.get(B + '/Agenda/RetrieveAgendasForYear', params={'agendatypeId': tid, 'year': 2026}, headers=H, timeout=30)
    labels = [re.sub(r'\s+', ' ', l).strip() for l in re.findall(r'/Agenda/Index/[^"]*"[^>]*>(.*?)</a>', x.text, re.S)]
    print('   ', len(labels), labels[-3:])
