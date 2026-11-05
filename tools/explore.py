import sys, json; sys.path.insert(0, '.')
import monitor as m
db = {'items': {}, 'status': {}, 'state': {}}
ms = m.go_list_meetings(db, 'koggenland', 'https://raad.koggenland.nl')
print('vergaderingen:', len(ms))
for h, v in sorted(ms.items(), key=lambda p: p[1]['date'])[-12:]: print('  ', v['date'], v.get('tijd'), v['type'], h)
r = m.http_get('https://raad.koggenland.nl/Vergaderingen/Gemeenteraad/2026/09-november/19:30', timeout=90)
punten, docs = m.go_parse_meeting(r.text)
print('agendapunten', len(punten), punten[:8])
print('documenten', len(docs))
for d in docs[:8]: print('  ', d)
moties = [d for d in docs if 'otie' in d[1] or 'mendement' in d[1]]
print('moties', moties[:5])
m.collect_go(db, 'koggenland')
print(db['status'])
print(len(db['items']), [ (v['title'][:50], v.get('motie_status')) for v in db['items'].values() if v.get('motie_status')][:6])
# test document via proxy (stream)
x = m.http_get(docs[0][2], timeout=60, stream=True); print('doc', x.status_code, x.headers.get('content-type'), x.raw.read(8))
