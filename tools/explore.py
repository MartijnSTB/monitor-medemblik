import requests, json, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)', 'Accept': 'application/json'}
def t(u, **kw):
    try:
        r = requests.get(u, headers=H, timeout=40, **kw)
        print('==', r.status_code, r.headers.get('content-type'), r.url[:200]); print(r.text[:1200].replace('\n', ' ')); print()
    except Exception as e: print('==', u, e)
# politie
t('https://api.politie.nl/v4/nieuws', params={'query': 'Medemblik', 'maxnumberofitems': 5})
t('https://api.politie.nl/v4/nieuws', params={'lat': 52.77, 'lon': 5.10, 'radius': 10, 'maxnumberofitems': 5})
t('https://api.politie.nl/v4/nieuws/lokaal', params={'lat': 52.77, 'lon': 5.10, 'radius': 10, 'maxnumberofitems': 5})
t('https://api.politie.nl/v4/vermist', params={'query': 'Medemblik', 'maxnumberofitems': 3})
# open overheid
t('https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek', params={'q': 'Medemblik', 'size': 3})
t('https://open.overheid.nl/zoekresultaten', params={'text': 'Medemblik'})
t('https://open.overheid.nl/api/zoek', params={'text': 'Medemblik'})
t('https://repository.overheid.nl/sru', params={'query': 'c.product-area==plooi AND Medemblik', 'maximumRecords': 2})
t('https://repository.overheid.nl/sru', params={'query': 'c.product-area==oep AND Medemblik', 'maximumRecords': 2})
