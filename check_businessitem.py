import requests
r = requests.get('https://api.parliament.uk/odata/BusinessItem', params={
    '$filter': "contains(tolower(title), 'division')",
    '$top': 10,
    '$select': 'id,title,date,description'
})
print('BusinessItem:', r.status_code)
print(r.text[:3000])