import requests
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for u in ['https://raad.koggenland.nl/nieuws/rss', 'https://raad.koggenland.nl/nieuws/', 'https://raad.koggenland.nl/rss']:
    try:
        r = requests.get(u, headers=H, timeout=30)
        print('==', u, r.status_code, r.headers.get('content-type'), len(r.text))
        print(r.text[:1500])
    except Exception as e: print(u, e)
