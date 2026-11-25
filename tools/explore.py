import requests, re
H = {'User-Agent': 'HoornPublicatieMonitor/0.1 (public information monitoring)'}
def get(u, **kw):
    try:
        r = requests.get(u, headers=H, timeout=25, **kw); t = r.text
        flag = ' ANUBIS' if 'anubis' in t.lower() else (' CLOUDFLARE' if ('cf-chl' in t or 'Just a moment' in t) else '')
        gen = re.findall(r'<meta[^>]+generator[^>]+content="([^"]+)"', t)[:1]
        title = (re.findall(r'<title>(.*?)</title>', t, re.S) or [''])[0].strip()[:60]
        print(f'== {u} {r.status_code}{flag} {r.headers.get("content-type","")[:25]} {len(t)} -> {r.url[:70]} | {title} {gen}')
        return r
    except Exception as e: print('==', u, 'ERR', str(e)[:80])
r = get('https://repository.overheid.nl/sru', params={'query': 'c.product-area==officielepublicaties AND dt.creator=="Hoorn" AND dt.modified>=2026-10-01', 'maximumRecords': 1})
print('KOOP sinds 1 okt:', re.findall(r'numberOfRecords>(\d+)', r.text) if r is not None else None)
for u in ['https://hoorn.bestuurlijkeinformatie.nl/', 'https://hoorn.raadsinformatie.nl/', 'https://hoorn.notubiz.nl/', 'https://raad.hoorn.nl/', 'https://gemeenteraad.hoorn.nl/',
          'https://hoorn.ibabs.eu/', 'https://www.hoorn.nl/', 'https://www.hoorn.nl/nieuws', 'https://www.hoorn.nl/rss', 'https://www.hoorn.nl/nieuws/rss', 'https://www.hoorn.nl/actueel/nieuws',
          'https://www.hoorn.nl/feed/', 'https://www.hoorn.nl/actueel/']:
    r = get(u)
    if r is not None and r.ok and 'xml' in r.headers.get('content-type', ''): print('   XML items:', r.text.count('<item'), r.text[:200].replace('\n', ' '))
    if r is not None and r.ok and u == 'https://www.hoorn.nl/':
        print('   raadlinks:', sorted(set(re.findall(r'href="(https?://[^"]*(?:raad|ibabs|notubiz|bestuurlijke|vergader)[^"]*)"', r.text, re.I)))[:8])
        print('   nieuwslinks:', sorted(set(re.findall(r'href="([^"]*(?:nieuws|actueel)[^"]*)"', r.text, re.I)))[:8])
        print('   feeds:', re.findall(r'<link[^>]+(?:rss|atom)[^>]*>', r.text)[:3])
r = get('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free', params={'q': 'gemeentenaam:"Hoorn"', 'fq': 'type:woonplaats', 'rows': 50, 'fl': 'woonplaatsnaam,gemeentenaam'})
if r is not None and r.ok: print('woonplaatsen:', sorted((d['woonplaatsnaam'], d['gemeentenaam']) for d in r.json()['response']['docs']))
r = get('https://api.openraadsinformatie.nl/v1/elastic/_cat/indices?format=json')
if r is not None and r.ok: print('ORI:', [i['index'] for i in r.json() if 'hoorn' in i['index']])
