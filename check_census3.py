import requests
import re

for year in [2022, 2023, 2024]:
    r = requests.get(f'https://www2.census.gov/geo/tiger/TIGER{year}/CD/')
    for match in re.findall(r'href="([^"]+)"', r.text):
        if 'cd118' in match.lower() and not match.startswith('tl_'):
            print(f'{year}: {match}')