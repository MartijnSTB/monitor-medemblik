import requests,re,json
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def sec(t): print('\n'+'='*20,t,'='*20,flush=True)
def page(url,maxlinks=60,filt=None,snip=None):
    sec(url)
    try:
        r=requests.get(url,headers=H,timeout=40);print(r.status_code,r.headers.get('Content-Type'),len(r.content),'final',r.url)
        s=BeautifulSoup(r.text,'html.parser')
        for t in s(['script','style']):t.decompose()
        for h in s.find_all(['h1','h2','h3'])[:25]:print(h.name,'|',re.sub(r'\s+',' ',h.get_text(' ',strip=True))[:110])
        seen=set();n=0
        for a in s.find_all('a',href=True):
            hr=a['href'];tx=re.sub(r'\s+',' ',a.get_text(' ',strip=True))[:110]
            if hr in seen or hr.startswith(('#','mailto','tel','javascript')):continue
            if filt and not re.search(filt,hr+' '+tx,re.I):continue
            seen.add(hr);n+=1;print('A',tx,'->',hr[:150])
            if n>maxlinks:break
        for l in s.find_all('link',type=re.compile('rss|atom')):print('FEED',l.get('href'))
        if snip:
            i=r.text.find(snip);print('SNIP',r.text[max(0,i-800):i+1500] if i>=0 else 'niet gevonden')
        return r
    except Exception as e: print('ERR',e)
page('https://www.koggenland.nl/nieuwsberichten',40,None,'nieuws')
page('https://www.opmeer.nl/nieuws',40)
page('https://www.koggenland.nl/gemeenteraad',60)
page('https://www.koggenland.nl/zoeken?q=collegebesluiten',30,r'besluit|college')
for u in ['https://www.koggenland.nl/collegebesluiten','https://www.koggenland.nl/besluitenlijsten-college','https://www.koggenland.nl/college-van-burgemeester-en-wethouders','https://www.koggenland.nl/bestuur','https://www.koggenland.nl/openbaar-gemaakte-informatie-koggenland']:
    page(u,50,r'besluit|college|woo|openbaar|pdf|nieuws')
page('https://www.koggenland.nl/sitemap',300,r'besluit|college|raad|bekendmak|openbaar|woo')
for u in ['https://www.koggenland.nl/rss','https://www.koggenland.nl/nieuwsberichten/rss','https://www.opmeer.nl/rss.xml','https://www.opmeer.nl/nieuws/rss']:
    try:
        r=requests.get(u,headers=H,timeout=30);print('\nRSS',u,r.status_code,r.headers.get('Content-Type'),r.text[:300].replace('\n',' '))
    except Exception as e: print('RSS',u,'ERR',e)
sec('Opmeer agenda jaarlijst')
for t in [100000025,100044942,100044935,100113337]:
    r=requests.get('https://opmeer.bestuurlijkeinformatie.nl/Agenda/RetrieveAgendasForYear',params={'agendatypeId':t,'year':2026},headers=H,timeout=30)
    print(t,r.status_code,len(re.findall(r'/Agenda/Index/',r.text)),re.findall(r'agenda-link-title">([^<]+)',r.text)[:3])
r=page('https://opmeer.bestuurlijkeinformatie.nl/Agenda/Index/4b7a5077-4b22-4a0c-8c4a-713900f40f21',15,r'Document')
sec('ORI Koggenland')
for u in ['https://api.openraadsinformatie.nl/v1/elastic/_search?q=koggenland&size=2','https://api.openraadsinformatie.nl/v1/elastic/ori_*/_search?q=Koggenland&size=1']:
    try:
        r=requests.get(u,headers=H,timeout=40);print(u,r.status_code,r.text[:700])
    except Exception as e: print('ERR',e)
try:
    r=requests.get('https://api.openraadsinformatie.nl/v1/elastic/_cat/indices?format=json',headers=H,timeout=40)
    idx=[x['index'] for x in r.json() if 'kogg' in x['index'] or 'opmeer' in x['index'] or 'medemblik' in x['index']];print('indices',r.status_code,idx)
except Exception as e: print('cat ERR',e)
sec('raad.koggenland.nl varianten')
for u in ['https://raad.koggenland.nl/rss','https://raad.koggenland.nl/Vergaderingen/Gemeenteraad/2026','https://raad.koggenland.nl/api/','https://raad.koggenland.nl/sitemap.xml']:
    try:
        r=requests.get(u,headers={**H,'Accept':'*/*'},timeout=30);print(u,r.status_code,r.headers.get('Content-Type'),'challenge' if 'Beveiligingscontrole' in r.text else r.text[:200].replace('\n',' '))
    except Exception as e: print(u,'ERR',e)
