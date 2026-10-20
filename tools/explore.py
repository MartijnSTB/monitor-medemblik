import requests, json
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)', 'Accept': 'application/json'}
U = 'https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek'
for p in [{'zoektekst': 'Medemblik'}, {'text': 'Medemblik'}, {'query': 'Medemblik'}, {'zoek': 'Medemblik'}, {'trefwoord': 'Medemblik'},
          {'publisher': 'Medemblik'}, {'organisatie': 'Medemblik'}, {'zoektekst': 'Medemblik', 'sort': 'datum'}]:
    try:
        r = requests.get(U, params={**p, 'size': 3}, headers=H, timeout=40)
        j = r.json() if r.ok else {}
        print(p, r.status_code, j.get('totaal'), [ (x['document'].get('titel') or '')[:60] + ' | ' + str(x['document'].get('publisher')) for x in j.get('resultaten', [])][:3])
    except Exception as e: print(p, e)
for u in ['https://open.overheid.nl/overheid/openbaarmakingen/api/v0/', 'https://open.overheid.nl/overheid/openbaarmakingen/api/v0/openapi.json',
          'https://open.overheid.nl/overheid/openbaarmakingen/api/v0/v3/api-docs', 'https://open.overheid.nl/overheid/openbaarmakingen/api/v0/api-docs']:
    r = requests.get(u, headers=H, timeout=40); print('==', u, r.status_code, r.text[:1500].replace('\n',' '))
