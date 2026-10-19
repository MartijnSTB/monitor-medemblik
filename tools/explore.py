import requests, re, json
H = {'User-Agent': 'AlkmaarPublicatieMonitor/0.1 (public information monitoring)'}
def get(u, n=600, **kw):
    try:
        r = requests.get(u, headers=H, timeout=30, **kw)
        print('==', u, r.status_code, r.headers.get('content-type'), len(r.text), r.url if r.url != u else '')
        return r
    except Exception as e: print('==', u, 'ERR', e)
# KOOP
r = get('https://repository.overheid.nl/sru', params={'query': 'c.product-area==officielepublicaties AND dt.creator=="Dijk en Waard" AND dt.modified>=2026-09-01', 'maximumRecords': 1})
if r is not None: print(re.findall(r'numberOfRecords>(\d+)', r.text))
# iBabs / notubiz / raadsinformatie
for u in ['https://dijkenwaard.bestuurlijkeinformatie.nl/', 'https://dijkenwaard.raadsinformatie.nl/', 'https://dijkenwaard.notubiz.nl/', 'https://raad.dijkenwaard.nl/', 'https://gemeenteraad.dijkenwaard.nl/',
          'https://www.dijkenwaard.nl/', 'https://www.dijkenwaard.nl/nieuws', 'https://www.dijkenwaard.nl/nieuws/feed', 'https://www.dijkenwaard.nl/rss', 'https://www.dijkenwaard.nl/actueel']:
    r = get(u)
    if r is not None and r.ok:
        t = r.text
        print('  anubis' if 'anubis' in t else '', '  cloudflare' if 'cf-chl' in t or 'Just a moment' in t else '')
        print('  title:', (re.findall(r'<title>(.*?)</title>', t, re.S) or [''])[0].strip()[:100])
        print('  rss links:', re.findall(r'<link[^>]+(?:rss|atom)[^>]*>', t)[:5])
        print('  agendatypes:', re.findall(r'agendatypeId=(\d+)[^>]*>([^<]{0,60})', t)[:20])
        if 'xml' in (r.headers.get('content-type') or ''): print(t[:800])
        hrefs = sorted(set(re.findall(r'href="([^"]*(?:nieuws|raad|bestuur|vergader|bekendmak|woo)[^"]*)"', t, re.I)))[:30]
        print('  hrefs:', hrefs)
# ORI
r = get('https://api.openraadsinformatie.nl/v1/elastic/_cat/indices?format=json')
if r is not None and r.ok:
    try: print([i['index'] for i in r.json() if 'dijk' in i['index'] or 'waard' in i['index'] or 'heerhugo' in i['index'] or 'langedijk' in i['index']])
    except Exception as e: print(e, r.text[:300])
for idx in ['ori_dijk_en_waard_*', 'ori_dijkenwaard_*', 'ori_heerhugowaard_*', 'osi_dijk_en_waard_*']:
    try:
        r = requests.post(f'https://api.openraadsinformatie.nl/v1/elastic/{idx}/_search', json={'size': 3, 'sort': [{'date_modified': {'order': 'desc', 'unmapped_type': 'date'}}], '_source': ['name', '@type', 'date_modified']}, headers=H, timeout=30)
        print('ORI', idx, r.status_code, json.dumps([h['_source'] for h in r.json().get('hits', {}).get('hits', [])], ensure_ascii=False)[:500])
    except Exception as e: print('ORI', idx, e)
# Woonplaatsen
r = get('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free', params={'q': 'gemeentenaam:"Dijk en Waard"', 'fq': 'type:woonplaats', 'rows': 50, 'fl': 'woonplaatsnaam'})
if r is not None and r.ok: print(sorted(d['woonplaatsnaam'] for d in r.json()['response']['docs']))
