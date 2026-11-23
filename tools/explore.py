import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for B, pad in [('https://gemeenteraad.enkhuizen.nl', '/Overzichten/Raadsbrief'), ('https://gemeenteraad.enkhuizen.nl', '/Overzichten/Besluitenlijst'), ('https://gemeenteraad.drechterland.nl', '/Documenten/Raadsbrieven')]:
    t = requests.get(B + pad, headers=H, timeout=30).text
    i = t.find('id="mtOverview"')
    body = re.sub(r'\s+', ' ', re.sub(r'<script[\s\S]*?</script>', '', t[i:i+5000]))
    print('==', B, pad, len(t), 'idx', i); print(body[:3000]); print()
