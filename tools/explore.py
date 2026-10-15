import requests,re,json,html
from bs4 import BeautifulSoup
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def report(base,rid):
    print('\n=====',base,rid)
    s=requests.Session();s.headers.update(H)
    p=s.get(f'{base}/Reports/Details/{rid}',timeout=40)
    cols=json.loads(html.unescape(re.search(r"data-columns='([^']+)'",p.text).group(1)));print('cols',cols)
    tok=re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',p.text);print('token',bool(tok))
    data={'draw':'1','start':'0','length':'5','order[0][column]':'0','order[0][dir]':'desc','search[value]':'','search[regex]':'false'}
    for i,c in enumerate(cols):
        data.update({f'columns[{i}][data]':c['data'],f'columns[{i}][name]':c.get('name',c['data']),f'columns[{i}][searchable]':'true',f'columns[{i}][orderable]':'true',f'columns[{i}][search][value]':'',f'columns[{i}][search][regex]':'false'})
    if tok: data['__RequestVerificationToken']=tok.group(1)
    r=s.post(f'{base}/Reports/GetReportData/{rid}',data=data,headers={'X-Requested-With':'XMLHttpRequest','Referer':f'{base}/Reports/Details/{rid}'},timeout=40)
    print(r.status_code,r.headers.get('Content-Type'),r.text[:1500])
report('https://opmeer.bestuurlijkeinformatie.nl','e90d2554-7a8b-4254-a9c1-fba22e8d67b3')
report('https://medemblik.bestuurlijkeinformatie.nl','b6e30d37-cfd2-4064-a7fa-19453570dfb5')
report('https://medemblik.bestuurlijkeinformatie.nl','55a67657-751b-488f-938d-31c4a7f557b4')
