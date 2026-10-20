import requests
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)', 'Accept': 'application/json'}
U = 'https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek'
base = {'zoektekst': 'Medemblik', 'size': 5}
for extra in [{}, {'sort': 'openbaarmakingsdatum,desc'}, {'sort': 'mutatiedatumtijd,desc'}, {'sortering': 'datum'}, {'sorteer': 'datum'}, {'order': 'desc'},
              {'openbaarmakingsdatumVanaf': '2026-09-01'}, {'datumVanaf': '2026-09-01'}, {'publicatiedatumVan': '2026-09-01'}, {'vanaf': '2026-09-01'},
              {'from': 0}, {'start': 0}, {'page': 1}, {'publisher': 'gemeente Medemblik'}, {'zoektekst': '"Medemblik"', 'size': 5},
              {'zoektekst': 'Medemblik', 'sort': 'relevantie'}, {'sortOrder': 'DESC', 'sortField': 'openbaarmakingsdatum'}, {'sorteren': 'nieuwste'}]:
    try:
        r = requests.get(U, params={**base, **extra}, headers=H, timeout=40)
        j = r.json() if r.ok else {}
        print(extra, r.status_code, j.get('totaal'), [x['document'].get('openbaarmakingsdatum') for x in j.get('resultaten', [])], r.text[:150] if not r.ok else '')
    except Exception as e: print(extra, e)
r = requests.get(U, params=base, headers=H, timeout=40); print(r.text[:2500])
