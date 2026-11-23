import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://gemeenteraad.enkhuizen.nl'
js = requests.get(B + '/site/default2020/script/MeetingTools/MeetingTools.js', headers=H, timeout=30).text
i = js.find('this.query'); print(re.sub(r'\s+', ' ', js[i:i+1800]))
for m in re.finditer(r'this\.init|reload\(\)', js): print('...', re.sub(r'\s+', ' ', js[m.start():m.start()+300]))
for q in ['?sortorder=ingediend&dir=aflopend&page=1', '?page=1', '?sort=ingediend&order=aflopend']:
    for hd in ({}, {'X-Requested-With': 'XMLHttpRequest'}):
        t = requests.get(B + '/Overzichten/Raadsbrief' + q, headers={**H, **hd}, timeout=30).text
        items = re.findall(r'<li[^>]*>\s*<a[^>]+href="([^"]+)"', t[t.find('id="mtOverview"'):])
        print(q, hd, len(t), 'items', len(items), items[:3])
