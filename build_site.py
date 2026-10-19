"""Bouwt de website van de Gemeentemonitor uit data/ (draait bij het publiceren, niet bij elke monitorrun).

Uitvoer in docs/ (niet in Git; wordt alleen naar GitHub Pages gestuurd):
  index.html                 het dashboard (kopie van dashboard.html)
  data/<gemeente>.json       alle stukken per gemeente
  search/<gemeente>/<xx>.json zoekindex: woord -> stukken, verdeeld op de eerste twee letters,
                             zodat het dashboard alleen het stukje laadt dat het nodig heeft
  text/<id>.txt              de opgeslagen tekst per stuk, voor de tekstfragmenten bij zoekresultaten

Zo groeit de repository niet bij elke run met megabytes aan zoekindex.
"""
import json, re, shutil, datetime, html
from collections import defaultdict
from monitor import GEMEENTEN, DB, ROOT, TEXT_DIR, KOOP_SOURCE, norm, text_path

DOCS = ROOT / 'docs'

PUBLIC_FIELDS = ('title', 'url', 'source', 'kind', 'doc_date', 'doc_date_label', 'first_seen', 'last_change',
                 'revisions', 'changes', 'removed', 'besluit_status', 'koop_type', 'locatie', 'meeting_title',
                 'agendapunt', 'rapport', 'antwoord_datum', 'portefeuillehouder', 'published_at', 'geo', 'plaats',
                 'kw_hits', 'bijlagen', 'media_bron', 'media_match')

def public_item(key, item):
    out = {k: item[k] for k in PUBLIC_FIELDS if item.get(k) not in (None, '', [])}
    out['excerpt'] = html.unescape(item.get('excerpt') or '')[:300]
    # Sommige bronnen leveren al geëscapete tekst ('R&amp;D'); het dashboard escapet zelf.
    out['title'] = html.unescape(out.get('title') or '')
    out['id'] = key[:24]
    if item.get('text_hash') and text_path(key).exists():
        out['tx'] = 1  # er is opgeslagen tekst (voor tekstfragmenten)
    if len(item.get('meetings') or []) > 1:
        out['n_meetings'] = len(item['meetings'])
    return out

def tokens(text):
    """Woorden zoals het dashboard ze ook maakt: zonder accenten, kleine letters, letters en cijfers.
    Woorden vanaf 3 tekens; getallen vanaf 2 cijfers (huisnummers, '380')."""
    return {t for t in re.findall(r'[a-z0-9]+', norm(text)) if len(t) >= 3 or (t.isdigit() and len(t) >= 2)}

def build():
    db = json.loads(DB.read_text())
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    if DOCS.exists():
        shutil.rmtree(DOCS)
    (DOCS / 'data').mkdir(parents=True)
    (DOCS / 'text').mkdir()
    for gid, cfg in GEMEENTEN.items():
        rows = [(k, v) for k, v in db['items'].items() if v.get('gemeente') == gid]
        items = [public_item(k, v) for k, v in rows]
        status = dict(db['status'].get(gid, {}))
        for name, reason in cfg['not_followed'].items():
            status[name] = {'skip': True, 'note': reason}
        # Dorpen voor het dorpfilter: de BAG-woonplaatsen (Koggenland zelf is geen woonplaats).
        dorpen = sorted(p for p in cfg.get('plaatsen', []) if p != 'Koggenland')
        payload = {'gemeente': gid, 'naam': cfg['naam'], 'generated': stamp, 'status': status, 'dorpen': dorpen,
                   'algemeen': db['status'].get('algemeen', {}), 'items': items}
        (DOCS / 'data' / f'{gid}.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

        # Zoekindex: per woord de volgnummers van de stukken (volgorde = items in data/<gemeente>.json).
        index = defaultdict(lambda: defaultdict(list))
        for i, (key, v) in enumerate(rows):
            text = ' '.join(str(v.get(f) or '') for f in ('title', 'excerpt', 'locatie', 'plaats', 'rapport',
                                                          'meeting_title', 'agendapunt', 'portefeuillehouder'))
            path = text_path(key)
            if v.get('text_hash') and path.exists():
                body = path.read_text(encoding='utf-8')
                text += ' ' + body
                (DOCS / 'text' / f'{key[:24]}.txt').write_text(body, encoding='utf-8')
            for t in tokens(text):
                index[t[:2]][t].append(i)
        sdir = DOCS / 'search' / gid
        sdir.mkdir(parents=True)
        for shard, words in index.items():
            (sdir / f'{shard}.json').write_text(json.dumps(words, separators=(',', ':')), encoding='utf-8')
        print(f'{gid}: {len(items)} stukken, {sum(len(w) for w in index.values())} woorden in de zoekindex, '
              f'{sum(1 for v in items if v.get("geo"))} op de kaart')
    shutil.copy(ROOT / 'dashboard.html', DOCS / 'index.html')
    # App-icoon en manifest (zet het dashboard als app op je beginscherm).
    for f in (ROOT / 'site').iterdir():
        shutil.copy(f, DOCS / f.name)
    # Gemeentegrenzen voor de kaart (opgehaald door monitor.py, bron: Kadaster/PDOK).
    (DOCS / 'grens').mkdir()
    for f in (ROOT / 'data' / 'grenzen').glob('*.json'):
        shutil.copy(f, DOCS / 'grens' / f.name)

if __name__ == '__main__':
    build()
