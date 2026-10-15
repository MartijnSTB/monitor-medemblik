import requests,re,json,html
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
def rows(base,rid,ordercol,n=3):
    p=requests.get(f'{base}/Reports/Details/{rid}',headers=H,timeout=40)
    cols=json.loads(html.unescape(re.search(r"data-columns='([^']+)'",p.text).group(1)))
    data={'draw':'1','start':'0','length':str(n),'order[0][column]':str(ordercol),'order[0][dir]':'desc'}
    for i,c in enumerate(cols): data.update({f'columns[{i}][data]':c['data'],f'columns[{i}][name]':c.get('name',c['data']),f'columns[{i}][orderable]':'true',f'columns[{i}][searchable]':'true'})
    r=requests.post(f'{base}/Reports/GetReportData/{rid}',data=data,headers={**H,'X-Requested-With':'XMLHttpRequest'},timeout=40)
    j=r.json();print('\n==',base[8:20],rid[:8],'order',ordercol,'total',j.get('recordsTotal'))
    for row in j['data']: print('  ',{k:(str(v)[:40] if v else v) for k,v in row.items() if k in ('registrationdate','datum','datumingekomen','title','datumantwoord')})
M='https://medemblik.bestuurlijkeinformatie.nl';O='https://opmeer.bestuurlijkeinformatie.nl'
import sys
for base in (M,O):
    p=requests.get(base+'/Reports',headers=H,timeout=30).text
    for rid in dict.fromkeys(re.findall(r'/Reports/Details/([0-9a-f-]{36})',p)):
        d=requests.get(f'{base}/Reports/Details/{rid}',headers=H,timeout=30).text
        cols=json.loads(html.unescape(re.search(r"data-columns='([^']+)'",d).group(1)))
        names=[c['data'] for c in cols]
        idx=next((i for i,c in enumerate(names) if c in ('datum','datumingekomen','registrationdate')),0)
        print('\n##',re.search(r'<h1>([^<]+)',d).group(1) if re.search(r'<h1>([^<]+)',d) else rid,names,'-> sorteer op',names[idx],'| data-order',re.search(r"data-order='([^']+)'",d).group(1) if re.search(r"data-order='([^']+)'",d) else None)
        rows(base,rid,idx,2)
