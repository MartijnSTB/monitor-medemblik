import requests
for u in ['https://martijn-media.nl/monitor/koggenland.php?pad=/', 'https://www.martijn-media.nl/monitor/koggenland.php?pad=/']:
    try:
        r = requests.get(u, headers={'X-Monitor-Key': 'fout'}, timeout=30, allow_redirects=False)
        print(u, r.status_code, r.headers.get('location'), r.text[:200])
    except Exception as e: print(u, e)
