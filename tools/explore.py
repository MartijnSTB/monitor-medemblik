import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)', 'X-Requested-With': 'XMLHttpRequest'}
for B, pad in [('https://gemeenteraad.enkhuizen.nl', '/Overzichten/Raadsbrief'), ('https://gemeenteraad.enkhuizen.nl', '/Overzichten/Besluitenlijst'),
               ('https://gemeenteraad.enkhuizen.nl', '/Overzichten/Schriftelijke-vragen'), ('https://gemeenteraad.drechterland.nl', '/Documenten/Raadsbrieven'),
               ('https://gemeenteraad.drechterland.nl', '/Documenten/Schriftelijke-vragen')]:
    r = requests.get(B + pad, params={'sorteren': 'ingediend_aflopend', 'pagina': 1}, headers=H, timeout=30)
    t = r.text
    print('==', B, pad, r.status_code, r.headers.get('content-type'), len(t))
    print(re.sub(r'\s+', ' ', t[:2500]))
