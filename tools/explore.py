import requests, json
H={'User-Agent':'Mozilla/5.0 (Gemeentemonitor)'}
def t(u, **kw):
    try:
        r=requests.get(u,headers=H,timeout=30,**kw); print(r.status_code, r.headers.get('content-type'), len(r.content), u[:150]); return r
    except Exception as e: print('ERR',u,e)
print('== tegels ==')
for u in ['https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/grijs/EPSG:3857/12/2105/1335.png',
          'https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/pastel/EPSG:3857/12/2105/1335.png',
          'https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/12/2105/1335.png']:
    t(u)
print('== grenzen ==')
r=t('https://api.pdok.nl/kadaster/bestuurlijkegebieden/ogc/v1/collections?f=json')
if r is not None and r.ok: print([c['id'] for c in r.json().get('collections',[])])
for g in ['Medemblik','Koggenland','Opmeer']:
    r=t('https://api.pdok.nl/kadaster/bestuurlijkegebieden/ogc/v1/collections/gemeentegebied/items',params={'f':'json','naam':g,'limit':5})
    if r is not None and r.ok:
        j=r.json(); fs=j.get('features',[])
        print(g,len(fs),[f['properties'] for f in fs][:2], fs and fs[0]['geometry']['type'], fs and len(json.dumps(fs[0]['geometry'])))
