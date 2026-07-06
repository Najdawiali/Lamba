import urllib.request, json, sys

base = 'http://localhost:8000'
token_path = sys.argv[1] if len(sys.argv) > 1 else None
token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYWViNGFjYy1hOWExLTQzY2ItYWYzMS1kYjAxZGZiNzI2MTMiLCJyb2xlIjoiY3VzdG9tZXIiLCJleHAiOjE3ODMyODQyMzQsImlhdCI6MTc4MzE5NzgzNH0.9Fk_fhYfrRbB3--JLEMzbaGPTjLJgtpn2pQjIuD8jy4'

payload = {
    'query_text': 'tea',
    'latitude': 32.053742908017625,
    'longitude': 35.708763575165875,
    'filters': {'max_distance_km': 5, 'in_stock_only': True, 'city': 'As Salt'},
}

req = urllib.request.Request(
    base + '/api/v1/search/hybrid',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    method='POST',
)

try:
    r = urllib.request.urlopen(req, timeout=45)
    data = json.loads(r.read())
    print('STATUS:', r.status, '| found:', data.get('found'), '| mode:', data.get('search_mode'), '| count:', len(data.get('results', [])))
    for x in (data.get('results') or [])[:5]:
        print("  ", x['name'][:30], "score=", x['final_score'])
except urllib.error.HTTPError as e:
    print('HTTP', e.code)
    print(e.read().decode('utf-8')[:2000])