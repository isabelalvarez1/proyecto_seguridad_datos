import urllib.request, json

for ep in ['homicidios/anual', 'provincias', 'desapariciones/anual', 'armas/anual', 'defunciones/anual']:
    r = urllib.request.urlopen(f'http://localhost:8000/{ep}')
    data = json.loads(r.read())
    print(f'/{ep}: type={type(data).__name__}, len={len(data)}')
    if data:
        print(f'  keys={list(data[0].keys())}')
        print(f'  first={data[0]}')
    print()
