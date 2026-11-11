import requests
import re

r = requests.get('https://www2.census.gov/geo/tiger/TIGER2024/CD/')
for match in re.findall(r'href="([^"]+)"', r.text):
    if 'cd119' in match.lower() and not match.startswith('tl_2024_'):
        print(match)