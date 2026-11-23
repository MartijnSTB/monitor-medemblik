import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
sq = lambda t: re.sub(r'\s+', ' ', t)
for u in ['https://gemeenteraad.enkhuizen.nl/overzichten/raadsbrief/', 'https://gemeenteraad.drechterland.nl/Documenten/Raadsbrieven']:
    t = requests.get(u, headers=H, timeout=30).text
    i = t.find('<main'); 
    print('==', u)
    print('data-attrs:', sorted(set(re.findall(r'data-(?:url|src|source|endpoint|ajax|api)[a-z-]*="([^"]+)"', t)))[:10])
    print('json/api urls:', sorted(set(re.findall(r'["\'](/[^"\']*(?:api|json|Ajax|ajax|Search|search|Overzicht|overzicht)[^"\']*)["\']', t)))[:20])
    print('forms:', re.findall(r'<form[^>]*>', t)[:4])
    print(sq(re.sub(r'<script[\s\S]*?</script>', '', t[i:i+6000]))[:2500])
