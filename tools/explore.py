import requests, re
H = {'User-Agent': 'HoornPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://hoorn.bestuurlijkeinformatie.nl'
t = requests.get(B + '/Calendar', headers=H, timeout=30).text
cats = re.findall(r'href="/Calendar/OpenCategory/(-?\d+)"\s*>([^<]+)<', t); print('cats:', cats)
for tid, naam in cats:
    x = requests.get(B + '/Agenda/RetrieveAgendasForYear', params={'agendatypeId': tid, 'year': 2026}, headers=H, timeout=30)
    labels = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', l)).strip() for l in re.findall(r'/Agenda/Index/[^"]*"[^>]*>(.*?)</a>', x.text, re.S)]
    print(tid, naam.strip(), x.status_code, len(labels), labels[:2])
