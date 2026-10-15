import requests,re
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
IB='https://medemblik.bestuurlijkeinformatie.nl'
u=IB+'/Agenda/Document/d4b32282-6d07-4f2e-9463-89fb9b55e9c3?documentId=0d404209-8669-41e9-af01-748bdc84be76&agendaItemId=a6938304-28bf-4898-b572-5cbfdca6c954'
for allow in (True,False):
    r=requests.get(u,headers=H,timeout=40,allow_redirects=allow)
    print('allow_redirects',allow,r.status_code,r.headers.get('Content-Type'),len(r.content),'Location',r.headers.get('Location'),'history',[h.status_code for h in r.history],'final',r.url)
r=requests.get(u,headers=H,timeout=40)
t=r.text
for pat in [r'[^"\' ]*(?:pdf|Load|Download|Document/View|viewer)[^"\' ]*']:
    print(sorted(set(re.findall(pat,t,re.I)))[:40])
s=BeautifulSoup(t,'html.parser')
for tag in s.find_all(['iframe','embed','object']): print('EMBED',tag.name,tag.attrs)
for a in s.find_all('a',href=True):
    if 'ocument' in a['href'] or 'ownload' in a['href']: print('A',a.get_text(' ',strip=True)[:60],'->',a['href'][:160])
i=t.find('0d404209');print(t[max(0,i-1500):i+1500])
for cand in [IB+'/Document/View/0d404209-8669-41e9-af01-748bdc84be76',IB+'/Agenda/Document/d4b32282-6d07-4f2e-9463-89fb9b55e9c3?documentId=0d404209-8669-41e9-af01-748bdc84be76&agendaItemId=a6938304-28bf-4898-b572-5cbfdca6c954&download=true']:
    r=requests.get(cand,headers=H,timeout=40);print('CAND',cand[-60:],r.status_code,r.headers.get('Content-Type'),len(r.content),r.content[:5])
r=requests.get(IB+'/Document/View/1257dc55-679b-4b8f-a2b2-f89db2147cd9',headers=H,timeout=40,stream=True);print('VIDEO',r.status_code,dict(r.headers));r.close()
