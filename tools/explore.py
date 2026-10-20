import requests, re, json
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def show(tag, r, n=1500):
    print('==', tag, r.status_code, r.headers.get('content-type'), r.url[:250]); print(r.text[:n]); print()
# Tweede Kamer OData
TK = 'https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/'
for q in ["contains(Onderwerp,'Medemblik')", "contains(Titel,'Medemblik')", "contains(Onderwerp,'Wognum')"]:
    try:
        r = requests.get(TK + 'Document', params={'$filter': q + ' and Verwijderd eq false', '$orderby': 'Datum desc', '$top': 5,
                         '$select': 'Id,Soort,Onderwerp,Titel,Datum,DocumentNummer,GewijzigdOp'}, headers=H, timeout=40)
        show('TK ' + q, r, 1500)
    except Exception as e: print('TK', q, e)
# Zaak search (Kamervragen)
try:
    r = requests.get(TK + 'Zaak', params={'$filter': "contains(Onderwerp,'Medemblik') and Verwijderd eq false", '$orderby': 'GestartOp desc', '$top': 5, '$select': 'Id,Soort,Onderwerp,GestartOp,Nummer'}, headers=H, timeout=40)
    show('TK zaak', r, 1200)
except Exception as e: print(e)
# KOOP provincie/waterschap with location
SRU = 'https://repository.overheid.nl/sru'
for q in ['c.product-area==officielepublicaties AND dt.creator=="Noord-Holland" AND dt.modified>=2026-10-01',
          'c.product-area==officielepublicaties AND dt.creator=="Hoogheemraadschap Hollands Noorderkwartier" AND dt.modified>=2026-10-01',
          'c.product-area==officielepublicaties AND dt.creator=="Noord-Holland" AND Medemblik AND dt.modified>=2026-08-01',
          'c.product-area==officielepublicaties AND cql.textAndIndexes="Medemblik" AND dt.modified>=2026-10-01',
          'c.product-area==officielepublicaties AND w.gemeente=="Medemblik" AND dt.modified>=2026-10-01']:
    try:
        r = requests.get(SRU, params={'query': q, 'maximumRecords': 3, 'httpAccept': 'application/xml'}, headers=H, timeout=40)
        n = re.findall(r'numberOfRecords>(\d+)', r.text)
        print('== KOOP', q, r.status_code, n)
        for rec in re.findall(r'<sru:recordData>(.*?)</sru:recordData>', r.text, re.S)[:2]:
            print('   ', re.sub(r'\s+', ' ', rec)[:1500])
        if not n: print(r.text[:600])
    except Exception as e: print('KOOP', q, e)
# Rechtspraak open data
try:
    r = requests.get('https://data.rechtspraak.nl/uitspraken/zoeken', params={'modified': '2026-10-19T00:00:00', 'return': 'DOC', 'max': 5,
                     'subject': 'http://psi.rechtspraak.nl/rechtsgebied#bestuursrecht'}, headers=H, timeout=40)
    show('RS zoeken', r, 1500)
    r2 = requests.get('https://data.rechtspraak.nl/uitspraken/zoeken', params={'modified': '2026-10-19T00:00:00', 'return': 'DOC', 'max': 1000}, headers=H, timeout=60)
    print('RS count all since 19 okt:', r2.text.count('<entry>'))
    r3 = requests.get('https://data.rechtspraak.nl/uitspraken/zoeken', params={'modified': '2026-10-19T00:00:00', 'return': 'DOC', 'max': 1000, 'subject': 'http://psi.rechtspraak.nl/rechtsgebied#bestuursrecht'}, headers=H, timeout=60)
    print('RS bestuursrecht since 19 okt:', r3.text.count('<entry>'))
    ecli = re.findall(r'<id>(ECLI:[^<]+)</id>', r.text)
    if ecli:
        c = requests.get('https://data.rechtspraak.nl/uitspraken/content', params={'id': ecli[0]}, headers=H, timeout=40)
        show('RS content', c, 2500)
except Exception as e: print('RS', e)
# Uitspraken website search API (public)
try:
    r = requests.post('https://uitspraken.rechtspraak.nl/api/zoek', json={'StartRow': 0, 'PageSize': 5, 'ShouldReturnHighlights': False, 'ShouldCountFacets': False, 'SortOrder': 'PublicatieDatumDesc', 'SearchTerms': [{'Term': 'Medemblik', 'Field': 'AlleVelden'}], 'Contentsoorten': [], 'Rechtsgebieden': [], 'Instanties': [], 'DatumPublicatie': [], 'DatumUitspraak': [], 'Advanced': {'PublicatieStatus': 'AlleenGepubliceerd'}, 'CorrelationId': 'x', 'Proceduresoorten': []}, headers=H, timeout=40)
    show('RS web api', r, 1500)
except Exception as e: print('RS web', e)
# Raad van State
try:
    r = requests.get('https://www.raadvanstate.nl/uitspraken/', params={'zoeken': 'true', 'zoeken_term': 'Medemblik'}, headers=H, timeout=40)
    print('== RvS', r.status_code, len(r.text), 'anubis' in r.text, 'Just a moment' in r.text)
    print(re.findall(r'href="(/uitspraken/@[^"]+)"', r.text)[:5])
except Exception as e: print('RvS', e)
