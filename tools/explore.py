import requests, re, json
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def get(u, **kw):
    try:
        r = requests.get(u, headers=H, timeout=25, **kw)
        t = r.text
        flag = ' ANUBIS' if 'anubis' in t.lower() else (' CLOUDFLARE' if ('cf-chl' in t or 'Just a moment' in t) else '')
        title = (re.findall(r'<title>(.*?)</title>', t, re.S) or [''])[0].strip()[:70]
        print(f'== {u} {r.status_code}{flag} {r.headers.get("content-type","")[:30]} {len(t)} -> {r.url[:70]} | {title}')
        return r
    except Exception as e:
        print('==', u, 'ERR', str(e)[:80])
for slug, gem in [('stedebroec', 'Stede Broec'), ('enkhuizen', 'Enkhuizen'), ('drechterland', 'Drechterland')]:
    print('\n########', gem)
    r = get('https://repository.overheid.nl/sru', params={'query': f'c.product-area==officielepublicaties AND dt.creator=="{gem}" AND dt.modified>=2026-10-01', 'maximumRecords': 1})
    if r is not None: print('  KOOP sinds 1 okt:', re.findall(r'numberOfRecords>(\d+)', r.text))
    for u in [f'https://{slug}.bestuurlijkeinformatie.nl/', f'https://{slug}.raadsinformatie.nl/', f'https://{slug}.notubiz.nl/', f'https://raad.{slug}.nl/',
              f'https://gemeenteraad.{slug}.nl/', f'https://{slug}.ibabs.eu/', f'https://www.{slug}.nl/', f'https://www.{slug}.nl/nieuws', f'https://www.{slug}.nl/rss',
              f'https://www.{slug}.nl/nieuws/rss', f'https://www.{slug}.nl/nieuws/feed', f'https://www.{slug}.nl/actueel/nieuws']:
        r = get(u)
        if r is not None and r.ok and 'xml' in r.headers.get('content-type', ''):
            print('   XML:', r.text[:300].replace('\n', ' '))
        if r is not None and r.ok and u.startswith('https://www.') and u.endswith('.nl/'):
            print('   raadlinks:', sorted(set(re.findall(r'href="(https?://[^"]*(?:raad|ibabs|notubiz|bestuurlijke|vergader)[^"]*)"', r.text, re.I)))[:8])
            print('   feeds:', re.findall(r'<link[^>]+(?:rss|atom)[^>]*>', r.text)[:3])
    r = get('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free', params={'q': f'gemeentenaam:"{gem}"', 'fq': 'type:woonplaats', 'rows': 50, 'fl': 'woonplaatsnaam'})
    if r is not None and r.ok: print('  woonplaatsen:', sorted(d['woonplaatsnaam'] for d in r.json()['response']['docs']))
r = get('https://api.openraadsinformatie.nl/v1/elastic/_cat/indices?format=json')
if r is not None and r.ok:
    print('ORI:', [i['index'] for i in r.json() if any(s in i['index'] for s in ('stede', 'enkhuizen', 'drechterland'))])
