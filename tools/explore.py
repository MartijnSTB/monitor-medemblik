import requests,re
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
IB='https://medemblik.bestuurlijkeinformatie.nl'
def sec(t): print('\n'+'='*20,t,'='*20,flush=True)
def get(u):
    r=requests.get(u,headers=H,timeout=40);print(r.status_code,r.headers.get('Content-Type'),len(r.content));return r
sec('Reports RSS')
r=get(IB+'/Reports/RSS');print(r.text[:3500])
sec('Reports Details raadsvragen')
r=get(IB+'/Reports/Details/b6e30d37-cfd2-4064-a7fa-19453570dfb5')
t=r.text;i=t.find('maincontent');print(t[i:i+6000])
s=BeautifulSoup(t,'html.parser');print('links Item:',len([a for a in s.find_all('a',href=True) if '/Reports/Item/' in a['href']]))
for a in s.find_all('a',href=True):
    if 'page' in a['href'].lower() or 'Load' in a['href']:print('PAG',a.get_text(strip=True),a['href'])
print('data-attrs:',sorted(set(re.findall(r'data-[a-z\-]+="[^"]{0,120}"',t)))[:40])
sec('RetrieveAgendasForYear')
r=get(IB+'/Agenda/RetrieveAgendasForYear?agendatypeId=0&year=2026');print(r.text[:2500])
sec('agendapunt structuur')
r=get(IB+'/Agenda/Index/d4b32282-6d07-4f2e-9463-89fb9b55e9c3');t=r.text
i=t.find('Deelname KCR2');print(t[i-2500:i+4000])
sec('nieuws rss')
r=get('https://www.medemblik.nl/nieuws.rss');print(r.text[:2500]);print('items:',r.text.count('<item'))
sec('nieuwspagina 5')
r=get('https://www.medemblik.nl/nieuws/nieuwspagina/5')
s=BeautifulSoup(r.text,'html.parser');print([h.get_text(strip=True)[:60] for h in s.find_all('h2')][:6])
