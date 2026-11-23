import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://gemeenteraad.enkhuizen.nl'
for src in ['/site/default2020/script/MeetingTools/MeetingTools.js', '/site/default2020/script/MeetingTools/_global.js']:
    js = requests.get(B + src, headers=H, timeout=30).text
    print('JS', src, len(js))
    for m in re.finditer(r'(fetch|\$\.(?:ajax|get|post|getJSON)|url\s*:)', js):
        print('   ', re.sub(r'\s+', ' ', js[max(0, m.start()-200):m.start()+400]))
    print('   paden:', sorted(set(re.findall(r'["\'`](/[A-Za-z][^"\'`\s]{3,80})["\'`]', js))))
