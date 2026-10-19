import json, sys, requests, collections
sys.path.insert(0, '.')
import monitor as m
d = json.load(open('data/items.json')) if False else None
H = m.HEADERS
REP = {
 'medemblik': {'d78d4c5b-fa21-407c-82d7-4d8e82ea7a6c': ('Moties en amendementen', ['identity','registrationdate','title','standvanzaken','portefeuillehouder','completed','datumafdoening','status','type','hoofdindiener','medeindiener'], 1),
               'b6e30d37-cfd2-4064-a7fa-19453570dfb5': ('Raadsvragen', ['datum','title','datumantwoord','bijlages','toelichting','identity','pinnummer','poho'], 0),
               '3e68aabb-a3f3-403a-b088-5d336fed3822': ('Toezeggingen', ['identity','registrationdate','title','completed','omschrijving','portefeuillehouder','standvanzaken'], 1)},
 'opmeer': {'28e14d86-7e0f-45a0-b1e7-50f9f83066c6': ('Moties', ['registrationdate','title','portefeuillehouder','status','raadsleden','afgedaan'], 0),
            'fe1e75d9-c849-4568-8195-14f33d21a7d5': ('Amendementen', ['registrationdate','title','status','portefeuillehouder','Fracties'], 0),
            '6d7d02ae-90e7-42dc-b08c-4780a85e5519': ('Politieke vragen', ['registrationdate','title','afgedaan','datumantwoord'], 0),
            'c7782114-c8ac-42f5-8746-aa78ef1ebc66': ('Toezeggingen', ['registrationdate','title','portefeuillehouder','fractie','afgedaan'], 0)}}
for g, reps in REP.items():
    base = m.GEMEENTEN[g]['ibabs']
    for rid, (name, cols, oc) in reps.items():
        try:
            rows, total = m.ibabs_report_rows(base, rid, [{'data': c} for c in cols], oc, 0, 400)
            print(f'\n=== {g} {name}: total {total}, got {len(rows)}')
            for r in rows[:4]:
                print({k: (str(v)[:140]) for k, v in r.items() if k not in ('bijlages',)})
            for c in cols:
                if c in ('status','type','hoofdindiener','medeindiener','raadsleden','Fracties','fractie','poho','completed','afgedaan'):
                    print('  ', c, collections.Counter(str(r.get(c))[:60] for r in rows).most_common(12))
            dates = sorted(str(r.get(cols[0]) or '') for r in rows)
            print('  oudste/nieuwste', dates[:1], dates[-1:])
        except Exception as e:
            print('FOUT', g, name, e)
print('\n=== iBabs mensen/fracties')
for g in ['medemblik','opmeer']:
    base = m.GEMEENTEN[g]['ibabs']
    for path in ['/People', '/People/Index', '/Persons', '/Organisatie', '/People/Profiles']:
        try:
            r = requests.get(base + path, headers=H, timeout=20)
            print(g, path, r.status_code, len(r.text), r.url[-60:])
        except Exception as e: print(g, path, e)
print('\n=== CBS catalogus')
r = requests.get("https://opendata.cbs.nl/ODataCatalog/Tables?$format=json&$filter=substringof('Kerncijfers wijken en buurten',Title)&$select=Identifier,Title,Modified", headers=H, timeout=30)
print(r.status_code)
try:
    for t in sorted(r.json()['value'], key=lambda t: t['Identifier']): print(t)
except Exception as e: print(r.text[:300])
