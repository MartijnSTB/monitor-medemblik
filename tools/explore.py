import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for ident in ['gmb-2023-200047', 'gmb-2026-226516']:
    r = requests.get('https://repository.overheid.nl/sru', params={'query': f'dt.identifier=="{ident}"', 'maximumRecords': 1}, headers=H, timeout=40)
    u = re.findall(r'<gzd:itemUrl manifestation="xml">([^<]+)</gzd:itemUrl>', r.text)
    print('==', ident, u)
    if not u: continue
    txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', requests.get(u[0], headers=H, timeout=40).text))
    for m in re.finditer(r'(?i)schriftelijke vragen', txt):
        seg = txt[m.start():m.start()+1400]
        if re.search(r'binnen (\w+) (dagen|weken|werkdagen)', seg):
            print('  >>', seg); break
    else:
        for m in re.finditer(r'binnen (\w+) (dagen|weken|werkdagen)', txt): print('  ~', txt[max(0,m.start()-300):m.start()+100])
