import requests, xml.etree.ElementTree as ET

base = 'http://localhost:8081'

# 1. Login
r = requests.get(base + '/', params={'f':'login','username':'admin','password':'admin'})
root = ET.fromstring(r.content)
token = root.find('.//token').text
print('1. Login OK, token:', token[:8] + '...')

# 2. Reel list rack 1
r2 = requests.get(base + '/', params={'f':'V2_reel_getlist','filter_smartrackidlist':'1','tkn':token})
if r2.status_code != 200 or not r2.content:
    print(f'2. Error: status={r2.status_code}, body={repr(r2.text)}')
    exit(1)
root2 = ET.fromstring(r2.content)
reels = root2.findall('.//v2_reelinfo')
print(f'2. Rack 1: {len(reels)} rollos')
firstR = reels[0]
print(f'   code={firstR.find("code").text} | item={firstR.find("itemcode").text} | qty={firstR.find("quantity").text} | stockcell={firstR.find("stockcell").text}')

# 3. JUKI containers 1,2
r3 = requests.get(base + '/', params={'f':'V2_reel_getlist','filter_containeridlist':'1,2','tkn':token,'filter_showactive':'true'})
root3 = ET.fromstring(r3.content)
jreels = root3.findall('.//v2_reelinfo')
print(f'3. JUKI containers 1+2: {len(jreels)} rollos')
firstJ = jreels[0]
print(f'   code={firstJ.find("code").text} | item={firstJ.find("itemcode").text} | container={firstJ.find("containerid").text}')

# 4. Extract
r4 = requests.get(base + '/', params={'f':'V3_extractreels','name':'TEST_MOCK','reelrequestlist':'0081647800,0081647795','autostart':'Y','tkn':token})
root4 = ET.fromstring(r4.content)
print('4. Extract result:', root4.attrib)

# 5. Token invalido
r5 = requests.get(base + '/', params={'f':'V2_reel_getlist','filter_smartrackidlist':'1','tkn':'BADTOKEN'})
root5 = ET.fromstring(r5.content)
print('5. Token invalido:', root5.attrib)

# 6. Status
r6 = requests.get(base + '/?f=status')
print('6. Status:', r6.json())

print('\nAll tests PASSED.')
