import sys,os,json
sys.path.insert(0,os.getcwd())
import monitor as M
key='x'*64
url='https://medemblik.bestuurlijkeinformatie.nl/Reports/Item/86f6c6f9-f9e5-4d5e-bd3f-44207ef9625b'
db={'items':{key:M.new_item('medemblik','Raadsvragen GB evenementenvergunningen en toiletten',url,'Raadsportaal',kind='overzichtsitem')},'status':{}}
M.TEXT_DIR=M.ROOT/'tools'/'tmptext'
M.check_documents(db)
it=db['items'][key]
print('bijlagen:',it.get('bijlagen'))
print('text_v',it.get('text_v'),'fout',it.get('content_error'))
lines=(M.TEXT_DIR/(key[:24]+'.txt')).read_text().split('\n')
print('regels',len(lines))
for l in lines:
    if l.startswith('[Bijlage'): print('  ',l)
i=next(i for i,l in enumerate(lines) if l.startswith('[Bijlage: Beatwoording'))
print('antwoord begint:',lines[i+1:i+4])
