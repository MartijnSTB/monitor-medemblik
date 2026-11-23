import requests, re
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://gemeenteraad.enkhuizen.nl'
t = requests.get(B + '/Overzichten/Raadsbrief', headers=H, timeout=30).text
srcs = re.findall(r'<script[^>]+src="([^"]+)"', t); print('scripts:', srcs)
for s in re.findall(r'<script(?![^>]*src)[^>]*>([\s\S]*?)</script>', t):
    if re.search(r'fetch|ajax|url|endpoint|search', s, re.I): print('INLINE:', re.sub(r'\s+', ' ', s)[:1200])
i = t.find('mt-list-overview'); print('AROUND:', re.sub(r'\s+', ' ', t[i-300:i+2500]))
for src in srcs:
    if 'opensearch' in src or 'overview' in src.lower() or 'list' in src.lower():
        js = requests.get(B + src if src.startswith('/') else src, headers=H, timeout=30).text
        print('JS', src, len(js), sorted(set(re.findall(r'["\'`](/[A-Za-z][^"\'`\s]{3,80})["\'`]', js)))[:30])
