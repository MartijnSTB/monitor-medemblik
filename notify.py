"""Meldingen van de Gemeentemonitor.

Twee soorten:
  1. Directe pushmelding (ntfy-app op je telefoon), na elke run, alleen voor belangrijke dingen:
     trefwoorden uit trefwoorden.txt (eigen bericht, hoge prioriteit), wijzigingen, nieuwe bijlagen
     (bijv. een antwoordbrief), beantwoorde raadsvragen, verdwenen stukken, nieuwe collegebesluiten,
     raadsvragen, moties/amendementen en raadsvoorstellen. Eén bericht per gemeente per run.
  2. Dagelijkse samenvatting per e-mail (Gmail), één keer per dag vanaf DIGEST_HOUR:
     alles wat sinds de vorige samenvatting nieuw of gewijzigd is, per gemeente en per kolom.

Instellingen komen uit GitHub-secrets (doorgegeven als omgevingsvariabelen):
  NTFY_TOPIC          geheime naam van je ntfy-onderwerp (werkt als wachtwoord)
  MAIL_USER           je Gmail-adres (afzender)
  MAIL_APP_PASSWORD   een Gmail-app-wachtwoord (niet je gewone wachtwoord)
  MAIL_TO             ontvanger(s), komma-gescheiden; leeg = MAIL_USER
  MAIL_SMTP_HOST      optioneel, standaard smtp.gmail.com (bijv. smtp.office365.com)
  MAIL_SMTP_PORT      optioneel, standaard 587
Ontbreekt een instelling, dan wordt dat kanaal overgeslagen en staat dat op het dashboard.
"""
import os, datetime, smtplib, html
from email.message import EmailMessage
from zoneinfo import ZoneInfo
import requests

DASHBOARD_URL = 'https://martijnstb.github.io/monitor-medemblik/'
DIGEST_HOUR = 7                 # samenvatting vanaf 07:00 Nederlandse tijd
FRESH_DAYS = 3                  # 'nieuw' telt alleen als het stuk zelf hooguit zoveel dagen oud is
MAX_PUSH_LINES = 8
MAX_MAIL_PER_COLUMN = 40
TZ = ZoneInfo('Europe/Amsterdam')
MAANDEN = ['januari','februari','maart','april','mei','juni','juli','augustus','september','oktober','november','december']

def nl_moment(dt):
    d = dt.astimezone(TZ)
    return f'{d.day} {MAANDEN[d.month - 1]} {d:%H:%M}'

# Zelfde indeling en kleuren als de kolommen op het dashboard.
COLUMNS = [
    ('Bekendmakingen', '#006dac'),
    ('Raad', '#1b4e8e'),
    ('College', '#f18700'),
    ('Nieuws en Woo', '#5498cf'),
]

def column_of(item):
    s = item.get('source')
    if s == 'Officiele bekendmakingen (KOOP)':
        return 'Bekendmakingen'
    if s in ('Raadsstukken', 'Raadsportaal'):
        return 'Raad'
    if s == 'Collegebesluiten':
        return 'College'
    return 'Nieuws en Woo'

def _date(s):
    try:
        return datetime.date.fromisoformat((s or '')[:10])
    except ValueError:
        return None

def is_fresh(item, since):
    """Een 'nieuw' gevonden stuk telt alleen als het zelf recent is. Zo geven oude stukken die de
    monitor pas nu vindt (archief, inhaalslag) geen meldingen."""
    d = _date(item.get('doc_date'))
    if d is None:
        return True
    return d >= (since.date() - datetime.timedelta(days=FRESH_DAYS))

def events_since(db, since):
    """Alle gebeurtenissen na tijdstip `since` (datetime, UTC): nieuwe stukken en wijzigingen."""
    since_iso = since.isoformat(timespec='seconds')
    events = []
    for item in db['items'].values():
        if item.get('kind') == 'vergadering':
            continue
        if (item.get('first_seen') or '') > since_iso and is_fresh(item, since):
            events.append({'kind': 'nieuw', 'item': item, 'at': item['first_seen'], 'text': ''})
        for k in item.get('kw_events') or []:
            if (k.get('at') or '') > since_iso:
                events.append({'kind': 'trefwoord', 'item': item, 'at': k['at'], 'words': k.get('words', []),
                               'snippets': k.get('snippets') or {},
                               'text': 'trefwoord: ' + ', '.join(k.get('words', []))})
        for c in item.get('changes') or []:
            if (c.get('at') or '') > since_iso:
                kind = {'Beantwoord': 'beantwoord', 'Niet meer bereikbaar': 'verdwenen',
                        'Bijlage toegevoegd': 'bijlage'}.get(c.get('type'), 'gewijzigd')
                events.append({'kind': kind, 'item': item, 'at': c['at'], 'text': c.get('summary', ''),
                               'added': c.get('added') or [], 'removed': c.get('removed') or []})
    events.sort(key=lambda e: e['at'], reverse=True)
    return events

def is_important(ev):
    """Wat een directe pushmelding waard is."""
    if ev['kind'] != 'nieuw':
        return True  # gewijzigd, beantwoord, verdwenen
    item = ev['item']
    title = (item.get('title') or '').casefold()
    rapport = (item.get('rapport') or '').casefold()
    if item.get('source') == 'Collegebesluiten':
        return True
    if any(w in rapport for w in ('vragen', 'motie', 'amendement')):
        return True
    if item.get('source') == 'Raadsstukken' and 'raadsvoorstel' in title:
        return True
    return False

def time_label(item, at=None):
    """'gepubliceerd 09:00' als de bron een tijd geeft, anders 'gevonden 16:30' (door de monitor).
    Voor een wijziging: het moment waarop de monitor de wijziging zag."""
    def hm(s):
        return datetime.datetime.fromisoformat(s).astimezone(TZ).strftime('%H:%M')
    try:
        if at:
            return 'gezien ' + hm(at)
        if item.get('published_at'):
            return 'gepubliceerd ' + hm(item['published_at'])
        if item.get('first_seen'):
            return 'gevonden ' + hm(item['first_seen'])
    except ValueError:
        pass
    return ''

LABEL = {'nieuw': 'Nieuw', 'gewijzigd': 'Gewijzigd', 'beantwoord': 'Beantwoord', 'verdwenen': 'Verdwenen',
         'bijlage': 'Nieuwe bijlage', 'trefwoord': 'Trefwoord'}

# ---------------------------------------------------------------------------
# Directe pushmelding (ntfy)
# ---------------------------------------------------------------------------
def send_keyword_push(gemeenten, events_by_gid, topic):
    """Trefwoorden krijgen een eigen bericht met hoge prioriteit, met een stukje tekst eromheen."""
    sent = 0
    for gid, events in events_by_gid.items():
        kws = [e for e in events if e['kind'] == 'trefwoord']
        if not kws:
            continue
        words = sorted({w for e in kws for w in e['words']})
        lines = []
        for e in kws[:MAX_PUSH_LINES]:
            snip = next(iter(e['snippets'].values()), '')
            lines.append(f"- **{', '.join(e['words'])}** · {column_of(e['item'])}: {e['item']['title'][:110]}"
                         + (f"\n  _…{snip}…_" if snip else ''))
        if len(kws) > MAX_PUSH_LINES:
            lines.append(f'- en nog {len(kws) - MAX_PUSH_LINES} op het dashboard')
        r = requests.post(f'https://ntfy.sh/{topic}', data='\n'.join(lines).encode('utf-8'), timeout=20, headers={
            'Title': f'{gemeenten[gid]["naam"]}: {", ".join(words)[:80]}',
            'Click': DASHBOARD_URL + '#' + gid,
            'Tags': 'mag',
            'Priority': 'high',
            'Markdown': 'yes',
        })
        r.raise_for_status()
        sent += 1
    return sent

def send_push(gemeenten, events_by_gid, topic):
    sent = send_keyword_push(gemeenten, events_by_gid, topic)
    for gid, events in events_by_gid.items():
        # Stukken die al in het trefwoordbericht stonden niet nog eens melden.
        kw_items = {id(e['item']) for e in events if e['kind'] == 'trefwoord'}
        important = [e for e in events if e['kind'] != 'trefwoord' and id(e['item']) not in kw_items and is_important(e)]
        if not important:
            continue
        naam = gemeenten[gid]['naam']
        lines = []
        for e in important[:MAX_PUSH_LINES]:
            extra = f" ({e['text']})" if e['kind'] in ('beantwoord', 'gewijzigd', 'bijlage') and e['text'] else ''
            tijd = time_label(e['item'], e['at'] if e['kind'] != 'nieuw' else None)
            lines.append(f"- **{LABEL[e['kind']]}** · {column_of(e['item'])}: {e['item']['title'][:120]}{extra} ({tijd})")
            if e['kind'] == 'bijlage' and e.get('added'):
                lines.append(f"  _{e['added'][0][:160]}_")
        if len(important) > MAX_PUSH_LINES:
            lines.append(f'- en nog {len(important) - MAX_PUSH_LINES} op het dashboard')
        urgent = any(e['kind'] in ('gewijzigd', 'beantwoord', 'verdwenen', 'bijlage') for e in important)
        r = requests.post(f'https://ntfy.sh/{topic}', data='\n'.join(lines).encode('utf-8'), timeout=20, headers={
            'Title': f'{naam}: {len(important)} melding{"en" if len(important) != 1 else ""}',
            'Click': DASHBOARD_URL + '#' + gid,
            'Tags': 'bell',
            'Priority': 'high' if urgent else 'default',
            'Markdown': 'yes',
        })
        r.raise_for_status()
        sent += 1
    return sent

# ---------------------------------------------------------------------------
# Dagelijkse samenvatting (e-mail)
# ---------------------------------------------------------------------------
def _mail_html(gemeenten, events_by_gid, since, now_local):
    e = html.escape
    parts = [f'''<div style="font-family:Arial,Helvetica,sans-serif;color:#1d1d1b;max-width:720px">
<h1 style="font-family:Georgia,serif;color:#1b4e8e;margin:0 0 4px">Gemeentemonitor</h1>
<p style="color:#5b6672;margin:0 0 18px">Nieuw en gewijzigd sinds {nl_moment(since)}
· <a href="{DASHBOARD_URL}" style="color:#006dac">open het dashboard</a></p>''']
    for gid, cfg in gemeenten.items():
        events = events_by_gid.get(gid, [])
        kws = [x for x in events if x['kind'] == 'trefwoord']
        changed = [x for x in events if x['kind'] not in ('nieuw', 'trefwoord')]
        new = [x for x in events if x['kind'] == 'nieuw']
        parts.append(f'<h2 style="font-family:Georgia,serif;border-bottom:3px solid #daeaf3;padding-bottom:4px;margin:26px 0 8px">'
                     f'<a href="{DASHBOARD_URL}#{gid}" style="color:#1d1d1b;text-decoration:none">{e(cfg["naam"])}</a>'
                     f' <span style="font-size:14px;color:#5b6672;font-weight:normal">{len(new)} nieuw, {len(changed)} gewijzigd'
                     + (f', {len(kws)} trefwoord' if kws else '') + '</span></h2>')
        if not events:
            parts.append('<p style="color:#5b6672">Niets nieuw of gewijzigd.</p>')
            continue
        if kws:
            parts.append('<h3 style="color:#1b4e8e;margin:12px 0 4px">Jouw trefwoorden</h3><ul style="padding-left:18px">')
            for x in kws:
                it = x['item']
                snips = ''.join(f'<div style="font-size:13px;color:#1d1d1b;background:#fff4e5;padding:3px 6px;margin-top:2px">'
                                f'<b>{e(w)}</b>: …{e(t)}…</div>' for w, t in x['snippets'].items())
                parts.append(f'<li style="margin:6px 0"><b>{e(", ".join(x["words"]))}</b> · {column_of(it)}: '
                             f'<a href="{e(it["url"])}" style="color:#006dac">{e(it["title"])}</a>{snips}</li>')
            parts.append('</ul>')
        if changed:
            parts.append('<h3 style="color:#f18700;margin:12px 0 4px">Gewijzigd, nieuwe bijlagen, beantwoord of verdwenen</h3><ul style="padding-left:18px">')
            for x in changed:
                it = x['item']
                diff = ''.join(f'<div style="color:#165c35">+ {e(a)}</div>' for a in x.get('added', [])[:2]) + \
                       ''.join(f'<div style="color:#8a2c2c;text-decoration:line-through">− {e(r)}</div>' for r in x.get('removed', [])[:2])
                parts.append(f'<li style="margin:6px 0"><b>{LABEL[x["kind"]]}</b> · {column_of(it)}: '
                             f'<a href="{e(it["url"])}" style="color:#006dac">{e(it["title"])}</a>'
                             f'<div style="color:#5b6672;font-size:13px">{e(x["text"])} · {time_label(it, x["at"])}</div>'
                             f'<div style="font-size:13px">{diff}</div></li>')
            parts.append('</ul>')
        for col, color in COLUMNS:
            rows = [x for x in new if column_of(x['item']) == col]
            if not rows:
                continue
            parts.append(f'<h3 style="color:{color};margin:14px 0 4px">{col} <span style="color:#5b6672;font-weight:normal">({len(rows)})</span></h3><ul style="padding-left:18px">')
            for x in rows[:MAX_MAIL_PER_COLUMN]:
                it = x['item']
                sub = ', '.join(v for v in (time_label(it), it.get('koop_type'), it.get('locatie'), it.get('rapport'), it.get('meeting_title')) if v)
                parts.append(f'<li style="margin:5px 0"><a href="{e(it["url"])}" style="color:#1d1d1b">{e(it["title"])}</a>'
                             + (f'<div style="color:#5b6672;font-size:13px">{e(sub)}</div>' if sub else '') + '</li>')
            if len(rows) > MAX_MAIL_PER_COLUMN:
                parts.append(f'<li style="color:#5b6672">en nog {len(rows) - MAX_MAIL_PER_COLUMN} op het dashboard</li>')
            parts.append('</ul>')
    parts.append('<p style="color:#5b6672;font-size:12px;margin-top:28px">Automatisch verstuurd door de Gemeentemonitor. '
                 'Geen garantie op volledigheid; zie het dashboard voor wat wel en niet wordt gevolgd.</p></div>')
    return ''.join(parts)

def _mail_text(gemeenten, events_by_gid):
    out = []
    for gid, cfg in gemeenten.items():
        events = events_by_gid.get(gid, [])
        out.append(f'\n== {cfg["naam"]} ==')
        if not events:
            out.append('Niets nieuw of gewijzigd.')
        for x in events[:150]:
            tijd = time_label(x['item'], x['at'] if x['kind'] != 'nieuw' else None)
            out.append(f'- {LABEL[x["kind"]]} · {column_of(x["item"])}: {x["item"]["title"]} ({tijd})\n  {x["item"]["url"]}')
    out.append(f'\nDashboard: {DASHBOARD_URL}')
    return '\n'.join(out)

def send_digest(gemeenten, events_by_gid, since, now_local, user, password, to,
                host='smtp.gmail.com', port=587):
    n_new = sum(1 for ev in events_by_gid.values() for x in ev if x['kind'] == 'nieuw')
    n_chg = sum(1 for ev in events_by_gid.values() for x in ev if x['kind'] not in ('nieuw', 'trefwoord'))
    n_kw = sum(1 for ev in events_by_gid.values() for x in ev if x['kind'] == 'trefwoord')
    msg = EmailMessage()
    msg['Subject'] = f'Gemeentemonitor {now_local.day}-{now_local.month}: ' + \
        (f'{n_kw}× trefwoord, ' if n_kw else '') + f'{n_new} nieuw, {n_chg} gewijzigd'
    msg['From'] = f'Gemeentemonitor <{user}>'
    msg['To'] = to
    msg.set_content(_mail_text(gemeenten, events_by_gid))
    msg.add_alternative(_mail_html(gemeenten, events_by_gid, since, now_local), subtype='html')
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return n_new, n_chg

# ---------------------------------------------------------------------------
# Aanroep vanuit monitor.py, aan het eind van elke run
# ---------------------------------------------------------------------------
def run(db, gemeenten, run_start, set_status):
    state = db.setdefault('state', {}).setdefault('notify', {})
    now = datetime.datetime.now(datetime.timezone.utc)
    now_local = now.astimezone(TZ)
    notes, errors = [], []

    test = os.environ.get('TEST_MELDING', '').strip().lower() == 'true'
    # 1. Directe pushmelding over wat deze run vond.
    topic = os.environ.get('NTFY_TOPIC', '').strip()
    if topic and test:
        # Testknop: altijd één bericht, zodat je ziet dat de push aankomt.
        try:
            requests.post(f'https://ntfy.sh/{topic}', timeout=20,
                          data='Testmelding: pushmeldingen van de Gemeentemonitor werken.'.encode('utf-8'),
                          headers={'Title': 'Gemeentemonitor test', 'Tags': 'white_check_mark',
                                   'Click': DASHBOARD_URL}).raise_for_status()
            notes.append('Testpush verstuurd.')
        except Exception as exc:
            errors.append('Testpush: ' + str(exc)[:120])
    if topic:
        by_gid = {}
        for ev in events_since(db, run_start):
            by_gid.setdefault(ev['item'].get('gemeente'), []).append(ev)
        try:
            n = send_push(gemeenten, {g: by_gid.get(g, []) for g in gemeenten}, topic)
            notes.append(f'Pushmeldingen actief (ntfy); deze run {n} bericht(en).')
        except Exception as exc:
            errors.append('Push: ' + str(exc)[:120])
    else:
        notes.append('Pushmeldingen niet ingesteld (geheim NTFY_TOPIC ontbreekt).')

    # 2. Dagelijkse samenvatting, één keer per dag vanaf DIGEST_HOUR.
    user = os.environ.get('MAIL_USER', '').strip()
    password = os.environ.get('MAIL_APP_PASSWORD', '').replace(' ', '').strip()
    to = os.environ.get('MAIL_TO', '').strip() or user
    if user and password:
        today = now_local.date().isoformat()
        if not state.get('digest_sent_at'):
            # Eerste keer: begin te tellen vanaf nu, anders bevat de eerste mail alles wat de
            # monitor ooit heeft opgebouwd.
            state['digest_sent_at'] = run_start.isoformat(timespec='seconds')
        if test:
            # Testknop: samenvatting van de afgelopen 24 uur, zonder de dagelijkse planning te verstoren.
            since = now - datetime.timedelta(days=1)
            by_gid = {}
            for ev in events_since(db, since):
                by_gid.setdefault(ev['item'].get('gemeente'), []).append(ev)
            try:
                n_new, n_chg = send_digest(gemeenten, by_gid, since, now_local, user, password, to,
                                           os.environ.get('MAIL_SMTP_HOST', '').strip() or 'smtp.gmail.com',
                                           int(os.environ.get('MAIL_SMTP_PORT', '').strip() or 587))
                notes.append(f'Testmail verstuurd ({n_new} nieuw, {n_chg} gewijzigd in de afgelopen 24 uur).')
            except Exception as exc:
                errors.append('Testmail: ' + str(exc)[:120])
        elif now_local.hour >= DIGEST_HOUR and state.get('digest_date') != today:
            last = state.get('digest_sent_at')
            since = datetime.datetime.fromisoformat(last) if last else now - datetime.timedelta(days=1)
            by_gid = {}
            for ev in events_since(db, since):
                by_gid.setdefault(ev['item'].get('gemeente'), []).append(ev)
            try:
                n_new, n_chg = send_digest(gemeenten, by_gid, since, now_local, user, password, to,
                                           os.environ.get('MAIL_SMTP_HOST', '').strip() or 'smtp.gmail.com',
                                           int(os.environ.get('MAIL_SMTP_PORT', '').strip() or 587))
                state.update(digest_date=today, digest_sent_at=now.isoformat(timespec='seconds'))
                notes.append(f'Dagelijkse samenvatting verstuurd om {now_local:%H:%M} ({n_new} nieuw, {n_chg} gewijzigd).')
            except Exception as exc:
                errors.append('E-mail: ' + str(exc)[:120])
        else:
            notes.append(f'Dagelijkse samenvatting actief, elke dag vanaf {DIGEST_HOUR:02d}:00'
                         + (f' (laatste: {state["digest_date"]}).' if state.get('digest_date') else '.'))
    else:
        notes.append('Dagelijkse e-mail niet ingesteld (geheimen MAIL_USER en MAIL_APP_PASSWORD ontbreken).')

    set_status(db, 'algemeen', 'Meldingen', ok=not errors, note=' '.join(notes),
               error='; '.join(errors) if errors else None)
