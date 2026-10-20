import sys; sys.path.insert(0, ".")
import json, collections, monitor as m
db = json.load(open('data/items.json'))
for gid in ('medemblik', 'opmeer'):
    reps = db['state']['reports'][gid]['reports']
    for rid, rep in reps.items():
        if not any(w in rep['name'].lower() for w in ('motie', 'amendement', 'toezegging')): continue
        rows, total = m.ibabs_report_rows(m.GEMEENTEN[gid]['ibabs'], rid, rep['columns'], rep.get('order_col', 0), 0, 40)
        print('==', gid, rep['name'], total)
        for col in [c['data'] for c in rep['columns']]:
            if col in ('title', 'DT_RowId', 'identity'): continue
            vals = collections.Counter(str(r.get(col))[:60] for r in rows)
            print('   ', col, vals.most_common(6))
        print('    sample', json.dumps(rows[0], ensure_ascii=False)[:700])
# run
