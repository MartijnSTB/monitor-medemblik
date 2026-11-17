import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
t = requests.get('https://www.drechterland.nl/actueel/', headers=H, timeout=30).text
links = re.findall(r'href="(https://www\.drechterland\.nl/actueel/[^"#?]+)"', t)
print(len(links), links[:12])
i = t.find(links[0]) if links else -1
print(re.sub(r'\s+', ' ', t[i-1500:i+1200]))
print('time tags:', re.findall(r'<time[^>]*>[^<]*</time>', t)[:5])
print('pagination:', re.findall(r'href="([^"]*actueel/page/\d+[^"]*)"', t)[:3])
