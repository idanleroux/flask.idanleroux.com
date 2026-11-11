import requests
r = requests.get('https://api.parliament.uk/odata/$metadata')
import xml.etree.ElementTree as ET
root = ET.fromstring(r.content)
ns = {'edm': 'http://docs.oasis-open.org/odata/ns/edm'}
for container in root.findall('.//edm:EntityContainer', ns):
    for entity_set in container.findall('edm:EntitySet', ns):
        name = entity_set.get('Name', '')
        print(f'EntitySet: {name}')