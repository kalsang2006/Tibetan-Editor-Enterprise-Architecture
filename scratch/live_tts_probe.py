import urllib.request
import json
import hashlib

API_KEY = "REPLACE_WITH_MONLAM_API_KEY"
URL = "https://api-v1.monlamai.studio/api/v1/text-to-speech/"

text = "à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼"
voices = ["lhasa_female", "lhasa_male", "amdo_female", "kham_male"]

for voice in voices:
    payload = json.dumps({"text": text, "voice_name": voice, "model_name": "monlamai-tts"}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers={
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("content-type", "")
            body = resp.read()
            if "json" in content_type:
                data = json.loads(body.decode("utf-8"))
                print(voice, "-> JSON:", json.dumps(data, ensure_ascii=False)[:300])
            else:
                h = hashlib.sha256(body).hexdigest()[:16]
                print(voice, f"-> binary {len(body)} bytes, sha256[:16]={h}, content-type={content_type}")
    except urllib.error.HTTPError as e:
        print(voice, "-> HTTP ERROR", e.code, e.read().decode("utf-8", errors="replace")[:300])
    except Exception as e:
        print(voice, "-> ERROR", e)
