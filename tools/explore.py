import os, re, requests
K = os.environ.get('KOGGENLAND_PROXY_KEY', '')
P = 'https://martijn-media.nl/monitor/koggenland.php'
def get(pad):
    return requests.get(P, params={'pad': pad}, headers={'X-Monitor-Key': K}, timeout=60)
def strip(t): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))
r = get('/Vergaderingen/Gemeenteraad/2026/09-november/19:30')
t = r.text; print('== meeting', r.status_code, len(t))
i = t.find('<main'); i = i if i > 0 else t.find('id="content"')
print(strip(t[i:i+3000])[:2500])
print('doc links:', sorted(set(re.findall(r'href="([^"]*(?:document|Document|\.pdf|download)[^"]*)"', t)))[:25])
m = re.search(r'(<li[^>]*class="[^"]*agenda[^"]*"[\s\S]{0,1500})', t)
print('agenda html sample:', re.sub(r'\s+', ' ', m.group(1))[:1500] if m else None)
for pad in ['/rss', '/documenten', '/Vergaderingen/Gemeenteraad/', '/Vergaderingen/Beeldvormende-commissievergadering-Sociaal-Domein/']:
    r = get(pad); t = r.text
    print('==', pad, r.status_code, r.headers.get('content-type'), len(t))
    if 'xml' in (r.headers.get('content-type') or ''): print(t[:1500])
    else:
        print('  links:', sorted(set(re.findall(r'href="(/(?:Vergaderingen|vergaderingen|documenten|Documenten)[^"#]{3,120})"', t)))[:40])
