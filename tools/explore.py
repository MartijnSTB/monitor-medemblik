import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
sq = lambda t: re.sub(r'\s+', ' ', t)
for u in ['https://gemeenteraad.enkhuizen.nl/overzichten/raadsbrief/', 'https://gemeenteraad.drechterland.nl/Documenten/Raadsbrieven']:
    t = requests.get(u, headers=H, timeout=30).text
    i = t.find('document-row'); i = i if i > 0 else t.find('<table')
    print('==', u, len(t), 'document-rows:', t.count('document-row'), 'tr:', t.count('<tr'))
    print(sq(t[i-1500:i+2500]))
for slug in ('enkhuizen', 'drechterland'):
    t = requests.get(f'https://www.{slug}.nl/bestuur-en-organisatie/bekendmakingen-en-besluiten/', headers=H, timeout=30).text
    print('== besluiten', slug, sorted(set(re.findall(r'href="(https://www\.' + slug + r'\.nl/[^"#]*)"', t)))[:60])
