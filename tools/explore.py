import requests,re
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for base,item in [('https://medemblik.bestuurlijkeinformatie.nl','/Reports/Item/86f6c6f9-f9e5-4d5e-bd3f-44207ef9625b'),('https://medemblik.bestuurlijkeinformatie.nl','/Reports/Item/a543e9b3-cb50-4e9c-be31-94f8fedebefe'),('https://opmeer.bestuurlijkeinformatie.nl','/Reports/Item/69d484ea-32e9-4eaf-b020-c8e1004c402d')]:
    r=requests.get(base+item,headers=H,timeout=40);s=BeautifulSoup(r.text,'html.parser')
    links=[(a.get_text(' ',strip=True)[:60],a['href']) for a in s.select('a[href*="/Reports/Document/"]')]
    print('\n##',item,r.status_code,'bijlagen:',len(links))
    for t,h in links[:4]:
        did=re.search(r'documentId=([0-9a-f-]+)',h).group(1)
        for cand in (base+'/Document/View/'+did, base+h):
            x=requests.get(cand,headers=H,timeout=40,stream=True);head=x.raw.read(5);x.close()
            print('  ',t,'|',cand[-70:],x.status_code,x.headers.get('Content-Type'),head)
q='c.product-area=="officielepublicaties" AND dt.creator=="Medemblik" AND dt.available>=2026-10-01'
r=requests.get('https://repository.overheid.nl/sru',params={'operation':'searchRetrieve','version':'2.0','query':q,'maximumRecords':'200'},headers=H,timeout=60)
recs=re.findall(r'<sru:recordData>(.*?)</sru:recordData>',r.text,re.S)
pts=[re.findall(r'locatiepunt>([^<]+)<',x) for x in recs]
print('\nKOOP records',len(recs),'met locatiepunt',sum(1 for p in pts if p),'meerdere',sum(1 for p in pts if len(p)>1),'voorbeeld',[p for p in pts if p][:3])
print('zonder punt types:',[re.findall(r'type[^>]*>([^<]+)<',x)[:1] for x,p in zip(recs,pts) if not p][:8])
