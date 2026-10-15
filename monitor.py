"""Gemeentemonitor: openbare publicaties van Medemblik, Koggenland en Opmeer.

Per gemeente staat in GEMEENTEN welke bronnen er zijn. Elke run:
  1. KOOP-bekendmakingen (laatste 30 dagen + archief maand voor maand)
  2. raadsportaal (iBabs): vergaderingen, documenten en overzichten (raadsvragen e.d.)
  3. nieuws (RSS of webpagina), collegebesluiten, losse pagina's
  4. documentcontrole: tekst van documenten vergelijken met de vorige versie
  5. per gemeente een databestand voor het dashboard (docs/data/<gemeente>.json)

Uitgangspunt: de monitor zegt eerlijk wat hij wel en niet volgt (zie 'note' per bron).
"""
import json, hashlib, re, datetime, urllib.parse, html as htmllib, email.utils
from pathlib import Path
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

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
        'news_rss': None,
        'college_pdf_page': None,
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
DOCS_PER_RUN = 40              # documentcontrole: documenten per run (alle gemeenten samen)
MAX_DOC_BYTES = 15_000_000     # groter: alleen bestandskenmerken vergelijken
TEXT_CAP = 300_000             # maximaal aantal tekens tekst per document
MAX_CHANGES = 10               # zoveel wijzigingen per document bewaren
MAX_ITEMS = 10_000             # bovengrens voor items.json

# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------
def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')

def today():
    # Alleen de dag: zo verandert 'last_seen' maar één keer per dag en blijft de Git-historie klein.
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()

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
    """'15-10-2026' -> '2026-10-15', anders None."""
    m = re.match(r'\s*(\d{1,2})-(\d{1,2})-(\d{4})', text or '')
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
        # Nieuwe versie bij KOOP (bijv. een rectificatie): versienummer of wijzigingsdatum anders.
        version = f"{first('hasVersion') or '1'}|{first('modified') or ''}"
        if item.get('koop_version') and item['koop_version'] != version:
            record_change(item, 'Nieuwe versie bij KOOP',
                          f"versiegegevens gewijzigd: {item['koop_version']} → {version}")
        item['koop_version'] = version
        types = [t for t in values('type') if '|' not in t]
        item.update(gemeente=gid, koop_dates=koop, doc_date=doc_date, doc_date_label=label,
                    publication_date=koop['available'] or koop['issued'], last_seen=today(),
                    koop_type=(types or values('type') or [None])[0], locatie=first('geometrielabel'),
                    publicatie=first('publicatienaam'),
                    excerpt=first('abstract') or ('Officiele bekendmaking; ' + (label + ': ' + doc_date if doc_date else 'datum onbekend')))
    return added

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
            date = None
            if it.findtext('pubDate'):
                try:
                    dt = email.utils.parsedate_to_datetime(clean(it.findtext('pubDate')))
                    date = dt.date().isoformat()
                except (TypeError, ValueError):
                    pass
            key = make_key(source + '|' + link)
            item = db['items'].get(key)
            if item is None:
                item = db['items'][key] = new_item(gid, title, link, source)
                added += 1
            item.update(doc_date=date, doc_date_label='publicatiedatum', publication_date=date,
                        excerpt=clean(it.findtext('description'))[:400], last_seen=today())
        set_status(db, gid, source, ok=bool(items), count=len(items), new=added,
                   note=f'RSS-feed van de gemeentesite: de {len(items)} nieuwste berichten. Oudere berichten niet.')
    except Exception as exc:
        set_status(db, gid, source, ok=False, error=str(exc)[:250])

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
    if listed.get(gid) == today():
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
    listed[gid] = today()
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
        window.sort(key=lambda p: p[1].get('checked', ''))
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
def ibabs_report_list(db, gid):
    """Eén keer per dag: welke overzichten zijn er, en welke kolommen hebben ze."""
    base = GEMEENTEN[gid]['ibabs']
    state = db.setdefault('state', {}).setdefault('reports', {}).setdefault(gid, {})
    if state.get('listed') == today() and state.get('reports'):
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
    state.update(listed=today(), reports=reports)
    return reports

def ibabs_report_rows(base, rid, columns, start, length):
    """Vraagt een pagina regels op via dezelfde tabel-aanvraag die de website zelf doet
    (POST /Reports/GetReportData/<id>, gecontroleerd 15 okt 2026). Nieuwste eerst."""
    data = {'draw': '1', 'start': str(start), 'length': str(length), 'order[0][column]': '0',
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

def collect_ibabs_reports(db, gid):
    base = GEMEENTEN[gid]['ibabs']
    source_name = 'Raadsportaal-overzichten'
    try:
        reports = ibabs_report_list(db, gid)
        full = db['state']['reports'][gid].get('full_pass') != today()  # één keer per dag dieper terug
        added = rows_seen = 0
        errors, summary = [], []
        for rid, rep in reports.items():
            cols = rep.get('columns') or []
            if not cols:
                continue
            date_col = cols[0]['data']
            is_besluitenlijst = 'besluitenlijst' in rep['name'].casefold()
            try:
                start, total, got = 0, None, 0
                while True:
                    length = 200 if full else REPORT_ROWS_PER_RUN
                    rows, total = ibabs_report_rows(base, rid, cols, start, length)
                    oldest = None
                    for row in rows:
                        rows_seen += 1
                        got += 1
                        rowid = row.get('DT_RowId')
                        title = clean(row.get('title'))
                        if not rowid or not title:
                            continue
                        url = f'{base}/Reports/Item/{rowid}'
                        key = make_key('Raadsportaal|' + url)  # zelfde sleutel als links van de startpagina
                        reg_date = parse_dmy(row.get(date_col) or '')
                        oldest = reg_date or oldest
                        item = db['items'].get(key)
                        is_new = item is None
                        if is_new:
                            item = db['items'][key] = new_item(gid, title, url, 'Raadsportaal', excerpt='')
                            added += 1
                        item.update(gemeente=gid, kind='overzichtsitem', rapport=rep['name'], last_seen=today())
                        if is_besluitenlijst:
                            # Besluitenlijsten van het college: datum van de collegevergadering uit de titel.
                            item['source'] = 'Collegebesluiten'
                            vergader = parse_nl_date(title)
                            item.update(doc_date=vergader or reg_date,
                                        doc_date_label='vergaderdatum college' if vergader else 'registratiedatum')
                        elif reg_date and (not item.get('doc_date') or item.get('doc_date_label') in ('registratiedatum', 'datum')):
                            label = 'datum vraag' if date_col == 'datum' and 'vraag' in rep['name'].casefold() \
                                else ('registratiedatum' if date_col == 'registrationdate' else 'datum')
                            item.update(doc_date=reg_date, doc_date_label=label)
                        if row.get('poho'):
                            item['portefeuillehouder'] = clean(row['poho'])
                        if 'datumantwoord' in row:
                            antwoord = parse_dmy(row.get('datumantwoord') or '')
                            if antwoord and item.get('antwoord_datum') != antwoord:
                                if not is_new:
                                    record_change(item, 'Beantwoord', f'datum antwoord: {antwoord}')
                                item['antwoord_datum'] = antwoord
                        item['excerpt'] = rep['name'] + (f' · antwoord {item["antwoord_datum"]}' if item.get('antwoord_datum')
                                                         else (' · nog niet beantwoord' if 'datumantwoord' in row else ''))
                    start += len(rows)
                    # Normaal alleen de nieuwste regels; bij de dagelijkse ronde door tot KOOP_START.
                    if not full or not rows or start >= (total or 0) or (oldest and oldest < KOOP_START) or start >= 2000:
                        break
                summary.append(f'{rep["name"]} {total}')
            except Exception as exc:
                errors.append(f'{rep["name"]}: {str(exc)[:60]}')
        if full and not errors:
            db['state']['reports'][gid]['full_pass'] = today()
        set_status(db, gid, source_name, ok=not errors, count=rows_seen, new=added,
                   error='; '.join(errors)[:250] if errors else None,
                   note='Alle overzichten van het raadsportaal (totaal per overzicht: ' + ', '.join(summary) + '). '
                        f'Elke run de {REPORT_ROWS_PER_RUN} nieuwste per overzicht; één keer per dag alles vanaf {KOOP_START}. '
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

def compare_text(key, item, lines, kind='Tekst gewijzigd'):
    """Vergelijk met de vorige tekstversie. De eerste keer is alleen een nulmeting."""
    import difflib
    digest = hashlib.sha256('\n'.join(lines).encode()).hexdigest()
    path = text_path(key)
    previous = item.get('text_hash')
    if previous and previous != digest:
        old = path.read_text(encoding='utf-8').split('\n') if path.exists() else []
        sm = difflib.SequenceMatcher(None, old, lines, autojunk=False)
        added = [l for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ('insert', 'replace') for l in lines[j1:j2]]
        removed = [l for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ('delete', 'replace') for l in old[i1:i2]]
        summary = 'tekst gewijzigd (vorige versie niet bewaard)' if not old else \
            f'{len(added)} zin(nen) toegevoegd of aangepast, {len(removed)} verwijderd of vervangen'
        record_change(item, kind, summary, added, removed)
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
    due.sort(key=lambda p: p[1].get('content_checked') or '')  # nooit gecontroleerd eerst
    checked = failures = pdf_count = noscan = 0
    for key, item in due[:DOCS_PER_RUN]:
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
                    compare_text(key, item, to_lines(area.get_text('\n', strip=True)))
                else:
                    compare_file(item, hashlib.sha256(data).hexdigest(), content_type or 'onbekend bestandstype')
            item['content_checked'] = utc()
            item.pop('content_error', None)
            checked += 1
        except Exception as exc:
            failures += 1
            item['content_checked'] = utc()
            item['content_error'] = str(exc)[:120]
    backlog = max(0, len(due) - DOCS_PER_RUN)
    set_status(db, 'algemeen', 'Documentcontrole', ok=failures == 0, count=checked, errors=failures,
               note=f'{checked} documenten gecontroleerd ({pdf_count} pdf), {len(tracked)} gevolgd (alle gemeenten), {backlog} wachten nog. '
                    'Controle: stukken tot 14 dagen oud elke 6 uur, tot 60 dagen dagelijks, tot 180 dagen wekelijks, ouder maandelijks. '
                    'Wijzigingen worden per zin getoond; de eerste controle is een nulmeting. '
                    'Pdf’s zonder leesbare tekst (scans) en grote bestanden: alleen te zien dát ze veranderden. '
                    'KOOP-bekendmakingen via hun versiegegevens.' + (f' {noscan} pdf zonder tekst deze run.' if noscan else ''))

# ---------------------------------------------------------------------------
# Migraties: oudere gegevens bijwerken zonder iets te wissen
# ---------------------------------------------------------------------------
def migrate(db):
    db.setdefault('items', {})
    db.setdefault('status', {})
    state = db.setdefault('state', {})
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

# ---------------------------------------------------------------------------
# Uitvoer voor het dashboard
# ---------------------------------------------------------------------------
PUBLIC_FIELDS = ('title', 'url', 'source', 'kind', 'doc_date', 'doc_date_label', 'first_seen', 'last_change',
                 'revisions', 'changes', 'removed', 'besluit_status', 'koop_type', 'locatie', 'meeting_title',
                 'agendapunt', 'rapport', 'antwoord_datum', 'portefeuillehouder')

def public_item(item):
    out = {k: item[k] for k in PUBLIC_FIELDS if item.get(k) not in (None, '', [])}
    out['excerpt'] = (item.get('excerpt') or '')[:300]
    if len(item.get('meetings') or []) > 1:
        out['n_meetings'] = len(item['meetings'])
    return out

def write_outputs(db):
    data_dir = DOCS / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    for gid, cfg in GEMEENTEN.items():
        status = dict(db['status'].get(gid, {}))
        for name, reason in cfg['not_followed'].items():
            status[name] = {'skip': True, 'note': reason}
        payload = {'gemeente': gid, 'naam': cfg['naam'], 'generated': utc(), 'status': status,
                   'algemeen': db['status'].get('algemeen', {}),
                   'items': [public_item(v) for v in db['items'].values() if v.get('gemeente') == gid]}
        (data_dir / f'{gid}.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (DOCS / 'index.html').write_text((ROOT / 'dashboard.html').read_text(encoding='utf-8'), encoding='utf-8')

def main():
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
    check_documents(db)
    # Bovengrens: bewaar de meest recent actieve items.
    items = sorted(db['items'].items(), key=lambda kv: kv[1].get('last_change') or kv[1]['first_seen'], reverse=True)[:MAX_ITEMS]
    db['items'] = dict(items)
    DB.write_text(json.dumps(db, ensure_ascii=False, indent=2) + '\n')
    write_outputs(db)
    for gid in GEMEENTEN:
        n = sum(1 for v in db['items'].values() if v.get('gemeente') == gid)
        print(f'{gid}: {n} items')

if __name__ == '__main__':
    main()
