import requests, re
H = {'User-Agent': 'HoornPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://hoorn.bestuurlijkeinformatie.nl'
for pad in ['/Calendar', '/Agenda', '/']:
    t = requests.get(B + pad, headers=H, timeout=30).text
    print('==', pad, len(t))
    print('  agendatype mentions:', [re.sub(r'\s+', ' ', t[m.start()-80:m.start()+120]) for m in re.finditer(r'agendatype', t, re.I)][:4])
    print('  options:', re.findall(r'<option[^>]*value="([^"]+)"[^>]*>\s*([^<]{2,60})', t)[:20])
    print('  agenda links:', re.findall(r'href="(/Agenda/Index/[^"]+)"', t)[:5])
