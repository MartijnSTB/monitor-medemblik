"""Werkplek: verzamelt de cijfers voor het werkdashboard (werk/index.html).

Draait één keer per dag via GitHub Actions (werk.yml) en schrijft data/werk.json.

Bronnen (allemaal openbaar):
  - Raadsportalen (iBabs) van Medemblik en Opmeer: moties, amendementen, raadsvragen / politieke vragen,
    toezeggingen en de raadsleden per fractie. Koggenland: raadsinformatie zit achter een beveiligingscheck.
  - Kiesraad, gemeenteraadsverkiezingen 18 maart 2026 (data.overheid.nl, CC-0): zetels, stemmen,
    opkomst en gekozen kandidaten met woonplaats.
  - CBS Kerncijfers wijken en buurten 2024, 2025 en 2026: per wijk. De CBS-wijken in deze drie gemeenten
    zijn precies de dorpen. Per cijfer wordt het nieuwste jaar gebruikt waarin het gevuld is.
"""
import csv, io, json, re, datetime, time
import requests
from bs4 import BeautifulSoup
import monitor as m

OUT = m.DB.parent / 'werk.json'
HEADERS = m.HEADERS
GEM = {'medemblik': ('0420', 'Medemblik'), 'koggenland': ('1598', 'Koggenland'), 'opmeer': ('0432', 'Opmeer')}
VERKIEZING = '2026-03-18'
KIESRAAD = 'https://data.overheid.nl/sites/default/files/dataset/09cf04e7-11ac-4b53-a2cc-baccf95e82fd/resources/GR2026.csv'
CBS_TABELLEN = [('2026', '86358NED'), ('2025', '86165NED'), ('2024', '85984NED')]

# Partijnamen zoals ze in titels en overzichten voorkomen -> één korte naam.
PARTIJEN = {
    'medemblik': {
        'HvM': ['Hart voor Medemblik', 'HvM'], 'VVD': ['VVD'], 'CDA': ['CDA'],
        'GB': ['GemeenteBelangen', 'Gemeentebelangen', 'Gemeente Belangen', 'GB'],
        'Morgen!': ['MORGEN!/Sociaal&Progressief', 'MORGEN!', 'Morgen!', 'Morgen'],
        'FvD': ['Forum voor Democratie', 'FvD', 'FVD'], 'D66': ['D66'], 'CU': ['ChristenUnie', 'CU'],
        'PvdA': ['PvdA'], 'GroenLinks': ['GroenLinks'],
    },
    'opmeer': {
        'KERN8': ['KERN8', 'KERN 8', 'Kern8'], 'CDA': ['CDA'], 'VVD': ['VVD'],
        'GB': ['Gemeentebelangen Opmeer', 'Gemeentebelangen', 'GemeenteBelangen', 'GB'],
        'LPO': ['Lokale Partij Opmeer(LPO)', 'Lokale Partij Opmeer', 'LPO'], 'PRO': ['PRO Opmeer', 'PRO'],
        'PvdA/GL': ['GROENLINKS/Partij van de Arbeid (PvdA)', 'PvdA / GroenLinks', 'PvdA/GroenLinks', 'GroenLinks/PvdA'],
        'DSV': ['DSV'],
    },
    'koggenland': {
        'VVD': ['VVD'], 'GBK': ['Gemeente Belangen Koggenland'], 'CDA': ['CDA'], 'FvD': ['Forum voor Democratie'],
        'GL/PvdA': ['GROENLINKS / Partij van de Arbeid (PvdA)'], 'D66': ['D66'],
    },
}

def partijen_in(gid, text):
    """Alle partijen die in een tekst genoemd worden (hele woorden), bijv. 'Raadsvragen CDA en VVD'."""
    found = []
    text = text or ''
    for kort, namen in PARTIJEN[gid].items():
        for naam in sorted(namen, key=len, reverse=True):
            if re.search(r'(?<![\w!])' + re.escape(naam) + r'(?![\w])', text):
                found.append(kort)
                break
    return found

def vraag_partijen(gid, titel):
    """Wie stelde de vraag? Alleen partijen direct na 'Raadsvragen' / 'Politieke vragen', zodat
    'Raadsvragen Morgen! over sandwichborden van Forum voor Democratie' alleen Morgen! telt."""
    t = re.sub(r'^\s*(aanvullende\s+)?(raadsvragen|politieke vragen|schriftelijke vragen|vragen)\s*(van\s+(de\s+)?(fractie\s+)?|fractie\s+)?', '', titel or '', flags=re.I)
    alias = sorted(((n, k) for k, ns in PARTIJEN[gid].items() for n in ns), key=lambda x: -len(x[0]))
    found = []
    while True:
        hit = next(((n, k) for n, k in alias if re.match(re.escape(n) + r'(?![\w])', t, re.I if n.isupper() is False and len(n) > 4 else 0)), None)
        if not hit:
            break
        found.append(hit[1])
        t = t[len(hit[0]):]
        sep = re.match(r'\s*(,|&|/|\ben\b)\s*', t)
        if not sep:
            break
        t = t[sep.end():]
    return list(dict.fromkeys(found))

def partij(gid, naam):
    p = partijen_in(gid, naam)
    return p[0] if p else (naam or '').strip()

# ---------------------------------------------------------------------------
# Raadsportaal-overzichten
# ---------------------------------------------------------------------------
def report_rows(gid, naam):
    """Alle regels van een overzicht (bijv. 'Raadsvragen'), 100 per keer."""
    db = json.loads(m.DB.read_text())
    reps = db['state']['reports'][gid]['reports']
    rid, rep = next(((k, v) for k, v in reps.items() if v['name'] == naam), (None, None))
    if not rid:
        return []
    base = m.GEMEENTEN[gid]['ibabs']
    rows, start = [], 0
    while True:
        batch, total = m.ibabs_report_rows(base, rid, rep['columns'], rep.get('order_col', 0), start, 100)
        for r in batch:
            r['_url'] = f"{base}/Reports/Item/{r.get('DT_RowId')}"
        rows += batch
        start += 100
        if not batch or start >= total or start > 3000:
            break
        time.sleep(0.5)
    return rows

def val(r, k):
    v = r.get(k)
    return '' if v in (None, 'None') else str(v).strip()

def dmy(text):
    return m.parse_dmy(text or '')

def lines(text):
    return [l.strip() for l in re.split(r'\n|<br\s*/?>', text or '') if l.strip()]

def indiener(s):
    """'Berlijn, T. (Tjeu) (HvM)' -> ('Tjeu Berlijn', 'HvM')."""
    mm = re.match(r'\s*([^,(]+),\s*([^()]*?)\s*(?:\(([^)]*)\))?\s*\(([^)]*)\)\s*$', s)
    if not mm:
        return s.strip(), ''
    achternaam, initialen, roepnaam, partijnaam = mm.groups()
    tussen = ''
    parts = initialen.split()
    if len(parts) > 1:  # 'E. van den' -> tussenvoegsel 'van den'
        tussen = ' '.join(p for p in parts if not p.endswith('.'))
    naam = ' '.join(x for x in [roepnaam or initialen.split()[0] if initialen else '', tussen, achternaam.strip()] if x)
    return naam, partijnaam

def raad_medemblik():
    gid = 'medemblik'
    moties = []
    for r in report_rows(gid, 'Moties en amendementen'):
        hoofd = indiener(val(r, 'hoofdindiener')) if val(r, 'hoofdindiener') else ('', '')
        mede = [indiener(x) for x in lines(val(r, 'medeindiener'))]
        moties.append({
            'titel': val(r, 'title'), 'soort': 'amendement' if 'amendement' in val(r, 'type').lower() else 'motie',
            'type': val(r, 'type'), 'status': val(r, 'status'), 'datum': dmy(val(r, 'registrationdate')),
            'vergadering': val(r, 'registrationdate'), 'poho': val(r, 'portefeuillehouder'),
            'indiener': hoofd[0], 'partijen': list(dict.fromkeys(p for p in [partij(gid, hoofd[1])] + [partij(gid, x[1]) for x in mede] if p)),
            'hoofdpartij': partij(gid, hoofd[1]) if hoofd[1] else '', 'mede': [x[0] for x in mede], 'url': r['_url'],
        })
    vragen = [{'titel': val(r, 'title'), 'datum': dmy(val(r, 'datum')), 'antwoord': dmy(val(r, 'datumantwoord')),
               'poho': val(r, 'poho'), 'partijen': vraag_partijen(gid, val(r, 'title')), 'url': r['_url']}
              for r in report_rows(gid, 'Raadsvragen')]
    toezeggingen = [{'titel': val(r, 'title'), 'datum': dmy(val(r, 'registrationdate')), 'open': val(r, 'completed') == 'Nee',
                     'poho': val(r, 'portefeuillehouder'), 'omschrijving': val(r, 'omschrijving')[:400],
                     'stand': val(r, 'standvanzaken')[:300], 'partijen': [], 'url': r['_url']}
                    for r in report_rows(gid, 'Toezeggingen')]
    return moties, vragen, toezeggingen

def raad_opmeer():
    gid = 'opmeer'
    moties = []
    for naam, kol, soort in [('Moties', 'raadsleden', 'motie'), ('Amendementen', 'Fracties', 'amendement')]:
        for r in report_rows(gid, naam):
            fr = [partij(gid, x) for x in lines(val(r, kol))]
            moties.append({'titel': val(r, 'title'), 'soort': soort, 'type': soort, 'status': val(r, 'status'),
                           'datum': dmy(val(r, 'registrationdate')), 'vergadering': val(r, 'registrationdate'),
                           'poho': val(r, 'portefeuillehouder'), 'indiener': '', 'partijen': list(dict.fromkeys(fr)),
                           'hoofdpartij': fr[0] if len(fr) == 1 else '', 'mede': [], 'url': r['_url']})
    vragen = [{'titel': val(r, 'title'), 'datum': dmy(val(r, 'registrationdate')), 'antwoord': dmy(val(r, 'datumantwoord')),
               'afgedaan': val(r, 'afgedaan') == 'Ja', 'poho': '', 'partijen': vraag_partijen(gid, val(r, 'title')), 'url': r['_url']}
              for r in report_rows(gid, 'Politieke vragen')]
    toezeggingen = [{'titel': val(r, 'title'), 'datum': dmy(val(r, 'registrationdate')), 'open': val(r, 'afgedaan') == 'Nee',
                     'poho': val(r, 'portefeuillehouder'), 'omschrijving': '', 'stand': '',
                     'partijen': [partij(gid, x) for x in lines(val(r, 'fractie'))], 'url': r['_url']}
                    for r in report_rows(gid, 'Toezeggingen')]
    return moties, vragen, toezeggingen

def raadsleden(gid):
    """Raadsleden per fractie van de pagina 'Gemeenteraad' in het raadsportaal."""
    base = m.GEMEENTEN[gid]['ibabs']
    r = requests.get(base + '/People', headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, 'html.parser')
    link = next((a['href'] for a in soup.select('a[href*="/People/Profiles/"]') if a.get_text(strip=True) == 'Gemeenteraad'), None)
    if not link:
        return []
    r = requests.get(base + link, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, 'html.parser')
    main = soup.select_one('main') or soup
    leden, fractie = [], ''
    for el in main.find_all(['h1', 'h2', 'h3', 'h4', 'a']):
        t = re.sub(r'\s+', ' ', el.get_text(' ', strip=True))
        if el.name != 'a':
            # Alleen kopjes die een bekende partij zijn (een naam in een kopje binnen een link telt niet).
            kop = re.sub(r'\s*\(\d+ zetels?\)$', '', t)
            if kop and partijen_in(gid, kop) and not el.find_parent('a'):
                fractie = partij(gid, kop)
            continue
        if '/People/Details/' not in el.get('href', ''):
            continue
        mm = re.match(r'(.+?)\s+(Fractievoorzitter|Raadslid|Voorzitter|Plaatsvervangend voorzitter|Burgerraadslid|Commissielid)\b', t)
        if mm:
            vacature = mm.group(1).lower().startswith(('opvolger', 'vacature'))
            leden.append({'naam': mm.group(1), 'functie': mm.group(2), 'fractie': fractie, 'vacature': vacature})
    return leden

# ---------------------------------------------------------------------------
# Kiesraad: gemeenteraadsverkiezingen 2026
# ---------------------------------------------------------------------------
def verkiezingen():
    r = requests.get(KIESRAAD, headers=HEADERS, timeout=180)
    r.raise_for_status()
    out = {gid: {'lijsten': {}, 'gekozen': [], 'totaal': {}} for gid in GEM}
    namen = {naam: gid for gid, (_, naam) in GEM.items()}
    for row in csv.DictReader(io.StringIO(r.content.decode('utf-8-sig', errors='replace')), delimiter=';'):
        gid = namen.get(row['Regio'])
        if not gid or not row['RegioCode'].startswith('G'):
            continue
        veld, waarde, lijst = row['VeldType'], row['Waarde'], row['LijstNaam']
        o = out[gid]
        if not lijst:
            o['totaal'][veld] = int(waarde) if waarde.isdigit() else waarde
        elif veld == 'KandidaatGekozen' and waarde == '1':
            naam = ' '.join(x for x in [row['KandidaatVoornaam'], row['KandidaatTussenvoegsel'], row['KandidaatAchternaam']] if x)
            o['gekozen'].append({'naam': naam, 'lijst': partij(gid, lijst) or lijst, 'nummer': int(row['KandidaatNummer'] or 0),
                                 'woonplaats': row['KandidaatWoonplaats'], 'geslacht': row['KandidaatGeslacht']})
        elif not row['KandidaatNummer']:
            L = o['lijsten'].setdefault(partij(gid, lijst) or lijst, {'naam': lijst})
            if veld in ('LijstAantalZetels', 'LijstAantalStemmen', 'AantalStemmen'):
                L['zetels' if veld == 'LijstAantalZetels' else 'stemmen'] = int(waarde)
    return out

# ---------------------------------------------------------------------------
# CBS: kerncijfers per dorp (wijk)
# ---------------------------------------------------------------------------
def cbs():
    codes = [f'WK{c}' for c, _ in GEM.values()]
    gm = [f'GM{c}' for c, _ in GEM.values()]
    # CBS-codes zijn met spaties aangevuld ('GM0420    '), dus 'startswith' in plaats van 'eq'.
    flt = ' or '.join(f"startswith(WijkenEnBuurten,'{c}')" for c in codes + gm + ['NL00'])
    regios, velden = {}, {}
    for jaar, tid in CBS_TABELLEN:
        props = requests.get(f'https://opendata.cbs.nl/ODataApi/odata/{tid}/DataProperties', params={'$format': 'json'}, headers=HEADERS, timeout=60).json()['value']
        titels = {p['Key']: (p.get('Title') or '').strip() for p in props if p.get('Key')}
        units = {p['Key']: (p.get('Unit') or '').strip() for p in props if p.get('Key')}
        rows = requests.get(f'https://opendata.cbs.nl/ODataApi/odata/{tid}/TypedDataSet', params={'$format': 'json', '$filter': flt}, headers=HEADERS, timeout=90).json()['value']
        namen = {w['Key'].strip(): w['Title'].strip() for w in requests.get(
            f'https://opendata.cbs.nl/ODataApi/odata/{tid}/WijkenEnBuurten', params={'$format': 'json', '$filter': ' or '.join(f"startswith(Key,'{c}')" for c in codes + gm + ['NL00'])}, headers=HEADERS, timeout=60).json()['value']}
        for row in rows:
            code = row['WijkenEnBuurten'].strip()
            if code.startswith('BU'):
                continue
            reg = regios.setdefault(code, {'code': code, 'naam': namen.get(code, code), 'gemeente': row.get('Gemeentenaam_1', '').strip(), 'cijfers': {}})
            for k, v in row.items():
                base = re.sub(r'_\d+$', '', k)
                if base in ('ID', 'WijkenEnBuurten', 'Gemeentenaam', 'SoortRegio', 'Codering', 'IndelingswijzigingGemeenteWijkBuurt', 'MeestVoorkomendePostcode'):
                    continue
                if v is None or (isinstance(v, str) and v.strip() in ('', '.')):
                    continue
                if base not in reg['cijfers']:  # nieuwste jaar eerst
                    reg['cijfers'][base] = {'w': v.strip() if isinstance(v, str) else v, 'j': jaar}
                if base == 'AantalInwoners':
                    reg.setdefault('inwoners_per_jaar', {})[jaar] = v
                velden.setdefault(base, {'titel': titels.get(k, base), 'eenheid': units.get(k, '')})
    return {'regios': regios, 'velden': velden}

def main():
    out = {'gegenereerd': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
           'verkiezingsdatum': VERKIEZING, 'gemeenten': {}, 'fouten': []}
    oud = json.loads(OUT.read_text()) if OUT.exists() else {}
    for gid, (code, naam) in GEM.items():
        g = out['gemeenten'][gid] = {'naam': naam, 'code': code}
        try:
            if gid == 'medemblik':
                g['moties'], g['vragen'], g['toezeggingen'] = raad_medemblik()
            elif gid == 'opmeer':
                g['moties'], g['vragen'], g['toezeggingen'] = raad_opmeer()
            if m.GEMEENTEN[gid]['ibabs']:
                g['raadsleden'] = raadsleden(gid)
        except Exception as exc:
            out['fouten'].append(f'Raad {naam}: {exc}'[:300])
            for k in ('moties', 'vragen', 'toezeggingen', 'raadsleden'):
                if k in (oud.get('gemeenten', {}).get(gid) or {}):
                    g[k] = oud['gemeenten'][gid][k]
    try:
        # De uitslag verandert niet meer: één keer ophalen is genoeg.
        out['verkiezingen'] = oud.get('verkiezingen') or verkiezingen()
    except Exception as exc:
        out['fouten'].append(f'Verkiezingen: {exc}'[:300])
    try:
        out['cbs'] = cbs()
    except Exception as exc:
        out['fouten'].append(f'CBS: {exc}'[:300])
        if oud.get('cbs'):
            out['cbs'] = oud['cbs']
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
    for gid, g in out['gemeenten'].items():
        print(gid, {k: len(v) for k, v in g.items() if isinstance(v, list)})
    print('fouten:', out['fouten'])

if __name__ == '__main__':
    main()
