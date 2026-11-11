import requests
r = requests.get('https://api.parliament.uk/odata/$metadata')
import xml.etree.ElementTree as ET
root = ET.fromstring(r.content)
ns = {'edm': 'http://docs.oasis-open.org/odata/ns/edm'}
for entity in root.findall('.//edm:EntityType', ns):
    name = entity.get('Name', '')
    if 'Div' in name or 'Vote' in name or 'Teller' in name:
        print(f'EntityType: {name}')

for container in root.findall('.//edm:EntityContainer', ns):
    for entity_set in container.findall('edm:EntitySet', ns):
        name = entity_set.get('Name', '')
        if 'Div' in name or 'Vote' in name or 'Teller' in name:
            print(f'EntitySet: {name}')