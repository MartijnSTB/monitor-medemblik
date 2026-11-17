import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
sq = lambda t: re.sub(r'\s+', ' ', t)
for slug in ('enkhuizen', 'drechterland'):
    r = requests.get(f'https://gemeenteraad.{slug}.nl/', headers=H, timeout=30); t = r.text
    print('##', slug, r.status_code, 'GO' if 'GO. vergaderen' in t or 'gemeenteoplossingen' in t.lower() else '', re.findall(r'<meta[^>]+generator[^>]*>', t)[:2])
    print('  links:', sorted(set(re.findall(r'href="(/Vergaderingen/[^"#?]{2,90})"', t)))[:25])
    print('  andere:', sorted(set(re.findall(r'href="(/[A-Za-z][^"#?]{2,60})"', t)))[:40])
for slug in ('stedebroec', 'enkhuizen', 'drechterland'):
    r = requests.get(f'https://www.{slug}.nl/', headers=H, timeout=30); t = r.text
    print('##', slug, 'nieuws-links:', sorted(set(re.findall(r'href="(https://www\.' + slug + r'\.nl/[^"#?]*(?:nieuws|actueel|bericht)[^"#?]*)"', t, re.I)))[:15])
    for u in [f'https://www.{slug}.nl/feed/?post_type=nieuws', f'https://www.{slug}.nl/nieuwsberichten/', f'https://www.{slug}.nl/actueel/', f'https://www.{slug}.nl/wp-json/wp/v2/types']:
        try:
            x = requests.get(u, headers=H, timeout=30)
            print('   ', u, x.status_code, x.headers.get('content-type', '')[:25], len(x.text), x.url[:80], '|', sq(x.text[:250]) if 'json' in x.headers.get('content-type', '') or 'xml' in x.headers.get('content-type', '') else '')
        except Exception as e: print('   ', u, e)
