import requests
H={'User-Agent':'MedemblikPublicatieMonitor/0.1 (public information monitoring)'}
for q in ['Kerkebuurt 149 1647MD','Duinweid 10 1713GE','Het Bon 68 1687TB']:
    r=requests.get('https://api.pdok.nl/bzk/locatieserver/search/v3_1/free',params={'q':q,'fq':'type:adres','rows':1,'fl':'weergavenaam,centroide_ll,woonplaatsnaam,gemeentenaam'},headers=H,timeout=30)
    print(q,r.status_code,r.json().get('response',{}).get('docs'))
