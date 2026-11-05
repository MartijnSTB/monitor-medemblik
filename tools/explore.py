import os, re, requests
K = os.environ.get('KOGGENLAND_PROXY_KEY', '')
print('sleutel aanwezig:', bool(K), len(K))
P = 'https://martijn-media.nl/monitor/koggenland.php'
def get(pad):
    r = requests.get(P, params={'pad': pad}, headers={'X-Monitor-Key': K}, timeout=60)
    return r
for pad in ['/', '/vergaderingen', '/Vergaderingen', '/calendar', '/agenda']:
    r = get(pad)
    t = r.text
    print('==', pad, r.status_code, r.headers.get('content-type'), len(t), 'ANUBIS' if 'anubis' in t.lower() else '')
    if pad == '/' or r.status_code == 200:
        print('  title:', (re.findall(r'<title>(.*?)</title>', t, re.S) or [''])[0].strip()[:120])
        print('  generator/meta:', re.findall(r'<meta[^>]+(?:generator|author)[^>]*>', t)[:3])
        hrefs = sorted(set(re.findall(r'href="(/[^"#]{2,80})"', t)))
        print('  links:', hrefs[:60])
        print('  scripts:', re.findall(r'<script[^>]+src="([^"]+)"', t)[:8])
