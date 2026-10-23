import requests, re, json
H = {'User-Agent': 'AlkmaarPublicatieMonitor/0.1 (public information monitoring)'}
B = 'https://alkmaar.bestuurlijkeinformatie.nl'
for tid in (100148034, 100050619):
    r = requests.get(B + '/Agenda/RetrieveAgendasForYear', params={'agendatypeId': tid, 'year': 2026}, headers=H, timeout=30)
    labels = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', l)).strip() for l in re.findall(r'/Agenda/Index/[^"]*"[^>]*>(.*?)</a>', r.text, re.S)]
    print(tid, r.status_code, len(labels), labels[:5])
r = requests.post(B + '/Reports/GetReportData', data={'reportId': 'a1132f05-4b54-4451-920d-195043a20824', 'draw': 1, 'start': 0, 'length': 5}, headers=H, timeout=30)
print('report', r.status_code, r.text[:600])
p = requests.get(B + '/Reports/Details/a1132f05-4b54-4451-920d-195043a20824', headers=H, timeout=30)
print('details', p.status_code, re.sub(r'\s+', ' ', p.text[p.text.find('<table'):p.text.find('<table')+1500]))
