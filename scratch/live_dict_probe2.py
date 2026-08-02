import urllib.request
import urllib.parse
import json
import time

API_KEY = "ml-y4K0RI88kQDXWbU8FboYc1tZ50NeXVXjbBNorbYG0gg"
BASE = "https://api-v1.monlamai.studio/api/v1/dictionary/search"

q = "སློབ་སྦྱང"
url = f"{BASE}?pair=bo-en&q={urllib.parse.quote(q)}"
print("URL:", url)
req = urllib.request.Request(url, headers={
    "X-API-Key": API_KEY,
    "Accept": "application/json",
    "User-Agent": "curl/8.0",
})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        print("STATUS", resp.status)
        print(resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code)
    print(e.read().decode("utf-8", errors="replace"))
