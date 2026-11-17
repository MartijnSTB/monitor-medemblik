import requests, re, json
H = {'User-Agent': 'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for slug in ('stedebroec', 'enkhuizen', 'drechterland'):
    j = requests.get(f'https://www.{slug}.nl/wp-json/wp/v2/types', headers=H, timeout=30).json()
    print('##', slug, [(k, v.get('rest_base')) for k, v in j.items()])
    base = next((v['rest_base'] for k, v in j.items() if 'actueel' in k or 'nieuws' in k or v.get('rest_base') in ('actueel', 'nieuws')), None)
    if base:
        r = requests.get(f'https://www.{slug}.nl/wp-json/wp/v2/{base}', params={'per_page': 5, '_fields': 'id,date,modified,link,title,excerpt'}, headers=H, timeout=30)
        print('  ', base, r.status_code, r.headers.get('X-WP-Total'))
        for p in r.json()[:5]: print('    ', p.get('date'), p['title']['rendered'][:70], p['link'])
        r = requests.get(f'https://www.{slug}.nl/feed/', params={'post_type': base}, headers=H, timeout=30)
        print('   feed', r.status_code, r.text.count('<item>'))
