"""Gemeentemonitor: openbare publicaties van Medemblik, Koggenland en Opmeer.

Per gemeente staat in GEMEENTEN welke bronnen er zijn. Elke run:
  1. KOOP-bekendmakingen (laatste 30 dagen + archief maand voor maand)
  2. raadsportaal (iBabs): vergaderingen, documenten en overzichten (raadsvragen e.d.)
  3. nieuws (RSS of webpagina), collegebesluiten, losse pagina's
  4. documentcontrole: tekst van documenten vergelijken met de vorige versie
  5. per gemeente een databestand voor het dashboard (docs/data/<gemeente>.json)

Uitgangspunt: de monitor zegt eerlijk wat hij wel en niet volgt (zie 'note' per bron).
"""
import json, hashlib, re, datetime, urllib.parse, html as htmllib, email.utils, time
from pathlib import Path
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

NL = ZoneInfo('Europe/Amsterdam')

ROOT = Path(__file__).parent
DB = ROOT / 'data' / 'items.json'
DOCS = ROOT / 'docs'
TEXT_DIR = ROOT / 'data' / 'text'   # vorige tekstversie per document, nodig om te kunnen vergelijken
HEADERS = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}

# ---------------------------------------------------------------------------
# Configuratie per gemeente (bronnen gecontroleerd op 15 okt 2026)
# ---------------------------------------------------------------------------
GEMEENTEN = {
    'medemblik': {
        'naam': 'Medemblik',
        'koop': 'Medemblik',
        'ibabs': 'https://medemblik.bestuurlijkeinformatie.nl',
        'ibabs_types': {0: 'Gemeenteraad', 100063720: 'Raadscommissie', 1: 'Presidium', 11: 'Auditcommissie',
                        100099145: 'Informatiebijeenkomst', 100067792: 'Themabijeenkomst'},
        # Webpagina's waarvan de links worden verzameld.
        'pages': {
            'Nieuws': 'https://www.medemblik.nl/nieuws',
            'Collegebesluiten': 'https://www.medemblik.nl/raad-bestuur-en-organisatie/college-van-bw/collegebesluiten',
            'Openbare informatie': 'https://www.medemblik.nl/raad-bestuur-en-organisatie/klacht-bezwaar-en-informatieverzoek/openbare-informatie',
            'Raadsportaal': 'https://medemblik.bestuurlijkeinformatie.nl/',
        },
        'domains': ('https://www.medemblik.nl/', 'https://medemblik.bestuurlijkeinformatie.nl/'),
        'news_rss': 'https://www.medemblik.nl/nieuws.rss',  # geeft ook de publicatietijd
        'college_pdf_page': None,
        # Woonplaatsen volgens de BAG (PDOK), voor Google Nieuws.
        'plaatsen': ['Medemblik', 'Abbekerk', 'Andijk', 'Benningbroek', 'Hauwert', 'Lambertschaag', 'Midwoud',
                     'Nibbixwoud', 'Oostwoud', 'Opperdoes', 'Sijbekarspel', 'Twisk', 'Wervershoof', 'Wognum',
                     'Zwaagdijk-Oost', 'Zwaagdijk-West'],
        'notes': {
            'Nieuws': 'Alleen de eerste nieuwspagina (de 12 nieuwste berichten).',
            'Collegebesluiten': 'Alleen de besluiten op de huidige pagina; het archief met oudere besluiten niet.',
            'Openbare informatie': 'Alleen de links op deze pagina.',
            'Raadsportaal': 'Startpagina van het raadsportaal (vergaderingen en de nieuwste overzichtsitems).',
        },
        'not_followed': {},
    },
    'koggenland': {
        'naam': 'Koggenland',
        'koop': 'Koggenland',
        'ibabs': None,
        'ibabs_types': {},
        'pages': {
            'Woo-verzoeken': 'https://www.koggenland.nl/overzicht-woo-verzoeken',
        },
        'domains': ('https://www.koggenland.nl/', 'https://cuatro.sim-cdn.nl/koggenland/'),
        'news_rss': 'https://www.koggenland.nl/rss/content-list?type%5B%5D=news&sort_by=published_at&sort_order=DESC',
        'college_pdf_page': 'https://www.koggenland.nl/bestuursstukken-vergaderingen-college-bw',
        'plaatsen': ['Koggenland', 'Avenhorn', 'Berkhout', 'De Goorn', 'Hensbroek', 'Obdam', 'Oudendijk',
                     'Scharwoude', 'Spierdijk', 'Ursem', 'Zuidermeer'],
        'notes': {
            'Woo-verzoeken': 'Alleen de links op de overzichtspagina Woo-verzoeken.',
        },
        # Bronnen die bewust NIET gevolgd worden, met de reden. Staat zo op het dashboard.
        'not_followed': {
            'Raadsinformatie': 'raad.koggenland.nl (vergaderingen, raadsstukken, raadsvragen) zit achter een '
                               'beveiligingscontrole tegen geautomatiseerde bezoekers. De monitor omzeilt die niet; '
                               'raadsstukken van Koggenland worden dus niet gevolgd. Raadsbesluiten die in het '
                               'Gemeenteblad verschijnen, komen wel binnen via KOOP.',
        },
    },
    'opmeer': {
        'naam': 'Opmeer',
        'koop': 'Opmeer',
        'ibabs': 'https://opmeer.bestuurlijkeinformatie.nl',
        'ibabs_types': {100000025: 'Besluitvormende raadsvergadering', 100044942: 'Oordeelsvormende raadsvergadering',
                        100044935: 'Beeldvormende bijeenkomst', 100113337: 'Auditcommissie'},
        'pages': {},
        'domains': ('https://www.opmeer.nl/', 'https://opmeer.bestuurlijkeinformatie.nl/'),
        'news_rss': 'https://www.opmeer.nl/rss/content-list?type%5B%5D=news&sort_by=published_at&sort_order=DESC',
        'college_pdf_page': None,
        'plaatsen': ['Opmeer', 'Aartswoud', 'De Weere', 'Hoogwoud', 'Spanbroek'],
        'notes': {},
        'not_followed': {},
    },
}

# KOOP: vanaf deze datum halen we alle bekendmakingen op (maand voor maand).
KOOP_START = '2026-01-01'
KOOP_RECENT_DAYS = 30          # elke run alles van de laatste zoveel dagen opnieuw ophalen
KOOP_SOURCE = 'Officiele bekendmakingen (KOOP)'
MEETING_WINDOW_PAST = 60       # vergaderingen: dagen terug
MEETING_WINDOW_AHEAD = 45      # vergaderingen: dagen vooruit
MEETINGS_PER_RUN = 10          # vergaderpagina's per gemeente per run, om de site te ontzien
DOCS_SOURCE = 'Raadsstukken'
REPORT_ROWS_PER_RUN = 50       # raadsportaal-overzichten: nieuwste regels per run
DOCS_PER_RUN = 50              # documentcontrole: documenten per run (alle gemeenten samen)
DOC_TIME_BUDGET = 240          # documentcontrole stopt na zoveel seconden (workflow mag 8 minuten)
ATT_V = 2                      # versie van de vergelijking incl. bijlagen; ophogen = nieuwe nulmeting
MAX_ATTACHMENTS = 8            # bijlagen per raadsportaal-item
KEYWORDS_FILE = ROOT / 'trefwoorden.txt'
KEYWORD_FRESH_DAYS = 3         # trefwoordmelding alleen voor stukken die zo recent zijn gevonden of gewijzigd
GEOCODE_PER_RUN = 150          # adressen per run opzoeken bij PDOK
GEO_V = 1                      # ophogen = KOOP-archief opnieuw ophalen om coördinaten aan te vullen
MAX_DOC_BYTES = 15_000_000     # groter: alleen bestandskenmerken vergelijken
TEXT_CAP = 300_000             # maximaal aantal tekens tekst per document
MAX_CHANGES = 10               # zoveel wijzigingen per document bewaren
MAX_ITEMS = 10_000             # bovengrens voor items.json
# Google Nieuws ('In de media'): artikelen over de gemeente en haar kernen.
MEDIA_SOURCE = 'In de media'
MEDIA_WINDOW = 'when:3d'       # elke run de artikelen van de laatste 3 dagen
MEDIA_KEEP_DAYS = 60           # oudere media-items worden opgeruimd
MEDIA_CHUNK = 8                # plaatsnamen per zoekvraag (Google geeft max. 100 resultaten per vraag)
# Regionale media: daar telt ook een artikel waarin de plaats alleen in de tekst staat.
MEDIA_REGIONAAL = ('rodi', 'noordhollands dagblad', 'onswestfriesland', 'streekomroep', 'nh nieuws',
                   'nieuwsuitwestfriesland', '112westfriesland', 'westfriesland', 'west-friesland')
# Verzamelsites (dubbel) en de gemeente zelf (staat al in de kolom Nieuws).
MEDIA_OVERSLAAN = ('drimble', 'stadindex', 'gemeente medemblik', 'gemeente koggenland', 'gemeente opmeer')
# Plaatsnamen die ook een achternaam zijn of elders voorkomen. 'Masha Berkhout' telt niet, 'in Berkhout' wel.
MEDIA_DUBBELZINNIG = {'berkhout', 'twisk', 'opmeer', 'oudendijk', 'hauwert', 'ursem', 'scharwoude'}
# Deze namen komen ook elders veel voor (Noord-Scharwoude, Oudendijk bij Strijen, de achternaam Berkhout):
# ze worden apart gezocht en tellen alleen als ze in de kop staan.
MEDIA_ALLEEN_KOP = {'berkhout', 'twisk', 'oudendijk', 'hauwert', 'ursem', 'scharwoude'}
MEDIA_VOORZETSELS = {'in', 'uit', 'bij', 'te', 'naar', 'van', 'rond', 'om', 'op', 'door', 'voor', 'nabij', 'en',
                     'gemeente', 'dorp', 'kern', 'centrum', 'buiten', 'tussen', 'richting', 'over'}

# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------
def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')

def today():
    # Alleen de dag: zo verandert 'last_seen' maar één keer per dag en blijft de Git-historie klein.
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()

def TODAY_ISO():
    return datetime.date.today().isoformat()

def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def make_key(text):
    return hashlib.sha256(text.encode()).hexdigest()

MAANDEN = {'januari': 1, 'februari': 2, 'maart': 3, 'april': 4, 'mei': 5, 'juni': 6, 'juli': 7,
           'augustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12}

def parse_nl_date(text):
    """'Collegebesluiten 29 september 2026' -> '2026-09-29', anders None."""
    m = re.search(r'(\d{1,2})\s+([a-z]+)\s+(\d{4})', (text or '').casefold())
    if not m or m.group(2) not in MAANDEN:
        return None
    try:
        return datetime.date(int(m.group(3)), MAANDEN[m.group(2)], int(m.group(1))).isoformat()
    except ValueError:
        return None

def parse_dmy(text):
    """'15-10-2026' of 'Gemeenteraad 24-09-2026 B.4' -> de datum als '2026-10-15', anders None."""
    m = re.search(r'\b(\d{1,2})-(\d{1,2})-(\d{4})\b', text or '')
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None

def new_item(gid, title, url, source, **extra):
    now = utc()
    item = {'title': title, 'url': url, 'source': source, 'gemeente': gid, 'first_seen': now,
            'updated': now, 'last_change': None, 'hash': '', 'revisions': 1}
    item.update(extra)
    return item

def set_status(db, gid, source, **values):
    db['status'].setdefault(gid, {})[source] = {'checked': utc(), **values}

# ---------------------------------------------------------------------------
# KOOP (officiële bekendmakingen)
# ---------------------------------------------------------------------------
def koop_fetch(creator, date_filter):
    """Haal ALLE records op voor een gemeente en datumfilter, met paginering (max 1000 per verzoek).

    Geeft (records, totaal_volgens_koop). Gecontroleerd 15 okt 2026: het filter
    dt.available>=JJJJ-MM-DD werkt; zonder filter levert KOOP de records in willekeurige volgorde."""
    base = f'c.product-area=="officielepublicaties" AND dt.creator=="{creator}"'
    records, start, total = [], 1, None
    while True:
        params = {'operation': 'searchRetrieve', 'version': '2.0', 'query': base + ' AND ' + date_filter,
                  'maximumRecords': '1000', 'startRecord': str(start)}
        r = requests.get('https://repository.overheid.nl/sru', params=params, headers=HEADERS, timeout=90)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        if root.findall('.//{*}diagnostic'):
            raise ValueError('SRU diagnostic: ' + clean(' '.join(root.itertext()))[:250])
        if total is None:
            n = root.find('.//{*}numberOfRecords')
            total = int(n.text) if n is not None and n.text else 0
        batch = root.findall('.//{*}recordData')
        records += batch
        nxt = root.find('.//{*}nextRecordPosition')
        if not batch or nxt is None or not (nxt.text or '').strip().isdigit():
            break
        start = int(nxt.text)
        if start > 20000:
            raise ValueError('Paginering loopt uit de hand; gestopt bij 20000')
    return records, total

def koop_store(db, records, gid, creator):
    """Sla KOOP-records op. Geeft het aantal nieuwe items."""
    added = 0
    for record in records:
        def values(name):
            return [clean(e.text) for e in record.iter()
                    if e.tag.rsplit('}', 1)[-1] == name and e.text and clean(e.text)]
        first = lambda name: (values(name) or [None])[0]
        if not any(c.casefold() == creator.casefold() for c in values('creator')):
            continue
        title = first('title') or 'Publicatie zonder titel'
        pattern = r'(?:gmb|stcrt|bgr|prb|wsb)-\d{4}-\d+'
        m = next((re.search(pattern, x) for x in values('identifier') if re.search(pattern, x)), None)
        # Zelfde URL-opbouw als versie 3, zodat bestaande items dezelfde sleutel houden.
        url = ('https://zoek.officielebekendmakingen.nl/' + m.group() + '.html') if m else first('preferredUrl')
        if not url:
            continue
        key = make_key(KOOP_SOURCE + '|' + url)
        # Volgens de KOOP SRU-handleiding: dcterms:available = publicatie, dcterms:issued =
        # formele uitgifte, dcterms:date = aanmaak document.
        koop = {k: (v[:10] if v else None) for k, v in
                {'available': first('available'), 'issued': first('issued'), 'date': first('date')}.items()}
        if koop['available']:
            doc_date, label = koop['available'], 'publicatiedatum (KOOP)'
        elif koop['issued']:
            doc_date, label = koop['issued'], 'uitgiftedatum (KOOP)'
        elif koop['date']:
            doc_date, label = koop['date'], 'documentdatum (KOOP)'
        else:
            doc_date, label = None, None
        item = db['items'].get(key)
        if item is None:
            item = db['items'][key] = new_item(gid, title, url, KOOP_SOURCE)
            added += 1
        # Alleen een hoger versienummer telt als nieuwe versie (bijv. een rectificatie). Een nieuwe
        # wijzigingsdatum bij hetzelfde versienummer is beheer bij KOOP, zoals het na een tijd
        # weghalen van persoonsgegevens; dat is geen nieuws.
        version = f"{first('hasVersion') or '1'}|{first('modified') or ''}"
        old_nr = (item.get('koop_version') or '').split('|')[0]
        if old_nr and old_nr != version.split('|')[0]:
            record_change(item, 'Nieuwe versie bij KOOP', f"versie {old_nr} → {version.split('|')[0]} (bijv. een rectificatie)")
        item['koop_version'] = version
        # Kaartpunt dat KOOP zelf meelevert ('52.72 5.17' = breedte lengte).
        punt = first('locatiepunt')
        if punt and not item.get('geo'):
            try:
                lat, lon = (float(x) for x in punt.split()[:2])
                item.update(geo=[round(lat, 6), round(lon, 6)], geo_src='KOOP')
            except ValueError:
                pass
        types = [t for t in values('type') if '|' not in t]
        item.update(gemeente=gid, koop_dates=koop, doc_date=doc_date, doc_date_label=label,
                    publication_date=koop['available'] or koop['issued'], last_seen=today(),
                    koop_type=(types or values('type') or [None])[0], locatie=first('geometrielabel'),
                    publicatie=first('publicatienaam'),
                    excerpt=first('abstract') or ('Officiele bekendmaking; ' + (label + ': ' + doc_date if doc_date else 'datum onbekend')))
    return added

KOOP_TIMES_PER_RUN = 60

def koop_publication_times(db):
    """De officiële publicatietijd staat niet in de KOOP-gegevens, wel op de pagina zelf:
    'Datum publicatie ... 14-10-2026 09:00' (gecontroleerd 15 okt 2026). De tijden in de
    KOOP-gegevens (bijv. 09:17) zijn verwerkingstijden en worden daarom niet gebruikt.
    Alleen voor recente stukken (laatste 7 dagen), om de site te ontzien."""
    lo = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    todo = [v for v in db['items'].values() if v.get('source') == KOOP_SOURCE and not v.get('published_at')
            and not v.get('published_at_tried') and (v.get('doc_date') or '') >= lo]
    todo.sort(key=lambda v: v.get('doc_date') or '', reverse=True)
    found = 0
    for item in todo[:KOOP_TIMES_PER_RUN]:
        item['published_at_tried'] = True
        try:
            r = requests.get(item['url'], headers=HEADERS, timeout=20)
            r.raise_for_status()
            text = clean(BeautifulSoup(r.text, 'html.parser').get_text(' '))
            m = re.search(r'Datum publicatie.{0,200}?\b(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2})\b', text)
            if m:
                d, mo, y, h, mi = map(int, m.groups())
                item.update(published_at=datetime.datetime(y, mo, d, h, mi, tzinfo=NL).isoformat(timespec='minutes'),
                            published_at_source='officielebekendmakingen.nl')
                found += 1
        except Exception:
            pass
    return found

def collect_official(db, gid):
    """KOOP in twee delen:
    1. recent: elke run alles van de laatste KOOP_RECENT_DAYS dagen (vangt nieuwe stukken);
    2. archief: per run één kalendermaand vanaf KOOP_START, tot de huidige maand is bereikt.
    Per deel wordt gecontroleerd of het aantal opgehaalde records gelijk is aan het totaal dat
    KOOP opgeeft. KOOP noemt dat totaal zelf een schatting."""
    creator = GEMEENTEN[gid]['koop']
    st = db.setdefault('state', {}).setdefault('koop', {}).setdefault(gid, {})
    try:
        since = (datetime.date.today() - datetime.timedelta(days=KOOP_RECENT_DAYS)).isoformat()
        records, total = koop_fetch(creator, 'dt.available>=' + since)
        added = koop_store(db, records, gid, creator)
        note = f'Laatste {KOOP_RECENT_DAYS} dagen: {len(records)} van {total} opgehaald.'
        ok = len(records) >= total
        month = st.get('backfill_month', KOOP_START[:7])
        current = datetime.date.today().strftime('%Y-%m')
        if st.get('geo_v') != GEO_V:
            # Eenmalig het archief opnieuw doorlopen om de kaartpunten aan te vullen.
            st.update(geo_v=GEO_V, backfill_month=KOOP_START[:7])
            month = KOOP_START[:7]
        if month < current:
            y, mo = map(int, month.split('-'))
            nxt = f'{y + (mo == 12)}-{(mo % 12) + 1:02d}'
            recs, tot = koop_fetch(creator, f'dt.available>={month}-01 AND dt.available<{nxt}-01')
            added += koop_store(db, recs, gid, creator)
            if len(recs) >= tot:
                st['backfill_month'] = nxt
                note += f' Archief {month}: {len(recs)} van {tot} opgehaald.'
            else:
                ok = False
                note += f' Archief {month}: slechts {len(recs)} van {tot}; volgende run opnieuw.'
        done = st.get('backfill_month', KOOP_START[:7]) >= current
        cover = ('Volledig vanaf ' + KOOP_START) if done else \
            ('Archief bijgewerkt t/m ' + st.get('backfill_month', KOOP_START[:7]) + ' (nog bezig)')
        set_status(db, gid, KOOP_SOURCE, ok=ok, count=len(records), new=added,
                   note=note + ' Dekking: ' + cover + '. Ouder dan ' + KOOP_START + ' wordt niet opgehaald.')
    except Exception as exc:
        set_status(db, gid, KOOP_SOURCE, ok=False, error=str(exc)[:250])

# ---------------------------------------------------------------------------
# Medemblik: collegebesluiten als losse besluiten op één webpagina
# ---------------------------------------------------------------------------
def parse_college(main):
    """Splits de collegebesluitenpagina in besluiten: [{'date','title','body'}].
    h2 = vergaderdatum, h3 = besluit, h4 ('Samenvatting'/'Besluit') hoort bij de besluittekst."""
    from bs4 import NavigableString, Comment
    decisions, date, current = [], None, None
    for node in main.descendants:
        name = getattr(node, 'name', None)
        if name == 'h2':
            date = parse_nl_date(clean(node.get_text(' ', strip=True)))
            current = None  # h2 zonder datum (bijv. 'Oudere collegebesluiten') sluit het blok af
        elif name == 'h3':
            current = None
            if date:
                current = {'date': date, 'title': clean(node.get_text(' ', strip=True)), 'parts': []}
                decisions.append(current)
        elif isinstance(node, NavigableString) and not isinstance(node, Comment) and current is not None:
            if node.find_parent(['h2', 'h3']):
                continue
            text = clean(str(node))
            if text:
                current['parts'].append(text)
    for d in decisions:
        d['body'] = clean(' '.join(d.pop('parts')))[:8000]
    return [d for d in decisions if d['title'] and d['body']]

def collect_college(db, main, url, gid):
    source = 'Collegebesluiten'
    seen = {}
    for d in parse_college(main):
        # Unieke sleutel: vergaderdatum + besluittitel (+ volgnummer bij dubbele titel op dezelfde datum).
        # Sleutelopbouw ongewijzigd sinds fase 1, zodat de historie van Medemblik blijft kloppen.
        base = d['date'] + '|' + d['title'].casefold().rstrip(' .:')
        seen[base] = seen.get(base, 0) + 1
        ident = base + ('#' + str(seen[base]) if seen[base] > 1 else '')
        key = make_key(source + '|' + ident)
        status = re.findall(r'\b(Conform besloten|Aangepast besloten|Niet besloten|Aangehouden|Conform)\b', d['body'])
        item = db['items'].get(key)
        if item is None:
            item = db['items'][key] = new_item(gid, d['title'], url, source, kind='collegebesluit',
                                               meeting_date=d['date'], publication_date=None,
                                               besluit_status=status[-1] if status else None)
        # Alleen een revisie bij een aantoonbaar andere tekst van precies dit besluit, met per zin
        # wat er veranderde. De eerste keer is een nulmeting.
        compare_text(key, item, to_lines(d['body']), 'Besluittekst gewijzigd')
        item.update(hash=make_key(d['body']), excerpt=d['body'][:400],
                    besluit_status=status[-1] if status else item.get('besluit_status'),
                    doc_date=d['date'], doc_date_label='vergaderdatum college', last_seen=today())

# ---------------------------------------------------------------------------
# Koggenland: besluitenlijsten en agenda's van het college als pdf
# ---------------------------------------------------------------------------
def collect_college_pdfs(db, gid, page_url):
    source = 'Collegebesluiten'
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for t in soup(['script', 'style', 'nav', 'footer', 'header']):
            t.decompose()
        main = soup.select_one('main') or soup
        year, found, added = None, 0, 0
        # Door de pagina lopen: kopjes als 'Besluitenlijsten 2026' bepalen het jaar
        # (sommige bestandsnamen missen het jaartal, bijv. 'Besluitenlijst college 22 september').
        for node in main.find_all(['h2', 'h3', 'h4', 'a']):
            if node.name != 'a':
                m = re.search(r'(20\d\d)', node.get_text(' ', strip=True))
                if m:
                    year = m.group(1)
                continue
            href = urllib.parse.urljoin(page_url, node.get('href', ''))
            if '.pdf' not in href.lower():
                continue
            raw = clean(node.get_text(' ', strip=True))
            title = clean(re.sub(r'\(PDF[^)]*\)', '', raw).replace('.pdf', '').replace('_', ' '))
            title = title[:1].upper() + title[1:]
            low = title.casefold()
            kind = 'besluitenlijst' if 'besluitenlijst' in low else ('collegeagenda' if 'agenda' in low else 'collegestuk')
            date = parse_nl_date(title) or (parse_nl_date(title + ' ' + year) if year else None)
            # Sleutel zonder '?cb=...': dat deel verandert als het bestand opnieuw wordt geüpload.
            key = make_key(source + '|' + href.split('?')[0])
            item = db['items'].get(key)
            if item is None:
                item = db['items'][key] = new_item(gid, title, href, source, kind=kind)
                added += 1
            # Geen datum in de linktekst? Dan uit de opgeslagen titel of de bestandsnaam
            # ('agenda_collegevergadering_16_december_2025.pdf').
            date = date or parse_nl_date(item['title']) or parse_nl_date(
                urllib.parse.unquote(href.split('?')[0].rsplit('/', 1)[-1]).replace('_', ' ').replace('-', ' '))
            item.update(url=href, file_url=href, doc_date=date, doc_date_label='vergaderdatum college',
                        last_seen=today(),
                        excerpt=('Besluitenlijst' if kind == 'besluitenlijst' else 'Agenda') + ' van het college van B&W (pdf)')
            found += 1
        set_status(db, gid, source, ok=found > 0, count=found, new=added,
                   note='Besluitenlijsten en agenda’s van het college (pdf) op de gemeentesite; '
                        'de inhoud van de pdf’s wordt per zin gevolgd.',
                   error=None if found else 'Geen pdf-links gevonden; paginastructuur gewijzigd?')
    except Exception as exc:
        set_status(db, gid, source, ok=False, error=str(exc)[:250])

# ---------------------------------------------------------------------------
# Nieuws via RSS (Koggenland, Opmeer)
# ---------------------------------------------------------------------------
def collect_news_rss(db, gid, feed_url):
    source = 'Nieuws'
    try:
        r = requests.get(feed_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items, added = root.findall('.//item'), 0
        for it in items:
            title = clean(it.findtext('title'))
            link = clean(it.findtext('link'))
            if not title or not link:
                continue
            date = published = None
            if it.findtext('pubDate'):
                try:
                    dt = email.utils.parsedate_to_datetime(clean(it.findtext('pubDate'))).astimezone(NL)
                    date, published = dt.date().isoformat(), dt.isoformat(timespec='minutes')
                except (TypeError, ValueError):
                    pass
            key = make_key(source + '|' + link)
            item = db['items'].get(key)
            if item is None:
                item = db['items'][key] = new_item(gid, title, link, source)
                added += 1
            item.update(doc_date=date, doc_date_label='publicatiedatum', publication_date=date, last_seen=today())
            if published:
                item.update(published_at=published, published_at_source='RSS-feed')
            if clean(it.findtext('description')):
                item['excerpt'] = clean(it.findtext('description'))[:400]
        set_status(db, gid, source, ok=bool(items), count=len(items), new=added,
                   note=f'RSS-feed van de gemeentesite: de {len(items)} nieuwste berichten. Oudere berichten niet.')
    except Exception as exc:
        set_status(db, gid, source, ok=False, error=str(exc)[:250])

# ---------------------------------------------------------------------------
# In de media (Google Nieuws)
# ---------------------------------------------------------------------------
def media_plaats(title, places):
    """Staat een plaats van de gemeente in de titel? Geeft 'ja', 'achternaam' of None.
    Een dubbelzinnige naam direct na een woord met hoofdletter ('Masha Berkhout') is een achternaam;
    'Noord-Scharwoude' telt niet (koppelteken ervoor)."""
    surname = False
    for place in places:
        # Geen koppelteken ervóór (Noord-Scharwoude), wel erna (Hoogwoud-Oost).
        for m in re.finditer(r'(?<![\w-])' + re.escape(place) + r'(?!\w)', title, re.I):
            if place.casefold() not in MEDIA_DUBBELZINNIG:
                return 'ja'
            prev = re.search(r'(\S+)\s+$', title[:m.start()])
            word = prev.group(1).strip('‘’\'"(:,') if prev else ''
            if word and word[0].isupper() and word.casefold() not in MEDIA_VOORZETSELS:
                surname = True
                continue
            return 'ja'
    return 'achternaam' if surname else None

def collect_media(db, gid, places):
    """Google Nieuws-zoekfeed met alle kernen van de gemeente. Een artikel komt erin als een kern in de
    titel staat, of als een regionaal medium de kern in de tekst noemt."""
    state = db.setdefault('state', {}).setdefault('media', {})
    now = datetime.datetime.now(datetime.timezone.utc)
    if state.get('pause_until', '') > now.isoformat():
        set_status(db, gid, MEDIA_SOURCE, ok=True, note='Google Nieuws even overgeslagen (te veel verzoeken); straks weer.')
        return
    seen = kept = added = 0
    gewoon = [p for p in places if p.casefold() not in MEDIA_ALLEEN_KOP]
    streng = [p for p in places if p.casefold() in MEDIA_ALLEEN_KOP]
    groepen = [(gewoon[i:i + MEDIA_CHUNK], False) for i in range(0, len(gewoon), MEDIA_CHUNK)]
    groepen += [(streng[i:i + MEDIA_CHUNK], True) for i in range(0, len(streng), MEDIA_CHUNK)]
    try:
        for groep, alleen_kop in groepen:
            terms = ' OR '.join(f'"{p}"' if re.search(r'[\s-]', p) else p for p in groep)
            url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode(
                {'q': f'{terms} {MEDIA_WINDOW}', 'hl': 'nl', 'gl': 'NL', 'ceid': 'NL:nl'})
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code in (429, 503):
                state['pause_until'] = (now + datetime.timedelta(hours=2)).isoformat(timespec='seconds')
                raise RuntimeError(f'Google Nieuws gaf HTTP {r.status_code}; 2 uur pauze')
            r.raise_for_status()
            for it in ET.fromstring(r.content).findall('./channel/item'):
                seen += 1
                bron = clean(it.findtext('source'))
                title = clean(it.findtext('title'))
                link = clean(it.findtext('link'))
                if not title or not link or any(w in bron.casefold() for w in MEDIA_OVERSLAAN):
                    continue
                if bron and title.endswith(' - ' + bron):
                    title = title[:-len(bron) - 3].strip()
                hit = media_plaats(title, places)
                regionaal = any(w in bron.casefold() for w in MEDIA_REGIONAAL)
                if hit != 'ja' and not (hit is None and regionaal and not alleen_kop):
                    continue
                key = make_key(f"{MEDIA_SOURCE}|{gid}|{clean(it.findtext('guid')) or link}")
                item = db['items'].get(key)
                if item is None:
                    item = db['items'][key] = new_item(gid, title, link, MEDIA_SOURCE, kind='media')
                    added += 1
                kept += 1
                # 'tekst': de plaats staat niet in de kop maar wel in het artikel (regionaal medium).
                item.update(title=title, media_bron=bron, media_match='kop' if hit == 'ja' else 'tekst', last_seen=today())
                try:
                    dt = email.utils.parsedate_to_datetime(clean(it.findtext('pubDate'))).astimezone(NL)
                    item.update(doc_date=dt.date().isoformat(), doc_date_label='publicatiedatum',
                                published_at=dt.isoformat(timespec='minutes'), published_at_source='Google Nieuws')
                except (TypeError, ValueError):
                    pass
            time.sleep(1)
        set_status(db, gid, MEDIA_SOURCE, ok=True, count=kept, new=added,
                   note=f'Google Nieuws, artikelen van de laatste 3 dagen over {", ".join(places)}. '
                        'Telt mee als de plaats in de kop staat, of als een regionaal medium hem in de tekst noemt.')
    except Exception as exc:
        set_status(db, gid, MEDIA_SOURCE, ok=False, error=str(exc)[:250])
    # Opruimen: media-items ouder dan MEDIA_KEEP_DAYS.
    grens = (datetime.date.today() - datetime.timedelta(days=MEDIA_KEEP_DAYS)).isoformat()
    for k in [k for k, v in db['items'].items() if v.get('gemeente') == gid and v.get('source') == MEDIA_SOURCE
              and (v.get('doc_date') or v['first_seen'][:10]) < grens]:
        del db['items'][k]

# ---------------------------------------------------------------------------
# Losse webpagina's: links verzamelen
# ---------------------------------------------------------------------------
def is_navigation(title, href):
    """Menuknoppen van het raadsportaal ('Bekijk kalender', 'Bekijk overzichten') zijn geen publicaties."""
    path = urllib.parse.urlparse(href).path.rstrip('/').casefold()
    return title.casefold().startswith('bekijk ') or path in ('/calendar', '/reports', '/agenda')

def news_title_date(item):
    """Medemblik-nieuwslinks heten bijv. 'Eerste paal geslagen Datum vrijdag 25 september 2026'.
    Haal de datum uit de titel en maak de titel schoon."""
    if item.get('source') != 'Nieuws':
        return
    m = re.search(r'\s+Datum\s+(?:[A-Za-z]+dag\s+)?(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*$', item['title'])
    if not m or not parse_nl_date(m.group(1)):
        return
    item['title'] = item['title'][:m.start()].strip()
    if not item.get('doc_date'):
        item['doc_date'], item['doc_date_label'] = parse_nl_date(m.group(1)), 'publicatiedatum'
        item['publication_date'] = item['doc_date']

def collect_pages(db, gid):
    cfg = GEMEENTEN[gid]
    for source, url in cfg['pages'].items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            for t in soup(['script', 'style', 'nav', 'footer', 'header', 'form']):
                t.decompose()
            main = soup.select_one('main') or soup.select_one('article') or soup
            candidates = []
            for a in main.select('a[href]'):
                title = clean(a.get_text(' ', strip=True))
                href = urllib.parse.urljoin(url, a['href'])
                if len(title) < 12 or len(title) > 240 or not href.startswith('https://'):
                    continue
                if not href.startswith(cfg['domains']):
                    continue
                if href.rstrip('/') == url.rstrip('/') or is_navigation(title, href):
                    continue
                candidates.append((title, href))
            if gid == 'medemblik' and source == 'Collegebesluiten':
                collect_college(db, main, url, gid)
            for title, href in candidates:
                key = make_key(source + '|' + href)
                if key not in db['items']:
                    db['items'][key] = new_item(gid, title, href, source, excerpt='')
                    if '/Agenda/Index/' in href and parse_nl_date(title):
                        db['items'][key].update(doc_date=parse_nl_date(title), doc_date_label='vergaderdatum')
                news_title_date(db['items'][key])
                db['items'][key]['last_seen'] = today()
            set_status(db, gid, source, ok=True, count=len(candidates), note=cfg['notes'].get(source))
        except Exception as exc:
            set_status(db, gid, source, ok=False, error=str(exc)[:180])

# ---------------------------------------------------------------------------
# Raadsportaal (iBabs): vergaderingen en hun documenten
# ---------------------------------------------------------------------------
def ibabs_list_meetings(db, gid):
    """Eén keer per dag per gemeente: de jaarlijst per vergadertype ophalen."""
    cfg = GEMEENTEN[gid]
    state = db.setdefault('state', {})
    meetings = state.setdefault('meetings', {})
    listed = state.setdefault('meetings_listed', {})
    # Elk half uur de vergaderlijst opnieuw ophalen (was: één keer per dag). Een vergadering die het college
    # of de griffie later op de dag plaatst, komt zo binnen een half uur binnen in plaats van de dag erna.
    vorige = listed.get(gid) or ''
    if len(vorige) > 10 and (datetime.datetime.now(datetime.timezone.utc)
                             - datetime.datetime.fromisoformat(vorige)).total_seconds() < 25 * 60:
        return []
    years = {datetime.date.today().year}
    if datetime.date.today().month <= 2:
        years.add(datetime.date.today().year - 1)
    errors = []
    for type_id, type_name in cfg['ibabs_types'].items():
        for year in sorted(years):
            try:
                r = requests.get(cfg['ibabs'] + '/Agenda/RetrieveAgendasForYear',
                                 params={'agendatypeId': type_id, 'year': year}, headers=HEADERS, timeout=30)
                r.raise_for_status()
                for a in BeautifulSoup(r.text, 'html.parser').select('a[href*="/Agenda/Index/"]'):
                    mid = a['href'].rstrip('/').rsplit('/', 1)[-1]
                    label = clean(a.get_text(' ', strip=True))
                    date = parse_nl_date(label)
                    if not date:
                        continue
                    m = meetings.setdefault(mid, {'checked': ''})
                    m.update(gemeente=gid, type=type_name, date=date, label=label)
            except Exception as exc:
                errors.append(f'{type_name} {year}: {str(exc)[:60]}')
    listed[gid] = utc()
    return errors

def ibabs_parse_meeting(page_html, base):
    """Geeft [(titel, url, agendapunt)] voor alle documenten op een vergaderpagina."""
    page = BeautifulSoup(page_html, 'html.parser')
    docs, seen = [], set()
    for a in page.select('a[href*="/Agenda/Document/"], a[href*="/Document/View/"]'):
        href = urllib.parse.urljoin(base, a['href'])
        if href in seen:
            continue
        seen.add(href)
        for badge in a.select('.badge'):
            badge.extract()
        title = clean(a.get_text(' ', strip=True))
        container = a.find_parent('div', class_='agenda-item')
        punt = None
        if container:
            pid = container.select_one('.panel-id')
            lab = container.select_one('.panel-title-label')
            punt = clean(((pid.get_text(strip=True) + ' ') if pid else '') + (lab.get_text(' ', strip=True) if lab else ''))
            punt = re.sub(r'\s*-\s*\d{1,2}:\d{2}$', '', punt) or None
        if title:
            docs.append((title, href, punt))
    return docs

def ibabs_agenda_points(page_html):
    """Alle agendapunten van een vergaderpagina, ook punten zonder documenten: ['5.1 Belastingverordeningen ...']."""
    page = BeautifulSoup(page_html, 'html.parser')
    out = []
    for div in page.select('div.agenda-item'):
        pid = div.select_one('.panel-id')
        lab = div.select_one('.panel-title-label')
        punt = clean(((pid.get_text(strip=True) + ' ') if pid else '') + (lab.get_text(' ', strip=True) if lab else ''))
        punt = re.sub(r'\s*-\s*\d{1,2}:\d{2}$', '', punt)
        if punt and punt not in out:
            out.append(punt)
    return out

def agenda_key(punt):
    """Agendapunt zonder nummer, zodat hernummeren (5.1 -> 5.2) geen wijziging is."""
    return re.sub(r'^\s*[0-9]+[a-z]?(?:\.[0-9]+[a-z]?)*\.?\s*', '', punt, flags=re.I).casefold()

def check_agenda(mitem, m, points):
    """Vergelijk de agenda met de vorige keer: gepubliceerd, punten erbij of eraf."""
    vorige = m.get('agenda')
    m['agenda'] = points
    if vorige is None:
        return  # eerste keer gezien: nulmeting
    if not vorige and points:
        record_change(mitem, 'Agenda gepubliceerd', f'agenda online met {len(points)} punten', added=points[:3])
        return
    oud, nieuw = {agenda_key(p): p for p in vorige}, {agenda_key(p): p for p in points}
    erbij = [nieuw[k] for k in nieuw if k not in oud]
    eraf = [oud[k] for k in oud if k not in nieuw]
    if erbij or eraf:
        delen = ([f'{len(erbij)} punt(en) erbij'] if erbij else []) + ([f'{len(eraf)} punt(en) eraf'] if eraf else [])
        record_change(mitem, 'Agenda gewijzigd', ', '.join(delen), added=erbij, removed=eraf)

def doc_id_from(url):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return (q.get('documentId') or [url.rstrip('/').rsplit('/', 1)[-1]])[0]

def collect_meetings(db, gid):
    cfg = GEMEENTEN[gid]
    base = cfg['ibabs']
    now = utc()
    meetings = db.setdefault('state', {}).setdefault('meetings', {})
    try:
        errors = ibabs_list_meetings(db, gid)
        lo = (datetime.date.today() - datetime.timedelta(days=MEETING_WINDOW_PAST)).isoformat()
        hi = (datetime.date.today() + datetime.timedelta(days=MEETING_WINDOW_AHEAD)).isoformat()
        window = [(mid, m) for mid, m in meetings.items() if m.get('gemeente') == gid and lo <= m['date'] <= hi]
        # Komende drie weken vaker controleren (agenda's en stukken verschijnen dan): die eerst,
        # daarna wie het langst niet is bekeken.
        soon = (datetime.date.today() + datetime.timedelta(days=21)).isoformat()
        recent = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=25)).isoformat(timespec='seconds')
        window.sort(key=lambda p: (not (TODAY_ISO() <= p[1]['date'] <= soon and p[1].get('checked', '') < recent),
                                   p[1].get('checked', '')))
        added = fetched = 0
        for mid, m in window[:MEETINGS_PER_RUN]:
            url = base + '/Agenda/Index/' + mid
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                r.raise_for_status()
            except Exception as exc:
                errors.append(f'{m["type"]} {m["date"]}: {str(exc)[:60]}')
                m['checked'] = now
                continue
            fetched += 1
            m['checked'] = now
            meeting_title = f'{m["type"]} {m["label"]}'
            # De vergadering zelf (zelfde sleutel als de links van de startpagina).
            mkey = make_key('Raadsportaal|' + url)
            mitem = db['items'].setdefault(mkey, new_item(gid, meeting_title, url, 'Raadsportaal', excerpt=''))
            mitem.update(gemeente=gid, kind='vergadering', doc_date=m['date'], doc_date_label='vergaderdatum',
                         last_seen=today())
            docs = ibabs_parse_meeting(r.text, base)
            m['documents'] = len(docs)
            check_agenda(mitem, m, ibabs_agenda_points(r.text))
            for title, href, punt in docs:
                doc_id = doc_id_from(href)
                key = make_key(DOCS_SOURCE + '|' + doc_id)
                item = db['items'].get(key)
                if item is None:
                    item = db['items'][key] = new_item(gid, title, href, DOCS_SOURCE, kind='raadsdocument')
                    added += 1
                # Eén document kan in meerdere vergaderingen staan (eerst commissie, dan raad).
                # Bewaar ze allemaal; datum en hoofdvergadering = de vroegste.
                seen_in = item.setdefault('meetings', [])
                entry = {'date': m['date'], 'meeting': meeting_title, 'agendapunt': punt}
                if entry not in seen_in:
                    seen_in.append(entry)
                    seen_in.sort(key=lambda e: e['date'])
                eerste = seen_in[0]
                # De link in de lijst opent een viewerpagina; het bestand zelf staat op
                # /Document/View/<documentId> (gecontroleerd 15 okt 2026).
                item['file_url'] = base + '/Document/View/' + doc_id
                item.update(gemeente=gid, doc_date=eerste['date'], doc_date_label='vergaderdatum',
                            meeting_title=eerste['meeting'], agendapunt=eerste['agendapunt'], last_seen=today(),
                            excerpt=eerste['meeting'] + (' · agendapunt ' + eerste['agendapunt'] if eerste['agendapunt'] else ' · vergaderdocumenten')
                            + (f' · ook in {len(seen_in) - 1} andere vergadering(en)' if len(seen_in) > 1 else ''))
        total_docs = sum(1 for v in db['items'].values() if v.get('kind') == 'raadsdocument' and v.get('gemeente') == gid)
        set_status(db, gid, DOCS_SOURCE, ok=not errors, count=fetched, new=added,
                   error='; '.join(errors)[:250] if errors else None,
                   note=f'{fetched} van {len(window)} vergaderingen in venster bijgewerkt; {total_docs} documenten bekend. '
                        f'Dekking: vergaderingen van {lo} t/m {hi} ({", ".join(cfg["ibabs_types"].values())}). Oudere vergaderingen niet.')
    except Exception as exc:
        set_status(db, gid, DOCS_SOURCE, ok=False, error=str(exc)[:250])

# ---------------------------------------------------------------------------
# Raadsportaal (iBabs): overzichten (raadsvragen, informatienota's, moties, besluitenlijsten ...)
# ---------------------------------------------------------------------------
REPORTS_VERSION = 4  # verhogen als de manier van ophalen verandert: dan opnieuw lijst + volledige ronde

def ibabs_report_list(db, gid):
    """Eén keer per dag: welke overzichten zijn er, welke kolommen en welke sortering.
    De sortering (data-order) is dezelfde die de website zelf gebruikt; niet elk overzicht
    sorteert op de eerste kolom (gecontroleerd 15 okt 2026)."""
    base = GEMEENTEN[gid]['ibabs']
    state = db.setdefault('state', {}).setdefault('reports', {}).setdefault(gid, {})
    if state.get('listed') == today() and state.get('reports') and state.get('v') == REPORTS_VERSION:
        return state['reports']
    r = requests.get(base + '/Reports', headers=HEADERS, timeout=30)
    r.raise_for_status()
    reports = {}
    for a in BeautifulSoup(r.text, 'html.parser').select('a[href*="/Reports/Details/"]'):
        rid = a['href'].rstrip('/').rsplit('/', 1)[-1]
        name = clean(a.get_text(' ', strip=True))
        if name and rid not in reports:
            reports[rid] = {'name': name}
    for rid, rep in reports.items():
        page = requests.get(f'{base}/Reports/Details/{rid}', headers=HEADERS, timeout=30)
        m = re.search(r"data-columns='([^']+)'", page.text)
        rep['columns'] = json.loads(htmllib.unescape(m.group(1))) if m else []
        o = re.search(r"data-order='([^']+)'", page.text)
        order = json.loads(htmllib.unescape(o.group(1))) if o else [[0, 'desc']]
        rep['order_col'] = int(order[0][0]) if order and order[0] else 0
    if state.get('v') != REPORTS_VERSION:
        state.pop('full_pass', None)  # nieuwe ophaalmethode: vandaag opnieuw een volledige ronde
    state.update(listed=today(), reports=reports, v=REPORTS_VERSION)
    return reports

def ibabs_report_rows(base, rid, columns, order_col, start, length):
    """Vraagt een pagina regels op via dezelfde tabelaanvraag die de website zelf doet
    (POST /Reports/GetReportData/<id>, gecontroleerd 15 okt 2026). Nieuwste eerst."""
    data = {'draw': '1', 'start': str(start), 'length': str(length), 'order[0][column]': str(order_col),
            'order[0][dir]': 'desc', 'search[value]': '', 'search[regex]': 'false'}
    for i, c in enumerate(columns):
        data.update({f'columns[{i}][data]': c['data'], f'columns[{i}][name]': c.get('name', c['data']),
                     f'columns[{i}][searchable]': 'true', f'columns[{i}][orderable]': 'true',
                     f'columns[{i}][search][value]': '', f'columns[{i}][search][regex]': 'false'})
    r = requests.post(f'{base}/Reports/GetReportData/{rid}', data=data, headers={**HEADERS,
                      'X-Requested-With': 'XMLHttpRequest', 'Referer': f'{base}/Reports/Details/{rid}'}, timeout=40)
    r.raise_for_status()
    body = r.json()
    return body.get('data', []), body.get('recordsTotal', 0)

def report_date(row, date_col, report_name):
    """Datum van een overzichtsregel + wat die datum betekent.
    Soms is de 'datum' een vergaderverwijzing, bijv. 'Gemeenteraad 24-09-2026 B.4. Ruimtelijk voorstel'."""
    raw = clean(row.get(date_col) or '')
    date = parse_dmy(raw)
    if not date:
        return None, None, None
    if re.match(r'\s*\d{1,2}-\d{1,2}-\d{4}\s*$', raw):
        if date_col == 'datum' and 'vragen' in report_name.casefold():
            return date, 'datum vraag', None
        if date_col in ('datum', 'datumingekomen'):
            return date, 'datum ingekomen' if 'ingekomen' in report_name.casefold() or date_col == 'datumingekomen' else 'datum', None
        return date, 'registratiedatum', None
    return date, 'vergaderdatum', raw  # tekst met vergadering en agendapunt

def volg_uitkomst(item, row, rapport):
    """Moties, amendementen en toezeggingen: status (aangenomen/verworpen), indieners, afgedaan en stand van zaken.
    Een verandering ten opzichte van de vorige keer wordt een wijziging (en een melding)."""
    r = rapport.casefold()
    if not any(w in r for w in ('motie', 'amendement', 'toezegging')):
        return
    status = clean(row.get('status') or '')
    if status:
        oud = item.get('motie_status')
        if oud and oud != status:
            record_change(item, 'Uitkomst', f'{oud} → {status}')
        item['motie_status'] = status
    indieners = [clean(x) for x in re.split(r'\n', '\n'.join(str(row.get(k) or '') for k in
                 ('hoofdindiener', 'medeindiener', 'raadsleden', 'Fracties', 'fractie'))) if clean(x)]
    if indieners:
        # 'Beerepoot, T. (Tom) (VVD)' -> 'VVD'; fracties blijven zoals ze zijn.
        partijen = list(dict.fromkeys((re.findall(r'\(([^()]+)\)\s*$', x) or [x])[-1] for x in indieners))
        item['indieners'] = ', '.join(partijen)[:120]
    for veld in ('completed', 'afgedaan'):
        if veld in row and row.get(veld) in ('Ja', 'Nee'):
            nu = row[veld] == 'Ja'
            if item.get('afgedaan') is False and nu:
                record_change(item, 'Afgedaan', ('toezegging' if 'toezegging' in r else 'motie') + ' is afgedaan',
                              added=[clean(row.get('standvanzaken') or '')[:220]] if row.get('standvanzaken') else ())
            item['afgedaan'] = nu
    stand = clean(row.get('standvanzaken') or '')
    if stand:
        if item.get('stand') and item['stand'] != stand[:400]:
            record_change(item, 'Stand van zaken', 'stand van zaken bijgewerkt', added=[stand[:220]], removed=[item['stand'][:220]])
        item['stand'] = stand[:400]

def collect_ibabs_reports(db, gid):
    base = GEMEENTEN[gid]['ibabs']
    source_name = 'Raadsportaal-overzichten'
    try:
        reports = ibabs_report_list(db, gid)
        rstate = db['state']['reports'][gid]
        full = rstate.get('full_pass') != today()  # één keer per dag dieper terug, tot KOOP_START
        pass_id = utc()  # kenmerk van deze ronde: wat een volledige ronde niet meer ziet, gaat naar het archief
        added = rows_seen = 0
        errors, summary = [], []
        for rid, rep in reports.items():
            cols = rep.get('columns') or []
            if not cols:
                continue
            # Sorteren zoals de website (vaak op ID-nummer, nieuwste eerst); de datum staat in een eigen kolom.
            order_col = min(rep.get('order_col', 0), len(cols) - 1)
            names = [c['data'] for c in cols]
            date_col = next((n for n in ('datum', 'datumingekomen', 'registrationdate') if n in names), names[order_col])
            is_besluitenlijst = 'besluitenlijst' in rep['name'].casefold()
            try:
                start, total, in_range = 0, None, 0
                while True:
                    rows, total = ibabs_report_rows(base, rid, cols, order_col, start,
                                                    200 if full else REPORT_ROWS_PER_RUN)
                    old_on_page = 0
                    for row in rows:
                        rows_seen += 1
                        rowid, title = row.get('DT_RowId'), clean(row.get('title'))
                        if not rowid or not title:
                            continue
                        date, label, meeting = report_date(row, date_col, rep['name'])
                        if date and date < KOOP_START:
                            old_on_page += 1  # buiten bereik: niet bewaren
                            continue
                        in_range += 1
                        url = f'{base}/Reports/Item/{rowid}'
                        key = make_key('Raadsportaal|' + url)  # zelfde sleutel als links van de startpagina
                        item = db['items'].get(key)
                        if item is None:
                            item = db['items'][key] = new_item(gid, title, url, 'Raadsportaal', excerpt='')
                            added += 1
                        item.update(gemeente=gid, kind='overzichtsitem', rapport=rep['name'], last_seen=today())
                        if full:
                            item['report_pass'] = pass_id
                        if is_besluitenlijst:
                            # Besluitenlijsten van het college: datum van de collegevergadering uit de titel.
                            item['source'] = 'Collegebesluiten'
                            vergader = parse_nl_date(title)
                            item.update(doc_date=vergader or date,
                                        doc_date_label='vergaderdatum college' if vergader else (label or 'datum'))
                        elif date:
                            item.update(doc_date=date, doc_date_label=label)
                        if meeting:
                            item['meeting_title'] = meeting
                        for poho_field in ('poho', 'portefeuillehouder'):
                            if row.get(poho_field):
                                item['portefeuillehouder'] = clean(re.sub(r'<[^>]+>', ' ', str(row[poho_field])))
                        if 'datumantwoord' in row:
                            antwoord = parse_dmy(row.get('datumantwoord') or '')
                            # Alleen melden als de monitor deze vraag eerder al zónder antwoord zag.
                            if antwoord and item.get('antwoord_datum') != antwoord and item.get('report_seen') \
                                    and not item.get('antwoord_datum'):
                                record_change(item, 'Beantwoord', f'datum antwoord: {antwoord}')
                            if antwoord:
                                item['antwoord_datum'] = antwoord
                        volg_uitkomst(item, row, rep['name'])
                        item['report_seen'] = True
                        item['excerpt'] = rep['name'] + (f' · antwoord {item["antwoord_datum"]}' if item.get('antwoord_datum')
                                                         else (' · nog niet beantwoord' if 'datumantwoord' in row else '')) \
                            + (f' · {item["motie_status"]}' if item.get('motie_status') else '') \
                            + (f' · {item["indieners"]}' if item.get('indieners') else '') \
                            + ((' · afgedaan' if item['afgedaan'] else ' · nog open') if 'afgedaan' in item else '')
                    start += len(rows)
                    # Stoppen zodra een hele pagina buiten bereik valt (nieuwste staan bovenaan).
                    reached_old = bool(rows) and old_on_page == len(rows)
                    if not full or reached_old or not rows or start >= (total or 0) or start >= 3000:
                        break
                summary.append(f'{rep["name"]} {in_range if full else total}')
            except Exception as exc:
                errors.append(f'{rep["name"]}: {str(exc)[:60]}')
        if full and not errors:
            rstate['full_pass'] = today()
            # Wat in een volledige ronde niet (meer) binnen het bereik viel, gaat naar het archief.
            archive = db.setdefault('archief', {})
            for key, item in list(db['items'].items()):
                if item.get('gemeente') == gid and item.get('kind') == 'overzichtsitem' and item.get('report_pass') != pass_id:
                    item.update(archived=utc(), archived_reason=f'Overzichtsitem buiten bereik (ouder dan {KOOP_START})')
                    archive[key] = db['items'].pop(key)
        set_status(db, gid, source_name, ok=not errors, count=rows_seen, new=added,
                   error='; '.join(errors)[:250] if errors else None,
                   note=('Alle overzichten van het raadsportaal vanaf ' + KOOP_START + ' (' + ', '.join(summary) + '). '
                         if full else 'Overzichten van het raadsportaal (totaal in het portaal: ' + ', '.join(summary) + '). ')
                        + f'Elke run de {REPORT_ROWS_PER_RUN} nieuwste per overzicht; één keer per dag alles vanaf {KOOP_START}. '
                        'Beantwoorde raadsvragen worden als wijziging gemeld. Bijlagen zelf worden (nog) niet inhoudelijk gevolgd.')
    except Exception as exc:
        set_status(db, gid, source_name, ok=False, error=str(exc)[:250])

# ---------------------------------------------------------------------------
# Documentwijzigingen inhoudelijk volgen
# ---------------------------------------------------------------------------
def check_interval(item):
    """Hoe vaak een document opnieuw wordt gecontroleerd, op basis van de leeftijd van het stuk.
    Verse stukken worden vaker aangepast (bijlage vervangen, tekst gecorrigeerd)."""
    ref = item.get('doc_date') or (item.get('first_seen') or '')[:10]
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(ref)).days
    except ValueError:
        age = 0
    if age <= 14:
        return datetime.timedelta(hours=6)
    if age <= 60:
        return datetime.timedelta(days=1)
    if age <= 180:
        return datetime.timedelta(days=7)
    return datetime.timedelta(days=30)

def is_due(item, now_dt):
    if '/Reports/Item/' in item.get('url', '') and item.get('text_v') != ATT_V:
        return True  # nog geen nulmeting inclusief bijlagen
    last = item.get('content_checked')
    if not last:
        return True
    try:
        return datetime.datetime.fromisoformat(last) + check_interval(item) <= now_dt
    except ValueError:
        return True

def to_lines(text):
    """Tekst in zinnen/regels knippen, zodat een wijziging per zin te tonen is."""
    text = (text or '')[:TEXT_CAP]
    parts = re.split(r'\n+|(?<=[.!?;])\s+(?=[A-Z0-9“"(])', text)
    return [clean(p) for p in parts if clean(p)]

def pdf_text(data):
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out = []
    for page in reader.pages[:300]:
        try:
            out.append(page.extract_text() or '')
        except Exception:
            out.append('')
    return '\n'.join(out)

def text_path(key):
    return TEXT_DIR / (key[:24] + '.txt')

def record_change(item, kind, summary, added=(), removed=()):
    now = utc()
    change = {'at': now, 'type': kind, 'summary': summary,
              'added': [a[:220] for a in list(added)[:3]], 'removed': [r[:220] for r in list(removed)[:3]]}
    item.setdefault('changes', []).append(change)
    item['changes'] = item['changes'][-MAX_CHANGES:]
    item.update(updated=now, last_change=now, revisions=item.get('revisions', 1) + 1, change_type=kind)

def compare_text(key, item, lines, kind='Tekst gewijzigd', baseline=False, summary=None):
    """Vergelijk met de vorige tekstversie. De eerste keer (of met baseline=True) is alleen een nulmeting."""
    import difflib
    digest = hashlib.sha256('\n'.join(lines).encode()).hexdigest()
    path = text_path(key)
    previous = item.get('text_hash')
    if previous and previous != digest and not baseline:
        old = path.read_text(encoding='utf-8').split('\n') if path.exists() else []
        sm = difflib.SequenceMatcher(None, old, lines, autojunk=False)
        added = [l for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ('insert', 'replace') for l in lines[j1:j2]]
        removed = [l for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ('delete', 'replace') for l in old[i1:i2]]
        counts = 'tekst gewijzigd (vorige versie niet bewaard)' if not old else \
            f'{len(added)} zin(nen) toegevoegd of aangepast, {len(removed)} verwijderd of vervangen'
        record_change(item, kind, (summary + '; ' + counts) if summary else counts, added, removed)
    if previous != digest:
        TEXT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(lines), encoding='utf-8')
    item['text_hash'] = digest

def compare_file(item, fingerprint, why):
    """Voor bestanden zonder leesbare tekst (scans, video): alleen zien dát het bestand veranderde."""
    previous = item.get('file_hash')
    if previous and previous != fingerprint:
        record_change(item, 'Bestand gewijzigd', 'bestand vervangen (' + why + '); inhoud niet als tekst te vergelijken')
    item['file_hash'] = fingerprint

def page_date(text, url):
    """Datum uit een opgehaalde pagina: nieuws op medemblik.nl ('Publicatiedatum: Woensdag 7 oktober 2026')
    of raadsvragen in iBabs ('Datum vraag 15-10-2026'). Geeft (datum, label) of (None, None)."""
    m = re.search(r'publicatiedatum\s*:?\s*(?:[a-z]+dag\s+)?(\d{1,2}\s+[a-z]+\s+\d{4})', text.casefold())
    if m and parse_nl_date(m.group(1)):
        return parse_nl_date(m.group(1)), 'publicatiedatum'
    if 'bestuurlijkeinformatie.nl/reports/item' in url.casefold():
        for label in ('Datum vraag', 'Datum ontvangst', 'Datum brief', 'Datum publicatie', 'Datum'):
            m = re.search(re.escape(label) + r'\s*:?\s*(\d{1,2}-\d{1,2}-\d{4})\b', text)
            if m and parse_dmy(m.group(1)):
                return parse_dmy(m.group(1)), label.lower()
    return None, None

def report_attachments(page, page_url):
    """Bijlagen op een raadsportaal-item (raadsvraag, informatienota ...): [(titel, bestandslink)].
    De link in de pagina opent een viewer; het bestand zelf staat op /Document/View/<documentId>
    (gecontroleerd 16 okt 2026)."""
    base = re.match(r'https://[^/]+', page_url).group(0)
    out, seen = [], set()
    for a in page.select('a[href*="/Reports/Document/"]'):
        m = re.search(r'documentId=([0-9a-f-]{36})', a.get('href', ''))
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        for badge in a.select('.badge'):
            badge.extract()
        out.append((clean(a.get_text(' ', strip=True)) or 'Bijlage', base + '/Document/View/' + m.group(1)))
    return out

def attachment_lines(attachments):
    """Tekst van de bijlagen, elk met een kopregel. Scans en te grote bestanden: alleen de kopregel.
    Geeft (alle regels, {titel: regels van die bijlage})."""
    lines, per_title = [], {}
    for title, url in attachments[:MAX_ATTACHMENTS]:
        lines.append(f'[Bijlage: {title}]')
        body = []
        try:
            r = requests.get(url, headers=HEADERS, timeout=40)
            r.raise_for_status()
            if len(r.content) <= MAX_DOC_BYTES and r.content[:4] == b'%PDF':
                body = to_lines(pdf_text(r.content))
        except Exception as exc:
            body = [f'[Bijlage niet te lezen: {str(exc)[:60]}]']
        lines += body
        per_title[title] = body
    return lines, per_title

def check_documents(db):
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    domains = tuple(d for cfg in GEMEENTEN.values() for d in cfg['domains'])
    overview = {u.rstrip('/') for cfg in GEMEENTEN.values() for u in cfg['pages'].values()}
    tracked = [(k, v) for k, v in db['items'].items()
               if (v.get('file_url') or v.get('url', '')).startswith(domains)
               and v.get('url', '').rstrip('/') not in overview
               # Collegebesluiten (Medemblik) en vergaderingen hebben hun eigen vergelijking.
               and v.get('kind') not in ('collegebesluit', 'vergadering') and '/Agenda/Index/' not in v.get('url', '')]
    due = [(k, v) for k, v in tracked if is_due(v, now_dt)]
    # Nooit gecontroleerd eerst, daarna wie het langst wacht; bij gelijke stand de nieuwste stukken eerst.
    due.sort(key=lambda p: p[1].get('doc_date') or '', reverse=True)
    due.sort(key=lambda p: p[1].get('content_checked') or '')
    checked = failures = pdf_count = noscan = 0
    started = datetime.datetime.now(datetime.timezone.utc)
    for key, item in due[:DOCS_PER_RUN]:
        if (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds() > DOC_TIME_BUDGET:
            break  # tijd op; de rest komt de volgende run
        try:
            head = requests.get(item.get('file_url') or item['url'], headers=HEADERS, timeout=30, stream=True)
            if head.status_code in (404, 410):
                head.close()
                item['missing_count'] = item.get('missing_count', 0) + 1
                # Twee keer achter elkaar weg: dan pas melden (één keer kan een storing zijn).
                if item['missing_count'] >= 2 and not item.get('removed'):
                    item['removed'] = utc()
                    record_change(item, 'Niet meer bereikbaar', f'document geeft HTTP {head.status_code}: verwijderd of verplaatst')
                item['content_checked'] = utc()
                checked += 1
                continue
            head.raise_for_status()
            if item.pop('removed', None):
                record_change(item, 'Weer bereikbaar', 'document is weer online')
            item['missing_count'] = 0
            size = int(head.headers.get('Content-Length') or 0)
            content_type = head.headers.get('Content-Type', '').lower()
            if size > MAX_DOC_BYTES:
                head.close()
                compare_file(item, f"{size}|{head.headers.get('Last-Modified', '')}|{head.headers.get('ETag', '')}", 'groot bestand')
            else:
                # Inlezen tot het maximum; sommige bestanden (video) sturen geen grootte mee.
                buf = bytearray()
                for chunk in head.iter_content(256 * 1024):
                    buf += chunk
                    if len(buf) > MAX_DOC_BYTES:
                        break
                head.close()
                data = bytes(buf)
                if len(data) > MAX_DOC_BYTES:
                    compare_file(item, f"groot|{head.headers.get('Content-Disposition', '')}|{hashlib.sha256(data[:1_000_000]).hexdigest()}", 'groot bestand')
                elif 'pdf' in content_type or data[:4] == b'%PDF':
                    pdf_count += 1
                    text = pdf_text(data)
                    if len(clean(text)) >= 80:
                        compare_text(key, item, to_lines(text))
                    else:
                        noscan += 1
                        compare_file(item, hashlib.sha256(data).hexdigest(), 'pdf zonder leesbare tekst')
                elif 'html' in content_type or b'<html' in data[:500].lower():
                    page = BeautifulSoup(data.decode(head.encoding or 'utf-8', errors='replace'), 'html.parser')
                    for tag in page(['script', 'style', 'nav', 'footer', 'header', 'form']):
                        tag.decompose()
                    area = page.select_one('main') or page.select_one('article') or page
                    area_text = clean(area.get_text(' ', strip=True))
                    if not item.get('doc_date') or item.get('doc_date_label') in ('publicatiedatum', 'datum vraag', 'datum ontvangst', 'datum brief', 'datum publicatie', 'datum'):
                        found, label = page_date(area_text, item['url'])
                        if not found:
                            found, label = page_date(clean(page.get_text(' ', strip=True)), item['url'])
                        if found:
                            item['doc_date'], item['doc_date_label'] = found, label
                            if label == 'publicatiedatum':
                                item['publication_date'] = found
                    # Bijlagen eerst ophalen: dat haalt ook de grootte-labels ('90 KB') uit de pagina.
                    atts = report_attachments(page, item['url']) if '/Reports/Item/' in item['url'] else []
                    lines = to_lines(area.get_text('\n', strip=True))
                    if '/Reports/Item/' in item['url']:
                        # Raadsvragen, informatienota's e.d.: de bijlagen (vraag, antwoordbrief, nota) meenemen.
                        att_lines, per_title = attachment_lines(atts)
                        lines += att_lines
                        titles = [t for t, _ in atts]
                        first_time = item.get('text_v') != ATT_V
                        new_titles = [t for t in titles if t not in (item.get('bijlagen_titels') or [])]
                        compare_text(key, item, lines,
                                     kind='Bijlage toegevoegd' if new_titles and not first_time else 'Tekst gewijzigd',
                                     baseline=first_time,
                                     summary=('nieuwe bijlage: ' + ', '.join(new_titles)) if new_titles and not first_time else None)
                        if new_titles and not first_time and item.get('changes') \
                                and item['changes'][-1]['type'] == 'Bijlage toegevoegd':
                            # Laat in de melding de eerste zinnen van de nieuwe bijlage zien (bijv. het antwoord).
                            body = [l for t in new_titles for l in per_title.get(t, []) if len(l) > 25]
                            item['changes'][-1]['added'] = [l[:220] for l in body[:3]]
                            item['changes'][-1]['removed'] = []
                        item.update(text_v=ATT_V, bijlagen_titels=titles,
                                    bijlagen=[{'t': t, 'u': u} for t, u in atts[:MAX_ATTACHMENTS]])
                    else:
                        compare_text(key, item, lines)
                else:
                    compare_file(item, hashlib.sha256(data).hexdigest(), content_type or 'onbekend bestandstype')
            item['content_checked'] = utc()
            item.pop('content_error', None)
            checked += 1
        except Exception as exc:
            failures += 1
            item['content_checked'] = utc()
            item['content_error'] = str(exc)[:120]
    backlog = max(0, len(due) - checked - failures)
    set_status(db, 'algemeen', 'Documentcontrole', ok=failures == 0, count=checked, errors=failures,
               note=f'{checked} documenten gecontroleerd ({pdf_count} pdf), {len(tracked)} gevolgd (alle gemeenten), {backlog} wachten nog. '
                    'Controle: stukken tot 14 dagen oud elke 6 uur, tot 60 dagen dagelijks, tot 180 dagen wekelijks, ouder maandelijks. '
                    'Wijzigingen worden per zin getoond; de eerste controle is een nulmeting. '
                    'Pdf’s zonder leesbare tekst (scans) en grote bestanden: alleen te zien dát ze veranderden. '
                    'Bij raadsvragen en informatienota\u2019s worden ook de bijlagen gelezen (bijv. de antwoordbrief). '
                    'KOOP-bekendmakingen via hun versienummer.' + (f' {noscan} pdf zonder tekst deze run.' if noscan else ''))

# ---------------------------------------------------------------------------
# Trefwoorden (trefwoorden.txt): directe melding als een trefwoord in een stuk opduikt
# ---------------------------------------------------------------------------
def norm(text):
    """Kleine letters, zonder accenten en met enkele spaties: 'Financiële  Zaken' -> 'financiele zaken'."""
    import unicodedata
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'\s+', ' ', text)

def load_keywords():
    """Regels uit trefwoorden.txt. 'medemblik: Wognum' geldt alleen voor die gemeente.
    Geeft [(gemeente of None, trefwoord, regex)]."""
    if not KEYWORDS_FILE.exists():
        return []
    out = []
    for line in KEYWORDS_FILE.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        gid = None
        m = re.match(r'^(medemblik|koggenland|opmeer)\s*:\s*(.+)$', line, re.I)
        if m:
            gid, line = m.group(1).lower(), m.group(2).strip()
        words = norm(line).split()
        if not words:
            continue
        # Heel woord of hele woordgroep, zodat 'Opmeer' niet in 'Opmeerder' en 'kV' niet in 'kVA' matcht.
        # Tussen de woorden mag spatie, streepje of niets staan: '380 kV' vindt ook '380kV' en '380-kV'.
        pattern = re.compile(r'(?<![a-z0-9])' + r'[\s\-]*'.join(re.escape(w) for w in words) + r'(?![a-z0-9])')
        out.append((gid, line, pattern))
    return out

def scan_keywords(db):
    """Zoekt de trefwoorden in titel, omschrijving, locatie en de opgeslagen tekst (pdf/pagina/bijlagen).
    Een nieuwe treffer wordt alleen gemeld bij een recent gevonden of recent gewijzigd stuk, zodat het
    toevoegen van een trefwoord geen stortvloed aan meldingen over oude stukken geeft."""
    keywords = load_keywords()
    kw_sig = hashlib.sha256(repr([(g, k) for g, k, _ in keywords]).encode()).hexdigest()[:12]
    now = datetime.datetime.now(datetime.timezone.utc)
    recent = (now - datetime.timedelta(days=KEYWORD_FRESH_DAYS)).isoformat(timespec='seconds')
    fresh_date = (now.date() - datetime.timedelta(days=KEYWORD_FRESH_DAYS)).isoformat()
    # Een trefwoord dat er net bij is gekomen doet eerst een stille nulmeting: dan meldt hij alleen
    # stukken die daarna binnenkomen of wijzigen, en niet alles wat er de afgelopen dagen al stond.
    state = db.setdefault('state', {}).setdefault('keywords', {})
    known = set(state.get('known') or [])
    scanned = events = 0
    for key, item in db['items'].items():
        sig = f"{kw_sig}|{item.get('text_hash', '')}|{item.get('title', '')}|{item.get('excerpt', '')}"
        if item.get('kw_sig') == sig:
            continue
        item['kw_sig'] = sig
        relevant = [(g, k, p) for g, k, p in keywords if g in (None, item.get('gemeente'))]
        if not relevant:
            item.pop('kw_hits', None)
            continue
        scanned += 1
        text = norm(' '.join(str(item.get(f) or '') for f in ('title', 'excerpt', 'locatie', 'rapport', 'meeting_title')))
        path = text_path(key)
        if item.get('text_hash') and path.exists():
            text += ' ' + norm(path.read_text(encoding='utf-8'))
        hits = sorted({k for g, k, p in relevant if p.search(text)})
        if hits:
            item['kw_hits'] = hits
        else:
            item.pop('kw_hits', None)
        new = [h for h in hits if h not in (item.get('kw_notified') or [])]
        quiet = [h for h in new if h not in known]  # nieuw trefwoord: nulmeting, geen melding
        if quiet:
            item['kw_notified'] = sorted(set(item.get('kw_notified') or []) | set(quiet))
            new = [h for h in new if h in known]
        if new:
            is_recent = (item.get('first_seen', '') >= recent and (item.get('doc_date') or '9999') >= fresh_date) \
                or (item.get('last_change') or '') >= recent
            if is_recent:
                # Stukje tekst rond de eerste treffer, voor de melding (zonder accenten-omzetting, dus leesbaar).
                raw = clean(' '.join(str(item.get(f) or '') for f in ('title', 'excerpt', 'locatie')) + ' ' +
                            (path.read_text(encoding='utf-8') if item.get('text_hash') and path.exists() else ''))
                snippets = {}
                for w in new:
                    m = re.search(r'[\s\-]*'.join(re.escape(x) for x in w.split()), raw, re.I)
                    if m:
                        a, b = max(0, m.start() - 80), m.end() + 80
                        frag = raw[a:b]
                        if a > 0 and ' ' in frag[:20]:
                            frag = frag[frag.index(' ') + 1:]  # niet midden in een woord beginnen
                        if b < len(raw) and ' ' in frag[-20:]:
                            frag = frag[:frag.rindex(' ')]
                        snippets[w] = clean(frag)
                item.setdefault('kw_events', []).append({'at': utc(), 'words': new, 'snippets': snippets})
                item['kw_events'] = item['kw_events'][-5:]
                events += 1
            item['kw_notified'] = sorted(set(item.get('kw_notified') or []) | set(new))
    state['known'] = sorted(k for _, k, _ in keywords)
    set_status(db, 'algemeen', 'Trefwoorden', ok=True,
               note=(f'{len(keywords)} trefwoord(en) in trefwoorden.txt: ' + ', '.join(k for _, k, _ in keywords) + '. '
                     if keywords else 'Nog geen trefwoorden ingesteld (trefwoorden.txt). ')
                    + f'Deze run {scanned} stukken doorzocht, {events} nieuwe treffer(s). '
                      'Gezocht wordt in titel, omschrijving en de volledige tekst van pdf\u2019s, pagina\u2019s en bijlagen.')

# ---------------------------------------------------------------------------
# Kaart: adressen uit bekendmakingen omzetten naar coördinaten (PDOK Locatieserver)
# ---------------------------------------------------------------------------
ADRES = re.compile(r"([A-Z][A-Za-zÀ-ÿ'\.\- ]{2,40}?\s\d+\s?[A-Za-z]?(?:\s?[-/]\s?\d+[A-Za-z]?)?)\s*,?\s*(\d{4})\s?([A-Z]{2})\b")

def geocode(db):
    """Bekendmakingen zonder kaartpunt maar met een adres + postcode ('Kerkebuurt 149, 1647MD Berkhout')
    opzoeken bij de gratis adreszoeker van de overheid (PDOK). Alleen als het gevonden adres in de
    eigen gemeente ligt."""
    todo = [v for v in db['items'].values() if v.get('source') == KOOP_SOURCE and not v.get('geo') and not v.get('geo_tried')]
    todo.sort(key=lambda v: v.get('doc_date') or '', reverse=True)
    found = 0
    for item in todo[:GEOCODE_PER_RUN]:
        item['geo_tried'] = True
        m = ADRES.search(f"{item.get('locatie') or ''} | {item.get('title') or ''}")
        if not m:
            continue
        street = re.split(r'[,:;]', m.group(1))[-1].strip()
        try:
            r = requests.get('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free', headers=HEADERS, timeout=20,
                             params={'q': f'{street} {m.group(2)}{m.group(3)}', 'fq': 'type:adres', 'rows': 1,
                                     'fl': 'weergavenaam,centroide_ll,woonplaatsnaam,gemeentenaam'})
            r.raise_for_status()
            docs = r.json().get('response', {}).get('docs') or []
        except Exception:
            item['geo_tried'] = False  # netwerkfout: volgende run opnieuw
            continue
        if not docs or docs[0].get('gemeentenaam') != GEMEENTEN[item['gemeente']]['naam']:
            continue
        pm = re.match(r'POINT\(([\d.]+) ([\d.]+)\)', docs[0].get('centroide_ll', ''))
        if pm:
            item.update(geo=[round(float(pm.group(2)), 6), round(float(pm.group(1)), 6)], geo_src='PDOK',
                        plaats=docs[0].get('woonplaatsnaam'))
            found += 1
    return found

# ---------------------------------------------------------------------------
# Migraties: oudere gegevens bijwerken zonder iets te wissen
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Raadsvragen die te laat zijn: beantwoordingstermijn uit het reglement van orde
# Medemblik: art. 37 Reglement van orde 2023 (gmb-2023-200047), max. 30 dagen.
# Opmeer: Reglement van orde 2026 (gmb-2026-226516), binnen dertig dagen.
# Een gemeld uitstel (de vragensteller krijgt een nieuwe termijn) is niet te zien in het portaal.
# ---------------------------------------------------------------------------
VRAAG_TERMIJN = {'medemblik': 30, 'opmeer': 30}

def check_vraag_termijnen(db):
    state = db.setdefault('state', {})
    baseline = not state.get('termijn_v1')  # eerste keer: alleen markeren, niet melden
    vandaag = datetime.date.today()
    groups = {}
    for item in db['items'].values():
        if 'vragen' in (item.get('rapport') or '').casefold() and item.get('gemeente') in VRAAG_TERMIJN:
            groups.setdefault((item['gemeente'], norm(item.get('title') or '')[:80]), []).append(item)
    teller = 0
    for (gid, _), items in groups.items():
        beantwoord = any(i.get('antwoord_datum') for i in items)
        for item in items:
            open_ = (item.get('excerpt') or '').endswith('nog niet beantwoord') and not beantwoord and not item.get('removed')
            if not open_:
                item.pop('termijn_verlopen', None)
                continue
            try:
                ingediend = datetime.date.fromisoformat(item.get('doc_date') or '')
            except ValueError:
                continue
            uiterlijk = ingediend + datetime.timedelta(days=VRAAG_TERMIJN[gid])
            if vandaag > uiterlijk:
                teller += 1
                if not item.get('termijn_verlopen'):
                    item['termijn_verlopen'] = uiterlijk.isoformat()
                    if not baseline:
                        record_change(item, 'Termijn verlopen',
                                      f'na {VRAAG_TERMIJN[gid]} dagen nog geen antwoord (ingediend {ingediend:%d-%m-%Y}, '
                                      f'termijn tot {uiterlijk:%d-%m-%Y}); mogelijk is uitstel gemeld')
    state['termijn_v1'] = True
    set_status(db, 'algemeen', 'Termijn raadsvragen', ok=True, count=teller,
               note=f'{teller} raadsvragen staan langer open dan de termijn uit het reglement van orde '
                    '(Medemblik en Opmeer: 30 dagen). Een uitstelbericht aan de vragensteller is in het portaal niet te zien.')

# ---------------------------------------------------------------------------
# Buiten de gemeente: andere overheden (KOOP), Tweede Kamer, rechtspraak. Eén keer per uur.
# ---------------------------------------------------------------------------
ELDERS_SOURCE = 'Andere overheden'
TK_SOURCE = 'Tweede Kamer'
RS_SOURCE = 'Rechtspraak'
WOO_SOURCE = 'Woo-publicaties'
ELDERS_DAYS = 45
# Namen die ook achternaam zijn of elders in Noord-Holland voorkomen (Zuid-Scharwoude, Oudendijk bij Strijen):
# niet los zoeken bij de rechtspraak (daar staan advocatennamen in de tekst).
RS_OVERSLAAN = {'scharwoude', 'oudendijk', 'berkhout', 'twisk', 'ursem'}

def plaats_regex(naam):
    return re.compile(r'(?<![\w-])' + re.escape(naam) + r'(?![\w-])', re.I)

# Plaatsnamen die ook elders in het land voorkomen of een achternaam zijn.
PLAATS_DUBBEL = {'oudendijk', 'scharwoude', 'twisk', 'berkhout', 'ursem'}
LOKALE_INSTANTIES = ('Noord-Holland', 'Hoogheemraadschap Hollands Noorderkwartier')

def plaats_in(text, dubbel_ok=True):
    """Eerste gemeente waarvan een plaatsnaam in de tekst staat: (gid, plaats) of (None, None).
    dubbel_ok=False: namen uit PLAATS_DUBBEL tellen niet mee."""
    for gid, cfg in GEMEENTEN.items():
        for p in [cfg['naam']] + cfg.get('plaatsen', []):
            if not dubbel_ok and p.casefold() in PLAATS_DUBBEL:
                continue
            if plaats_regex(p).search(text or ''):
                return gid, p
    return None, None

def elders_first(db, naam):
    """Draait deze bron voor het eerst? Dan geen pushmeldingen voor wat er al stond."""
    return naam not in db.get('state', {}).get('elders', {})

def elders_due(db, naam, minutes=60):
    st = db.setdefault('state', {}).setdefault('elders', {})
    last = st.get(naam)
    if last and (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(last)).total_seconds() < minutes * 60:
        return False
    st[naam] = utc()
    return True

def collect_andere_overheden(db):
    """Bekendmakingen van provincie, waterschap, ministeries en buurgemeenten waarin een van onze
    plaatsen in de titel of samenvatting staat. Kamerstukken komen via collect_tweede_kamer."""
    eerste = elders_first(db, 'koop')
    if not elders_due(db, 'koop'):
        return
    sinds = (datetime.date.today() - datetime.timedelta(days=ELDERS_DAYS)).isoformat()
    added = total = 0
    errors = []
    eigen = {c['koop'] for c in GEMEENTEN.values()}
    # Opruimen van eerder opgeslagen treffers die niet meer aan de regels voldoen.
    for key in [k for k, v in db['items'].items() if v.get('source') == ELDERS_SOURCE and (
            v.get('instantie') in eigen or (v.get('instantie') not in LOKALE_INSTANTIES and (
                (v.get('plaats') or '').casefold() in PLAATS_DUBBEL
                or re.search(re.escape(v.get('plaats') or '~') + r'\s+\d', v.get('title') or ''))))]:
        db['items'].pop(key)
    for gid, cfg in GEMEENTEN.items():
        namen = [cfg['naam']] + cfg.get('plaatsen', [])
        terms = ' OR '.join(f'"{n}"' for n in dict.fromkeys(namen))
        q = (f'c.product-area=="officielepublicaties" AND ({terms}) AND dt.modified>={sinds} '
             f'NOT dt.creator=="{cfg["koop"]}"')
        try:
            r = requests.get('https://repository.overheid.nl/sru', params={'operation': 'searchRetrieve', 'version': '2.0',
                             'query': q, 'maximumRecords': '500'}, headers=HEADERS, timeout=90)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for record in root.findall('.//{*}recordData'):
                def values(name):
                    return [clean(e.text) for e in record.iter() if e.tag.rsplit('}', 1)[-1] == name and e.text and clean(e.text)]
                first = lambda name: (values(name) or [None])[0]
                creator = first('creator') or ''
                if 'Kamer der Staten-Generaal' in creator or creator in eigen:
                    continue  # Kamerstukken via collect_tweede_kamer; eigen bekendmakingen staan al in KOOP
                title = first('title') or ''
                tekst = title + ' ' + (first('abstract') or '')
                # Oudendijk, Twisk e.d. bestaan ook elders: alleen bij provincie en waterschap meetellen.
                hit_gid, plaats = plaats_in(tekst, dubbel_ok=creator in LOKALE_INSTANTIES)
                if not hit_gid:
                    continue  # plaats alleen ergens diep in de tekst (bijv. een lijst van alle gemeenten)
                if creator not in LOKALE_INSTANTIES and re.search(re.escape(plaats) + r'\s+\d', tekst):
                    continue  # straatnaam elders, bijv. 'Koggenland 29, Purmerend'
                m = next((re.search(r'[a-z]+(?:-[a-z]+)?-\d{4}-[\w-]+', x) for x in values('identifier')
                          if re.search(r'^[a-z]+(?:-[a-z]+)?-\d{4}-[\w-]+$', x)), None)
                if not m:
                    continue
                ident = m.group()
                url = f'https://zoek.officielebekendmakingen.nl/{ident}.html'
                key = make_key(ELDERS_SOURCE + '|' + ident)
                item = db['items'].get(key)
                if item is None:
                    item = db['items'][key] = new_item(hit_gid, title, url, ELDERS_SOURCE, excerpt='', baseline=eerste or None)
                    added += 1
                datum = (first('available') or first('modified') or '')[:10] or None
                types = [t for t in values('type') if '|' not in t]
                item.update(gemeente=hit_gid, instantie=creator, plaats=plaats, doc_date=datum,
                            doc_date_label='publicatiedatum', koop_type=(types[0] if types else None),
                            excerpt=f'{creator}' + (f' · {types[0]}' if types else ''), last_seen=today())
                total += 1
        except Exception as exc:
            errors.append(f'{cfg["naam"]}: {str(exc)[:80]}')
    set_status(db, 'algemeen', ELDERS_SOURCE, ok=not errors, count=total, new=added,
               error='; '.join(errors) or None,
               note=f'Officiële bekendmakingen van provincie Noord-Holland, het waterschap (HHNK), ministeries en andere '
                    f'gemeenten waarin een van de plaatsen in de titel of samenvatting staat (laatste {ELDERS_DAYS} dagen). '
                    'Eén keer per uur.')

def collect_tweede_kamer(db):
    """Kamerstukken (o.a. schriftelijke vragen, moties, brieven) met een van onze plaatsen in titel of onderwerp,
    via de open data van de Tweede Kamer (gegevensmagazijn)."""
    eerste = elders_first(db, 'tk')
    if not elders_due(db, 'tk'):
        return
    namen = list(dict.fromkeys(n for cfg in GEMEENTEN.values() for n in [cfg['naam']] + cfg.get('plaatsen', [])
                               if n.casefold() not in ('scharwoude', 'oudendijk')))
    sinds = (datetime.date.today() - datetime.timedelta(days=ELDERS_DAYS)).isoformat()
    namen += ['West-Friesland', 'Westfriesland']
    try:
        docs, seen = [], set()
        # In blokjes van 6 namen: een te lange zoekvraag weigert de API (HTTP 400).
        for i in range(0, len(namen), 6):
            cond = ' or '.join(f"contains(Onderwerp,'{n}') or contains(Titel,'{n}')" for n in namen[i:i + 6])
            r = requests.get('https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Document', headers=HEADERS, timeout=60, params={
                '$filter': f'({cond}) and Verwijderd eq false and Datum ge {sinds}', '$orderby': 'Datum desc', '$top': 100,
                '$select': 'Id,Soort,Onderwerp,Titel,Datum,DocumentNummer'})
            if not r.ok:
                raise RuntimeError(f'HTTP {r.status_code}: {r.text[:150]}')
            for d in r.json().get('value', []):
                if d['Id'] not in seen:
                    seen.add(d['Id'])
                    docs.append(d)
        added = 0
        for d in docs:
            onderwerp = clean(d.get('Onderwerp') or '')
            titel = clean(d.get('Titel') or '')
            hit_gid, plaats = plaats_in(onderwerp + ' ' + titel)
            regio = not hit_gid
            if regio:
                hit_gid = next(iter(GEMEENTEN))  # West-Friesland in het algemeen: bij de eerste gemeente
            key = make_key(TK_SOURCE + '|' + d['Id'])
            item = db['items'].get(key)
            if item is None:
                item = db['items'][key] = new_item(hit_gid, onderwerp or titel, '', TK_SOURCE, excerpt='', baseline=eerste or None)
                added += 1
            item.update(title=onderwerp or titel, gemeente=hit_gid, plaats=plaats if not regio else None,
                        url=f'https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/Document({d["Id"]})/resource',
                        tk_soort=d.get('Soort'), doc_date=(d.get('Datum') or '')[:10] or None, doc_date_label='datum',
                        excerpt=(d.get('Soort') or 'Kamerstuk') + (f' · {titel}' if titel and titel != onderwerp else '')
                                + f' · {d.get("DocumentNummer")}', last_seen=today())
        set_status(db, 'algemeen', TK_SOURCE, ok=True, count=len(docs), new=added,
                   note=f'Tweede Kamer (open data): documenten van de laatste {ELDERS_DAYS} dagen met een van de plaatsen of '
                        '"West-Friesland" in titel of onderwerp. Alleen titel en onderwerp, niet de volledige tekst. Eén keer per uur.')
    except Exception as exc:
        set_status(db, 'algemeen', TK_SOURCE, ok=False, error=str(exc)[:250])

def collect_rechtspraak(db):
    """Nieuw gepubliceerde uitspraken waarin een van onze plaatsen voorkomt (zoekfunctie van uitspraken.rechtspraak.nl)."""
    eerste = elders_first(db, 'rechtspraak')
    if not elders_due(db, 'rechtspraak'):
        return
    grens = datetime.date.today() - datetime.timedelta(days=ELDERS_DAYS)
    added = total = 0
    errors = []
    for gid, cfg in GEMEENTEN.items():
        for plaats in dict.fromkeys([cfg['naam']] + cfg.get('plaatsen', [])):
            if plaats.casefold() in RS_OVERSLAAN:
                continue
            try:
                r = requests.post('https://uitspraken.rechtspraak.nl/api/zoek', headers=HEADERS, timeout=40, json={
                    'StartRow': 0, 'PageSize': 20, 'ShouldReturnHighlights': False, 'ShouldCountFacets': False,
                    'SortOrder': 'PublicatieDatumDesc', 'SearchTerms': [{'Term': f'"{plaats}"', 'Field': 'AlleVelden'}],
                    'Contentsoorten': [], 'Rechtsgebieden': [], 'Instanties': [], 'DatumPublicatie': [], 'DatumUitspraak': [],
                    'Advanced': {'PublicatieStatus': 'AlleenGepubliceerd'}, 'CorrelationId': 'monitor', 'Proceduresoorten': []})
                r.raise_for_status()
                for res in r.json().get('Results', []):
                    pub = (res.get('PublicatiedatumDate') or '')[:10]
                    if not pub or pub < grens.isoformat():
                        continue
                    ecli = res.get('TitelEmphasis') or ''
                    if not ecli.startswith('ECLI:'):
                        continue
                    total += 1
                    key = make_key(RS_SOURCE + '|' + ecli)
                    frag = clean(res.get('Tekstfragment') or '')
                    titel = re.split(r'(?<=[.!?])\s', frag, 1)[0][:200] if frag else ''
                    if len(titel) < 45:
                        titel = frag[:160] + ('…' if len(frag) > 160 else '') if len(frag) > len(titel) else titel
                    titel = titel or clean(res.get('Titel') or ecli)
                    item = db['items'].get(key)
                    if item is None:
                        item = db['items'][key] = new_item(gid, titel, res.get('DeeplinkUrl') or '', RS_SOURCE, excerpt='', baseline=eerste or None)
                        added += 1
                    uitspraak = res.get('Uitspraakdatum') or ''
                    item.update(title=titel, instantie=clean(res.get('Titel') or ''), ecli=ecli, plaats=item.get('plaats') or plaats,
                                rechtsgebied=', '.join(res.get('Rechtsgebieden') or []), doc_date=pub,
                                doc_date_label='gepubliceerd', excerpt=f'{clean(res.get("Titel") or "")} · '
                                f'{", ".join(res.get("Rechtsgebieden") or [])} · zoekterm {item.get("plaats") or plaats}'
                                + (f' · {frag[:300]}' if frag else ''), last_seen=today())
            except Exception as exc:
                errors.append(f'{plaats}: {str(exc)[:60]}')
    set_status(db, 'algemeen', RS_SOURCE, ok=not errors, count=total, new=added, error='; '.join(errors)[:250] or None,
               note=f'Uitspraken op rechtspraak.nl (laatste {ELDERS_DAYS} dagen gepubliceerd) waarin de gemeente of een '
                    'van de dorpen voorkomt. Namen die ook achternaam zijn (Berkhout, Twisk) of elders voorkomen worden '
                    'niet los gezocht. Uitspraken zijn geanonimiseerd. Eén keer per uur.')

def collect_woo(db):
    """Woo-publicaties op open.overheid.nl: wat de gemeenten zelf openbaar maken, en documenten van andere
    overheden waarin een van de plaatsen in titel of omschrijving staat."""
    eerste = elders_first(db, 'woo')
    if not elders_due(db, 'woo'):
        return
    vanaf = (datetime.date.today() - datetime.timedelta(days=ELDERS_DAYS)).strftime('%d-%m-%Y')
    added = total = 0
    errors = []
    # open.overheid.nl bevat ook regelgeving die al als bekendmaking (KOOP) binnenkomt: die niet dubbel.
    koop_titels = {norm(v.get('title') or '') for v in db['items'].values() if v.get('source') == KOOP_SOURCE}
    for key in [k for k, v in db['items'].items() if v.get('source') == WOO_SOURCE and norm(v.get('title') or '') in koop_titels]:
        db['items'].pop(key)
    for gid, cfg in GEMEENTEN.items():
        eigen = 'gemeente ' + cfg['naam'].casefold()
        for naam in dict.fromkeys([cfg['naam']] + cfg.get('plaatsen', [])):
            if naam.casefold() in PLAATS_DUBBEL:
                continue
            try:
                r = requests.get('https://open.overheid.nl/overheid/openbaarmakingen/api/v0/zoek', headers=HEADERS, timeout=40,
                                 params={'zoektekst': naam, 'sort': 'publicatiedatum', 'publicatiedatumVan': vanaf})
                r.raise_for_status()
                for res in r.json().get('resultaten') or []:
                    d = res.get('document') or {}
                    titel, oms = clean(d.get('titel') or ''), clean(d.get('omschrijving') or '')
                    publisher = clean(d.get('publisher') or '')
                    if publisher.casefold() == eigen:
                        hit_gid, plaats = gid, None
                    else:
                        hit_gid, plaats = plaats_in(titel + ' ' + oms, dubbel_ok=False)
                        if not hit_gid:
                            continue
                    if not titel or not d.get('id') or norm(titel) in koop_titels:
                        continue
                    total += 1
                    key = make_key(WOO_SOURCE + '|' + d['id'])
                    item = db['items'].get(key)
                    if item is None:
                        item = db['items'][key] = new_item(hit_gid, titel, d.get('pid') or f'https://open.overheid.nl/documenten/{d["id"]}',
                                                           WOO_SOURCE, excerpt='', baseline=eerste or None)
                        added += 1
                    item.update(gemeente=hit_gid, instantie=publisher, plaats=plaats or item.get('plaats'),
                                doc_date=(d.get('openbaarmakingsdatum') or '')[:10] or None, doc_date_label='openbaar gemaakt',
                                excerpt=publisher + (f' · {oms[:300]}' if oms else ''), last_seen=today())
            except Exception as exc:
                errors.append(f'{naam}: {str(exc)[:60]}')
    set_status(db, 'algemeen', WOO_SOURCE, ok=not errors, count=total, new=added, error='; '.join(errors)[:250] or None,
               note=f'open.overheid.nl (Woo-publicaties, laatste {ELDERS_DAYS} dagen): alles wat de drie gemeenten openbaar maken, '
                    'plus documenten van andere overheden met een van de plaatsen in titel of omschrijving. Eén keer per uur.')

def migrate(db):
    db.setdefault('items', {})
    db.setdefault('status', {})
    state = db.setdefault('state', {})
    # Okt 2026: bronnen buiten de gemeente opnieuw laten ophalen na aanpassing van de zoekregels.
    if state.get('elders_v') != 2:
        state.pop('elders', None)
        state['elders_v'] = 2
    archive = db.setdefault('archief', {})
    med = GEMEENTEN['medemblik']
    # Versie 3 sloeg kopjes als 'Samenvatting' op als collegebesluiten: naar het archief (niet gewist).
    for key, item in list(db['items'].items()):
        if item.get('source') == 'Collegebesluiten' and item.get('kind') is None \
                and item.get('url', '').rstrip('/') == med['pages']['Collegebesluiten'].rstrip('/'):
            item.update(archived=utc(), archived_reason='Foutieve identificatie in versie 3 (kopje als besluit); revisietelling onbetrouwbaar')
            archive[key] = db['items'].pop(key)
        elif is_navigation(item.get('title', ''), item.get('url', '')):
            item.update(archived=utc(), archived_reason='Menuknop, geen publicatie')
            archive[key] = db['items'].pop(key)
    # Alles van vóór de uitbreiding naar drie gemeenten is Medemblik.
    for item in db['items'].values():
        item.setdefault('gemeente', 'medemblik')
    # Bronstatus per gemeente.
    if any(isinstance(v, dict) and 'checked' in v for v in db['status'].values()):
        old = db['status']
        db['status'] = {'medemblik': {k: v for k, v in old.items() if k not in ('Documentcontrole', 'Bekendmakingen')},
                        'algemeen': {'Documentcontrole': old['Documentcontrole']} if 'Documentcontrole' in old else {}}
    # Bijhoudgegevens per gemeente.
    if 'koop_backfill_month' in state:
        state.setdefault('koop', {}).setdefault('medemblik', {})['backfill_month'] = state.pop('koop_backfill_month')
        state.pop('koop_complete_since', None)
    if isinstance(state.get('meetings_listed'), str):
        state['meetings_listed'] = {'medemblik': state['meetings_listed']}
    for m in state.get('meetings', {}).values():
        m.setdefault('gemeente', 'medemblik')
    # Raadsdocumenten: echte bestandslink (de oude link opende een viewerpagina).
    for key, item in db['items'].items():
        if item.get('kind') == 'raadsdocument' and 'file_url' not in item:
            for k in ('text_hash', 'file_hash', 'content_checked', 'content_error'):
                item.pop(k, None)
            if text_path(key).exists():
                text_path(key).unlink()
            base = GEMEENTEN[item['gemeente']]['ibabs']
            item['file_url'] = base + '/Document/View/' + doc_id_from(item['url'])
    # Correctie: 'Nieuwe versie bij KOOP' bij alleen een nieuwe wijzigingsdatum (zelfde versienummer) was ruis.
    for item in db['items'].values():
        if item.get('source') == KOOP_SOURCE and item.get('changes'):
            def ruis(c):
                m = re.match(r'versiegegevens gewijzigd: (\d+)\|.*?\u2192 (\d+)\|', c.get('summary', ''))
                return c.get('type') == 'Nieuwe versie bij KOOP' and m and m.group(1) == m.group(2)
            kept = [c for c in item['changes'] if not ruis(c)]
            if len(kept) != len(item['changes']):
                item['revisions'] = max(1, item.get('revisions', 1) - (len(item['changes']) - len(kept)))
                item['changes'] = kept
                item['last_change'] = kept[-1]['at'] if kept else None
                item.pop('change_type', None)
    # Correctie: 'Beantwoord' werd ook gemeld bij de eerste keer dat een vraag in het overzicht stond.
    for item in db['items'].values():
        if item.get('kind') == 'overzichtsitem' and not item.get('report_seen') and item.get('changes'):
            kept = [c for c in item['changes'] if c['type'] != 'Beantwoord']
            if len(kept) != len(item['changes']):
                item['revisions'] = max(1, item.get('revisions', 1) - (len(item['changes']) - len(kept)))
                item['changes'] = kept
                item['last_change'] = kept[-1]['at'] if kept else None
                item.pop('change_type', None)
    for item in db['items'].values():
        news_title_date(item)
        if 'last_change' not in item:
            item['last_change'] = item.get('updated') if item.get('revisions', 1) > 1 else None
        if item.get('doc_date'):
            continue
        if item.get('meeting_date'):
            item['doc_date'], item['doc_date_label'] = item['meeting_date'], 'vergaderdatum college'
        elif item.get('source') == KOOP_SOURCE and item.get('publication_date'):
            item['doc_date'], item['doc_date_label'] = item['publication_date'], 'documentdatum (KOOP)'
            item['publication_date'] = None
        elif '/Agenda/Index/' in item.get('url', '') and parse_nl_date(item.get('title', '')):
            item['doc_date'], item['doc_date_label'] = parse_nl_date(item['title']), 'vergaderdatum'

def fetch_grenzen():
    """Gemeentegrens per gemeente voor de kaart (Kadaster, via PDOK). Eén keer ophalen; grenzen
    veranderen zelden. Verwijder data/grenzen/<gemeente>.json om opnieuw op te halen."""
    folder = DB.parent / 'grenzen'
    folder.mkdir(exist_ok=True)
    for gid, cfg in GEMEENTEN.items():
        path = folder / f'{gid}.json'
        if path.exists():
            continue
        try:
            r = requests.get('https://api.pdok.nl/kadaster/bestuurlijkegebieden/ogc/v1/collections/gemeentegebied/items',
                             params={'f': 'json', 'naam': cfg['naam'], 'limit': 1}, headers=HEADERS, timeout=30)
            r.raise_for_status()
            feats = r.json().get('features') or []
            if not feats:
                continue
            geom = feats[0]['geometry']
            def rnd(c):
                return [rnd(v) for v in c] if isinstance(c[0], list) else [round(c[0], 5), round(c[1], 5)]
            geom['coordinates'] = rnd(geom['coordinates'])
            path.write_text(json.dumps({'type': 'Feature', 'properties': {'naam': cfg['naam']}, 'geometry': geom},
                                       separators=(',', ':')))
        except Exception as exc:
            print('Gemeentegrens', gid, 'niet opgehaald:', exc)

# De website (dashboard, zoekindex, kaart) wordt bij het publiceren gebouwd door build_site.py.

def main():
    run_start = datetime.datetime.now(datetime.timezone.utc)
    DB.parent.mkdir(exist_ok=True)
    db = json.loads(DB.read_text()) if DB.exists() else {}
    migrate(db)
    for gid, cfg in GEMEENTEN.items():
        collect_official(db, gid)
        if cfg['ibabs']:
            collect_meetings(db, gid)
            collect_ibabs_reports(db, gid)
        if cfg['news_rss']:
            collect_news_rss(db, gid, cfg['news_rss'])
        if cfg['college_pdf_page']:
            collect_college_pdfs(db, gid, cfg['college_pdf_page'])
        collect_pages(db, gid)
        if cfg.get('plaatsen'):
            collect_media(db, gid, cfg['plaatsen'])
    for fn in (collect_andere_overheden, collect_tweede_kamer, collect_rechtspraak, collect_woo):
        try:
            fn(db)
        except Exception as exc:
            print(fn.__name__, exc)
    check_vraag_termijnen(db)
    koop_publication_times(db)
    fetch_grenzen()
    geocode(db)
    check_documents(db)
    scan_keywords(db)
    # Bovengrens: bewaar de meest recent actieve items.
    items = sorted(db['items'].items(), key=lambda kv: kv[1].get('last_change') or kv[1]['first_seen'], reverse=True)[:MAX_ITEMS]
    db['items'] = dict(items)
    # Meldingen: push na elke run, e-mailsamenvatting één keer per dag (zie notify.py).
    import notify
    try:
        notify.run(db, GEMEENTEN, run_start, set_status)
    except Exception as exc:
        set_status(db, 'algemeen', 'Meldingen', ok=False, error=str(exc)[:200])
    DB.write_text(json.dumps(db, ensure_ascii=False, indent=2) + '\n')
    for gid in GEMEENTEN:
        n = sum(1 for v in db['items'].values() if v.get('gemeente') == gid)
        print(f'{gid}: {n} items')

if __name__ == '__main__':
    main()
