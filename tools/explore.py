import os, re, requests
K = os.environ.get('KOGGENLAND_PROXY_KEY', '')
P = 'https://martijn-media.nl/monitor/koggenland.php'
def get(pad): return requests.get(P, params={'pad': pad}, headers={'X-Monitor-Key': K}, timeout=60)
sq = lambda t: re.sub(r'\s+', ' ', t)
t = get('/Vergaderingen/Gemeenteraad/2026/09-november/19:30').text
i = t.find('/Documenten/01-01-Memo')
print('== rond eerste document:\n', sq(t[i-3500:i+900]))
j = t.find('/Documenten/04-02a')
print('\n== rond 04-02a:\n', sq(t[j-1200:j+500]))
for pad in ['/Vergaderingen/Gemeenteraad/2026', '/documenten/Moties-en-amendementen', '/documenten/Memo-s-en-afdoeningen-van-college']:
    r = get(pad); t = r.text
    print('\n==', pad, r.status_code, len(t))
    k = max(t.find('<main'), t.find('id="content"'))
    links = re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', t, re.S)
    rel = [(h, sq(re.sub(r'<[^>]+>', ' ', x)).strip()[:90]) for h, x in links if re.search(r'Vergaderingen/.+/20\d\d/|Documenten/|documenten/', h)]
    for h, x in rel[:25]: print('   ', h[:110], '|', x)
    m = t.find('<table'); 
    if m > 0: print('  table:', sq(t[m:m+1500]))
