import requests,re
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def sec(t): print('\n'+'='*20,t,'='*20,flush=True)
def page(url,maxlinks=150,filt=None,show_heads=True):
    sec(url)
    try:
        r=requests.get(url,headers=H,timeout=40);print(r.status_code,r.headers.get('Content-Type'),len(r.content),'final',r.url)
        s=BeautifulSoup(r.text,'html.parser')
        for t in s(['script','style']):t.decompose()
        if show_heads:
            for h in s.find_all(['h1','h2','h3'])[:30]:print(h.name,'|',re.sub(r'\s+',' ',h.get_text(' ',strip=True))[:110])
        seen=set();n=0
        for a in s.find_all('a',href=True):
            hr=a['href'];tx=re.sub(r'\s+',' ',a.get_text(' ',strip=True))[:90]
            if hr in seen or hr.startswith(('#','mailto','tel','javascript')):continue
            if filt and not re.search(filt,hr+' '+tx,re.I):continue
            seen.add(hr);n+=1;print('A',tx,'->',hr[:150])
            if n>maxlinks:break
        for l in s.find_all('link',type=re.compile('rss|atom')):print('FEED',l.get('href'))
        return r.text
    except Exception as e: print('ERR',e);return ''
for name in ['Koggenland','Opmeer']:
    sec('KOOP '+name)
    for q in [f'c.product-area=="officielepublicaties" AND dt.creator=="{name}"', f'c.product-area=="officielepublicaties" AND dt.creator=="{name}" AND dt.available>=2026-09-15']:
        r=requests.get('https://repository.overheid.nl/sru',params={'operation':'searchRetrieve','version':'2.0','query':q,'maximumRecords':'3'},headers=H,timeout=60)
        print(q[-60:],r.status_code,re.findall(r'numberOfRecords>(\d+)<',r.text),re.findall(r'creator[^>]*>([^<]+)<',r.text)[:3])
KW=r'nieuws|besluit|college|raad|bekendmak|openbare|woo|agenda|vergader|rss|feed'
page('https://www.koggenland.nl/',200,KW)
page('https://www.opmeer.nl/',200,KW)
page('https://raad.koggenland.nl/',200)
page('https://raad.koggenland.nl/Vergaderingen',120)
page('https://opmeer.bestuurlijkeinformatie.nl/',120)
page('https://opmeer.bestuurlijkeinformatie.nl/Calendar',80,r'OpenCategory|Agenda/Index')
