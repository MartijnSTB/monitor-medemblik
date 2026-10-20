import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', requests.get('https://repository.overheid.nl/frbr/officielepublicaties/gmb/2023/gmb-2023-200047/1/xml/gmb-2023-200047.xml', headers=H, timeout=40).text))
for m in re.finditer(r'(?i)vragen', txt):
    s = txt[max(0, m.start()-100):m.start()+700]
    if re.search(r'(?i)artikel|termijn|binnen|weken|dagen', s): print('>>', s, '\n')
r = requests.get('https://repository.overheid.nl/sru', params={'query': 'c.product-area==officielepublicaties AND dt.creator=="Medemblik" AND (vragenrecht OR "schriftelijke vragen")', 'maximumRecords': 10}, headers=H, timeout=40)
print(re.findall(r'<dcterms:identifier>([^<]+)</dcterms:identifier><dcterms:title>([^<]+)</dcterms:title>', r.text))
