import requests
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)', 'Accept': 'application/json'}
U = 'https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek'
for extra in [{'sort': 'x'}, {'publicatiedatumVan': 'x'}, {'sort': 'publicatiedatum'}, {'sort': 'datum'}, {'sort': 'DATUM_AFLOPEND'}, {'sort': 'nieuwste'}, {'sort': 'openbaarmakingsdatum'}, {'sort': 'desc'},
              {'publicatiedatumVan': '01-09-2026'}, {'publicatiedatumVan': '2026-09-01T00:00:00Z'}, {'publicatiedatumVan': '20260901'}, {'aantal': 50}, {'rows': 50}, {'limit': 50}, {'pagina': 2}, {'offset': 20}]:
    r = requests.get(U, params={'zoektekst': 'Medemblik', **extra}, headers=H, timeout=40)
    j = r.json() if r.headers.get('content-type','').startswith('application/json') else {}
    print(extra, r.status_code, j.get('totaal'), len(j.get('resultaten', []) or []), [x['document'].get('openbaarmakingsdatum') for x in (j.get('resultaten') or [])][:6], (j.get('detail') or '')[:400])
