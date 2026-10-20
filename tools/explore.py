import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for gem in ['Medemblik', 'Opmeer', 'Koggenland']:
    q = f'dcterms.creator="{gem}" and dcterms.title="Reglement van orde" and dcterms.title="raad"'
    try:
        r = requests.get('https://zoekservice.overheid.nl/sru/Search', params={'x-connection': 'cvdr', 'query': q, 'maximumRecords': 10}, headers=H, timeout=40)
        print('==', gem, r.status_code, re.findall(r'numberOfRecords>(\d+)', r.text))
        recs = re.findall(r'<dcterms:identifier>(CVDR[^<]+)</dcterms:identifier>.*?<dcterms:title>([^<]+)</dcterms:title>', r.text, re.S)
        for ident, title in recs: print('  ', ident, title)
        ups = re.findall(r'<publicatieurl_xml>([^<]+)</publicatieurl_xml>', r.text) or re.findall(r'https://repository\.officiele-overheidspublicaties\.nl/cvdr/[^<"]+\.xml', r.text)
        print('   urls', ups[:5])
        # take entries whose title is reglement van orde voor de vergaderingen van de raad; fetch latest
        for u in ups[:4]:
            t = requests.get(u, headers=H, timeout=40).text
            title = (re.findall(r'<citeertitel[^>]*>([^<]+)', t) or re.findall(r'<titel[^>]*>([^<]+)', t) or [''])[0]
            txt = re.sub(r'<[^>]+>', ' ', t); txt = re.sub(r'\s+', ' ', txt)
            print('   --', u, title[:100])
            for m in re.finditer(r'[Ss]chriftelijke vragen', txt):
                seg = txt[m.start():m.start()+1200]
                if re.search(r'binnen|dagen|weken', seg):
                    print('      ', seg[:1200]); break
    except Exception as e: print(gem, e)
