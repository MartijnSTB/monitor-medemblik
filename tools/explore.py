import requests,re,sys
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def sec(t): print('\n'+'='*20,t,'='*20,flush=True)
SRU='https://repository.overheid.nl/sru'
def sru(q,n=1,start=1,extra=None):
    p={'operation':'searchRetrieve','version':'2.0','query':q,'maximumRecords':str(n),'startRecord':str(start)}
    if extra:p.update(extra)
    r=requests.get(SRU,params=p,headers=H,timeout=60);return r
base='c.product-area=="officielepublicaties" AND dt.creator=="Medemblik"'
for q in [base, base+' AND dt.available>=2026-01-01', base+' AND dt.available>=2026-10-01', base+' AND dt.modified>=2026-10-01']:
    sec('SRU '+q)
    try:
        r=sru(q);t=r.text
        print(r.status_code,'numberOfRecords',re.findall(r'numberOfRecords>(\d+)<',t),'next',re.findall(r'nextRecordPosition>(\d+)<',t))
        d=re.findall(r'<[^>]*diagnostic[^>]*>.*?</[^>]*diagnostic>',t,re.S);print('diag',d[:1])
    except Exception as e: print('ERR',e)
sec('SRU eerste record volledig')
r=sru(base);print(r.text[:6000])
sec('SRU sortKeys test')
for sk in ['dt.available,,0','dt.available']:
    try:
        r=sru(base,3,extra={'sortKeys':sk});print(sk,r.status_code,re.findall(r'available>([^<]+)<',r.text)[:3],re.findall(r'diagnostic.{0,300}',r.text,re.S)[:1])
    except Exception as e: print('ERR',e)
sec('SRU 1000 test')
try:
    r=sru(base,1000);print(r.status_code,len(r.content),'records',r.text.count('recordData>')//2)
    av=sorted(re.findall(r'available>(\d{4}-\d{2}-\d{2})',r.text));print('oudste',av[:2],'nieuwste',av[-2:])
    print('types',sorted(set(re.findall(r'<dcterms:type[^>]*>([^<]+)<',r.text)))[:20])
except Exception as e: print('ERR',e)

IB='https://medemblik.bestuurlijkeinformatie.nl'
def page(url,maxlinks=120):
    sec(url)
    try:
        r=requests.get(url,headers=H,timeout=40);print(r.status_code,r.headers.get('Content-Type'),len(r.content))
        s=BeautifulSoup(r.text,'html.parser')
        for t in s(['script','style']):t.decompose()
        for h in s.find_all(['h1','h2','h3'])[:40]:print(h.name,'|',re.sub(r'\s+',' ',h.get_text(' ',strip=True))[:100])
        seen=set()
        for a in s.find_all('a',href=True):
            hr=a['href']
            if hr in seen or hr.startswith('#') or 'javascript' in hr:continue
            seen.add(hr);print('A',re.sub(r'\s+',' ',a.get_text(' ',strip=True))[:80],'->',hr[:140])
            if len(seen)>maxlinks:break
        return s,r.text
    except Exception as e: print('ERR',e);return None,''
page(IB+'/')
page(IB+'/Calendar')
page(IB+'/Reports')
s,t=page(IB+'/Agenda/Index/d4b32282-6d07-4f2e-9463-89fb9b55e9c3',200)
sec('agenda html snippet');i=t.find('ocument');print(t[max(0,i-3000):i+3000])
s,t=page(IB+'/Reports/Item/78aba77b-4fb2-4210-b19b-f3034d2a5bc7')
sec('report item html');m=t.find('Datum vraag');print(t[max(0,m-1500):m+2500])
s,t=page(IB+'/Reports/Details/raadsvragen')
page('https://www.medemblik.nl/nieuws',60)
