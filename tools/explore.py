import requests,json
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
r=requests.get('https://api.openraadsinformatie.nl/v1/elastic/_cat/indices?format=json',headers=H,timeout=60)
idx=sorted(x['index'] for x in r.json())
print('ORI indices totaal',len(idx));print([i for i in idx if any(k in i for k in ('kogg','opmeer','medem','hoorn','drechter','stede','enkhuizen','westfries'))])
q={'query':{'bool':{'must':[{'match':{'_all':'koggenland'}}]}},'size':3}
for name in ['koggenland','Koggenland']:
    r=requests.get('https://api.openraadsinformatie.nl/v1/elastic/_search',params={'q':f'has_organization_name:{name}','size':2},headers=H,timeout=60)
    print(name,r.status_code,r.text[:300])
# directe pdf zonder controle?
for u in ['https://raad.koggenland.nl/Documenten/Besluitenlijst-vergadering-26-november.pdf','https://raad.koggenland.nl/robots.txt']:
    x=requests.get(u,headers=H,timeout=30);print(u,x.status_code,x.headers.get('Content-Type'),'challenge' if 'Beveiligingscontrole' in x.text[:5000] else x.content[:60])
