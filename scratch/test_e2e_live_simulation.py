"""Live E2E Integration and API Connectivity Verification Script."""
import os
import sys
import urllib.request
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from teea.engine import TEEAEngine

def test_local_engine():
    print("--- 1. Testing Local TEEA Engine (/analyze) ---")
    engine = TEEAEngine()
    test_text = "སློབ་སྦྱང"
    result = engine.analyze(test_text)
    print(f"Suggestions count: {len(result.suggestions)}")
    for s in result.suggestions:
        print(f" - Plugin: {s.source}, Priority: {s.priority}, Replacement: {s.replacement!r}")
    assert len(result.suggestions) > 0, "Engine should detect unknown Tibetan word"
    print("Local engine check: PASSED\n")

def test_monlam_api():
    print("--- 2. Testing Monlam AI Studio API Connectivity ---")
    api_key = os.environ.get("REACT_APP_MONLAM_API_KEY", "ml-y4K0RI88kQDXWbU8FboYc1tZ50NeXVXjbBNorbYG0gg")
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MonlamClient/1.0"
    
    # LLM Chat API Test
    url_chat = "https://api-v1.monlamai.studio/api/v1/ai/chat"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "User-Agent": user_agent
    }
    payload_chat = {
        "model_name": "melong",
        "messages": [
            {"role": "system", "content": "You are a Tibetan assistant."},
            {"role": "user", "content": "Hello"}
        ]
    }
    req = urllib.request.Request(url_chat, data=json.dumps(payload_chat).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"Monlam Chat API Status: {resp.status}")
            print(f"Monlam Chat Response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    except Exception as e:
        print(f"Monlam Chat API Warning/Error: {e}")

    # TTS API Test
    url_tts = "https://api-v1.monlamai.studio/api/v1/text-to-speech/"
    payload_tts = {
        "text": "བཀྲ་ཤིས་བདེ་ལེགས།",
        "voice_name": "lhasa_female",
        "model_name": "monlamai-tts",
        "response_format": "mp3"
    }
    req_tts = urllib.request.Request(url_tts, data=json.dumps(payload_tts).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req_tts, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"Monlam TTS API Status: {resp.status}")
            print(f"Monlam TTS Response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    except Exception as e:
        print(f"Monlam TTS API Warning/Error: {e}")

if __name__ == "__main__":
    test_local_engine()
    test_monlam_api()
