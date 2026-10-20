import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for gem in ['Medemblik', 'Opmeer']:
    q = f'c.product-area==officielepublicaties AND dt.creator=="{gem}" AND dt.title="Reglement van orde"'
    r = requests.get('https://repository.overheid.nl/sru', params={'query': q, 'maximumRecords': 30, 'sortKeys': 'dt.modified,,0'}, headers=H, timeout=40)
    print('==', gem, re.findall(r'numberOfRecords>(\d+)', r.text))
    recs = re.findall(r'<dcterms:identifier>([^<]+)</dcterms:identifier><dcterms:title>([^<]+)</dcterms:title>.*?<dcterms:modified>([^<]+)<', r.text, re.S)
    for i, t, d in recs: print('  ', d, i, t[:120])
    urls = re.findall(r'<gzd:itemUrl manifestation="xml">([^<]+)</gzd:itemUrl>', r.text)
    done = 0
    for (i, t, d), u in zip(recs, urls):
        if re.search(r'reglement van orde', t, re.I) and re.search(r'raad', t, re.I) and not re.search(r'commissie|rekenkamer|wijziging', t, re.I):
            x = requests.get(u, headers=H, timeout=40).text
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', x))
            hits = [m.start() for m in re.finditer(r'[Ss]chriftelijke vragen', txt)]
            for h in hits:
                seg = txt[h:h+1600]
                if re.search(r'binnen (\w+) (dagen|weken|werkdagen)', seg):
                    print('     >>', d, i, '::', seg); done += 1; break
            if done >= 2: break
