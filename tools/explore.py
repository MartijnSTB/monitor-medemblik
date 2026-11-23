import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
sq = lambda t: re.sub(r'\s+', ' ', t)
def get(u):
    try:
        r = requests.get(u, headers=H, timeout=30); return r
    except Exception as e: print(u, e)
for slug in ('enkhuizen', 'drechterland', 'stedebroec'):
    print('\n########', slug)
    for u in [f'https://www.{slug}.nl/collegebesluiten/', f'https://www.{slug}.nl/besluitenlijsten/', f'https://www.{slug}.nl/bestuur/college/',
              f'https://www.{slug}.nl/?s=besluitenlijst', f'https://www.{slug}.nl/?s=collegebesluiten']:
        r = get(u)
        if r is None: continue
        links = sorted(set(re.findall(r'href="([^"#]*(?:college|besluit)[^"#]*)"', r.text, re.I)))
        print('==', u, r.status_code, r.url[:80], len(r.text)); print('   ', links[:15])
    base = f'https://gemeenteraad.{slug}.nl'
    if slug != 'stedebroec':
        r = get(base + '/')
        if r is not None:
            print('== GO links:', sorted(set(re.findall(r'href="(/(?:overzichten|documenten|Documenten|Overzichten)[^"#]*)"', r.text)))[:30])
        for pad in ['/overzichten/raadsbrief', '/documenten', '/overzichten']:
            r = get(base + pad)
            if r is not None:
                print('== ', pad, r.status_code, len(r.text), sorted(set(re.findall(r'href="(/(?:overzichten|documenten|Documenten)/[^"#]{2,80})"', r.text)))[:25])
