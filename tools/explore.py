import requests
H = {'User-Agent': 'AlkmaarPublicatieMonitor/0.1 (public information monitoring)'}
r = requests.get('https://www.alkmaar.nl/actueel-feed', headers=H, timeout=30)
print(r.status_code, r.headers.get('content-type'))
print(r.text[:3000])
