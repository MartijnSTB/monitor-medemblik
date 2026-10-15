import requests,re
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def sec(t): print('\n'+'='*20,t,'='*20,flush=True)
def raw(url,n=3000,params=None):
    sec(url)
    try:
        r=requests.get(url,headers=H,timeout=40,params=params);print(r.status_code,r.headers.get('Content-Type'),len(r.content));print(r.text[:n]);return r
    except Exception as e: print('ERR',e)
raw('https://www.koggenland.nl/rss/content-list?type%5B%5D=news&sort_by=published_at&sort_order=DESC',1800)
raw('https://www.opmeer.nl/rss/content-list?type%5B%5D=news&sort_by=published_at&sort_order=DESC',1200)
r=raw('https://raad.koggenland.nl/rss',4000)
print('items:',r.text.count('<item'))
for u in ['https://raad.koggenland.nl/rss/vergaderingen','https://raad.koggenland.nl/Vergaderingen/rss','https://raad.koggenland.nl/rss?type=vergaderingen','https://raad.koggenland.nl/Documenten/rss','https://raad.koggenland.nl/rss/documenten','https://raad.koggenland.nl/agenda/rss','https://raad.koggenland.nl/ical']:
    try:
        x=requests.get(u,headers=H,timeout=30);print('CAND',u,x.status_code,x.headers.get('Content-Type'),'challenge' if 'Beveiligingscontrole' in x.text else x.text[:150].replace('\n',' '))
    except Exception as e: print('CAND',u,'ERR',e)
sec('koggenland bestuursstukken college')
r=requests.get('https://www.koggenland.nl/bestuursstukken-vergaderingen-college-bw',headers=H,timeout=40);print(r.status_code,len(r.content))
s=BeautifulSoup(r.text,'html.parser')
for t in s(['script','style','nav','footer','header']):t.decompose()
m=s.select_one('main') or s
for h in m.find_all(['h1','h2','h3','h4'])[:40]:print(h.name,'|',re.sub(r'\s+',' ',h.get_text(' ',strip=True))[:120])
for a in m.find_all('a',href=True)[:60]:print('A',re.sub(r'\s+',' ',a.get_text(' ',strip=True))[:110],'->',a['href'][:160])
txt=re.sub(r'\s+',' ',m.get_text(' ',strip=True));print('TEXT',txt[:2500])
sec('opmeer bestuur')
r=requests.get('https://www.opmeer.nl/bestuur-en-organisatie',headers=H,timeout=40);s=BeautifulSoup(r.text,'html.parser')
for a in s.find_all('a',href=True):
    t=a.get_text(' ',strip=True)
    if re.search(r'besluit|college|raad|bekendmak|woo|openbaar',t+a['href'],re.I):print('A',t[:100],'->',a['href'][:150])
sec('iBabs reports ajax')
r=requests.get('https://opmeer.bestuurlijkeinformatie.nl/Reports/Details/e90d2554-7a8b-4254-a9c1-fba22e8d67b3',headers=H,timeout=40)
print(sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"',r.text))))
print(sorted(set(re.findall(r'["\'](/Reports/[A-Za-z]+[^"\']*)',r.text))))
i=r.text.find('overzichten-data');print(r.text[i-200:i+2500])
for js in set(re.findall(r'src="(/[^"]+\.js[^"]*)"',r.text)):
    try:
        j=requests.get('https://opmeer.bestuurlijkeinformatie.nl'+js,headers=H,timeout=30).text
        for m_ in set(re.findall(r'.{0,80}(?:Reports/|ajax).{0,120}',j)):
            if 'Report' in m_: print('JS',js[-30:],'|',m_[:200])
    except Exception as e: print('JSERR',e)
