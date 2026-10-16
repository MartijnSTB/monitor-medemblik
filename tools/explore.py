import requests, xml.etree.ElementTree as ET, urllib.parse, collections
H={'User-Agent':'Mozilla/5.0 (Gemeentemonitor; journalistiek onderzoek)'}
print('== BAG-woonplaatsen per gemeente (PDOK) ==')
for g in ['Medemblik','Koggenland','Opmeer']:
    r=requests.get('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free',params={'q':'*','fq':['type:woonplaats',f'gemeentenaam:"{g}"'],'rows':50,'fl':'woonplaatsnaam,gemeentenaam'},headers=H,timeout=30)
    print(g, r.status_code, sorted(d['woonplaatsnaam'] for d in r.json()['response']['docs']))
print()
print('== Google Nieuws RSS ==')
def gn(q):
    u='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'nl','gl':'NL','ceid':'NL:nl'})
    r=requests.get(u,headers=H,timeout=30)
    print('\nQ:',q,'|',r.status_code,len(r.content),'bytes', r.headers.get('content-type'))
    if r.status_code!=200: print(r.text[:300]); return
    root=ET.fromstring(r.content); items=root.findall('./channel/item')
    print(len(items),'items')
    src=collections.Counter(i.findtext('source') for i in items); print('bronnen:',src.most_common(12))
    for i in items[:8]:
        print(' -',i.findtext('pubDate'),'|',i.findtext('title')[:110],'|',i.findtext('link')[:70], '| guid', (i.findtext('guid') or '')[:40])
for q in ['Medemblik when:7d','Koggenland OR Avenhorn OR "De Goorn" OR Obdam OR Spierdijk when:7d','Opmeer OR Spanbroek OR Hoogwoud when:7d','"Berkhout" when:7d','Twisk when:7d']:
    gn(q)
