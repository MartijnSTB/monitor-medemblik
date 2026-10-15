import requests,re
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
q='c.product-area=="officielepublicaties" AND dt.creator=="Medemblik" AND dt.available>=2026-10-14'
r=requests.get('https://repository.overheid.nl/sru',params={'operation':'searchRetrieve','version':'2.0','query':q,'maximumRecords':'6'},headers=H,timeout=60)
for rec in re.findall(r'<sru:recordData>(.*?)</sru:recordData>',r.text,re.S):
    f=lambda t:(re.search(r'<[^>]*:'+t+r'[^>]*>([^<]+)<',rec) or [None,None])[1]
    print(f('identifier'),'| available',f('available'),'| issued',f('issued'),'| modified',f('modified'),'| wijzigingWork',f('datumTijdstipWijzigingWork'),'| timestamp',f('timestamp'))
r=requests.get('https://zoek.officielebekendmakingen.nl/'+re.search(r'(gmb-\d{4}-\d+)',r.text).group(1)+'.html',headers=H,timeout=40)
t=re.sub(r'<[^>]+>',' ',r.text);i=t.find('Datum publicatie');print('SITE:',re.sub(r'\s+',' ',t[i:i+200]))
x=requests.get('https://www.medemblik.nl/nieuws.rss',headers=H,timeout=30).text
print('MED RSS pubDates:',re.findall(r'<pubDate>\s*([^<]+?)\s*</pubDate>',x)[:3])
