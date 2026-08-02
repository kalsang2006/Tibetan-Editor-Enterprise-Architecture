import urllib.request
import urllib.parse
import json

API_KEY = "ml-y4K0RI88kQDXWbU8FboYc1tZ50NeXVXjbBNorbYG0gg"
BASE = "https://api-v1.monlamai.studio/api/v1/dictionary/search"

queries = ["སློབ་སྦྱང", "སློབ་སྦྱོང"]

for q in queries:
    for pair in ["bo-en", "bo-bo"]:
        url = f"{BASE}?pair={urllib.parse.quote(pair)}&q={urllib.parse.quote(q)}"
        req = urllib.request.Request(url, headers={"X-API-Key": API_KEY})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            body = {"error": str(e)}
        print(q, pair, json.dumps(body, ensure_ascii=False))
