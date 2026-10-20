import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for gem in ['Medemblik', 'Opmeer']:
    for q in [f'c.product-area==cvdr AND dt.creator=="{gem}" AND dt.title="Reglement van orde"',
              f'c.product-area==cvdr AND dt.creator=="{gem}" AND Reglement']:
        r = requests.get('https://repository.overheid.nl/sru', params={'query': q, 'maximumRecords': 20}, headers=H, timeout=40)
        print('==', q, r.status_code, re.findall(r'numberOfRecords>(\d+)', r.text), r.text[:300] if r.status_code != 200 else '')
        titles = re.findall(r'<dcterms:title>([^<]+)</dcterms:title>', r.text)
        urls = re.findall(r'<gzd:itemUrl manifestation="xml">([^<]+)</gzd:itemUrl>', r.text)
        for t, u in zip(titles, urls): print('  ', t[:110], u)
        for t, u in zip(titles, urls):
            if re.search(r'reglement van orde.*raad', t, re.I):
                x = requests.get(u, headers=H, timeout=40).text
                txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', x))
                for m in re.finditer(r'[Ss]chriftelijke vragen', txt):
                    seg = txt[m.start():m.start()+1500]
                    if re.search(r'binnen \w+ (dagen|weken)', seg):
                        print('     >>', t[:80], '::', seg[:1500]); break
                break
        if titles: break
