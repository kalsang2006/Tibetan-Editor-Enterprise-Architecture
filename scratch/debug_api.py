import requests
import json

out = {}
res = requests.post("http://127.0.0.1:50505/api/analysis/run", json={
    "method": "analysis.run",
    "params": {"text": "བཀྲ་ཤེས་བདེ་ལེགས།"},
    "request_id": "test-1"
})
out["analysis"] = res.json()

res2 = requests.post("http://127.0.0.1:50505/api/plagiarism/check", json={
    "text": "༄༅། །བོད་སྐད་ནི་བོད་རིགས་ཀྱི་སྐད་ཡིག་ཡིན་ཞིང་། དེ་ནི་འཛམ་གླིང་སྟེང་གི་སྐད་ཡིག་རྙིང་ཤོས་ཤིག་རེད།",
    "min_similarity": 0.05
})
out["plagiarism"] = res2.json() if res2.status_code == 200 else res2.text

with open("scratch/debug_api_out.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
