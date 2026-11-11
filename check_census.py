import requests
import re

r = requests.get('https://www2.census.gov/geo/tiger/TIGER2023/CD/')
for match in re.findall(r'href="([^"]+)"', r.text):
    if '119' in match or 'cd119' in match.lower():
        print(match)

r2 = requests.get('https://www2.census.gov/geo/tiger/TIGER2024/CD/')
for match in re.findall(r'href="([^"]+)"', r2.text):
    if '119' in match or 'cd119' in match.lower():
        print(match)