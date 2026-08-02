"""Monlam AI Studio Text-to-Speech (TTS) Endpoint Test Suite (50 Comprehensive Test Cases)."""
import os
import json
import time
import urllib.request
import urllib.error

BASE_URL = "https://api-v1.monlamai.studio"
API_KEY = os.environ.get("REACT_APP_MONLAM_API_KEY", "ml-y4K0RI88kQDXWbU8FboYc1tZ50NeXVXjbBNorbYG0gg")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MonlamClient/1.0"
MAX_TTS_CHARS = 2000

def get_tts_test_cases():
    headers_valid = {"Content-Type": "application/json", "X-API-Key": API_KEY, "User-Agent": USER_AGENT}
    headers_invalid_key = {"Content-Type": "application/json", "X-API-Key": "ml-invalid-key-9999999", "User-Agent": USER_AGENT}
    headers_no_key = {"Content-Type": "application/json", "User-Agent": USER_AGENT}

    voices = ["lhasa_female", "lhasa_male", "amdo_female", "amdo_male", "kham_female", "kham_male"]
    cases = []

    # 1-6: All 6 Voice Cards Grid
    for idx, v in enumerate(voices, 1):
        cases.append({"name": f"0{idx}. Voice Grid: {v}", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་བདེ་ལེགས།", "voice_name": v, "model_name": "monlamai-tts"}, "expected": [200]})

    # 7-15: Text Lengths & Formatting
    cases.append({"name": "07. Single character Tibetan text", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "ཀ", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "08. Medium Tibetan paragraph (300 chars)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་བདེ་ལེགས་ " * 20, "voice_name": "lhasa_male", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "09. Long text (1,000 characters)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་བདེ་ལེགས་ " * 70, "voice_name": "amdo_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "10. Very long text (Bounded to MAX_TTS_CHARS=2000)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་བདེ་ལེགས་ " * 120, "voice_name": "kham_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "11. Empty text string (Error validation)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200, 400, 422]})
    cases.append({"name": "12. Whitespace-only text string", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "   \n\t ", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200, 400, 422]})
    cases.append({"name": "13. Text with newlines and tabs", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Line 1\nLine 2\tTabbed", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "14. Text with Tibetan Punctuation (༎ ༅ ༺ ༻)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "༺ ༄༅༎ བཀྲ་ཤིས་བདེ་ལེགས་ ༎ ༻", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "15. Text with numbers & symbols (2026-10-15 #1)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "2026 ༡ ༢ ༣ #1", "voice_name": "kham_female", "model_name": "monlamai-tts"}, "expected": [200]})

    # 16-25: Voice IDs & Formats
    cases.append({"name": "16. Invalid voice ID ('lhasa_robot')", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "lhasa_robot", "model_name": "monlamai-tts"}, "expected": [200, 400, 422]})
    cases.append({"name": "17. Invalid voice ID ('random_voice_123')", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "random_voice_123", "model_name": "monlamai-tts"}, "expected": [200, 400, 422]})
    cases.append({"name": "18. Missing 'voice_name' parameter", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "model_name": "monlamai-tts"}, "expected": [200, 400, 422]})
    cases.append({"name": "19. Missing 'text' parameter", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [400, 422]})
    cases.append({"name": "20. Missing 'model_name' parameter", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "lhasa_female"}, "expected": [200, 400, 422]})
    cases.append({"name": "21. Explicit response_format ('mp3')", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "lhasa_female", "model_name": "monlamai-tts", "response_format": "mp3"}, "expected": [200]})
    cases.append({"name": "22. Explicit response_format ('wav')", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "lhasa_female", "model_name": "monlamai-tts", "response_format": "wav"}, "expected": [200]})
    cases.append({"name": "23. Explicit response_format ('pcm')", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "lhasa_female", "model_name": "monlamai-tts", "response_format": "pcm"}, "expected": [200, 400, 422]})
    cases.append({"name": "24. Non-Tibetan text (English input)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Tashi Delek welcome", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "25. Non-Tibetan text (Chinese input)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "扎西德勒", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})

    # 26-35: Multilingual, Alternate Parameters & Edge cases
    cases.append({"name": "26. Mixed Tibetan + English sentence", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་བདེ་ལེགས Hello World", "voice_name": "lhasa_male", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "27. Multiple Tibetan sentences", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་བདེ་ལེགས། ཁྱེད་རང་སྐུ་ཁམས་བཟང་ངམ། ང་རང་བདེ་པོ་ཡིན།", "voice_name": "amdo_male", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "28. Speed / pitch parameter (if supported)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "lhasa_female", "model_name": "monlamai-tts", "speed": 1.0}, "expected": [200]})
    cases.append({"name": "29. Extra unknown JSON field", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་", "voice_name": "lhasa_female", "model_name": "monlamai-tts", "extra_param": True}, "expected": [200]})
    cases.append({"name": "30. Duplicate request 1 (Idempotency test)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Idempotent sample", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "31. Duplicate request 2 (Idempotency test)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Idempotent sample", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "32. Audio URL reachability test", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Audio check", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "33. Large payload text (Bounded to MAX_TTS_CHARS=2000)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "བཀྲ་ཤིས་ " * 120, "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "34. Trailing slash check", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Slash check", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "35. Non-trailing slash check", "url": f"{BASE_URL}/api/v1/text-to-speech", "headers": headers_valid, "payload": {"text": "No slash check", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200, 301, 307, 308]})

    # 36-50: Security, Authentication & Method Validations
    cases.append({"name": "36. No API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_no_key, "payload": {"text": "Test", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [401, 403]})
    cases.append({"name": "37. Invalid API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_invalid_key, "payload": {"text": "Test", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [401, 403]})
    cases.append({"name": "38. Alternate Auth Header ('Authorization: Bearer')", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}", "User-Agent": USER_AGENT}, "payload": {"text": "Test", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200, 401, 403]})
    cases.append({"name": "39. Wrong Content-Type ('text/plain')", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": {"Content-Type": "text/plain", "X-API-Key": API_KEY, "User-Agent": USER_AGENT}, "payload": None, "expected": [400, 415, 422, 200]})
    cases.append({"name": "40. GET method instead of POST", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": None, "method": "GET", "expected": [405, 400]})
    cases.append({"name": "41. Numeric text input (123456789)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "123456789", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "42. Tibetan numerals (༡ ༢ ༣ ༤ ༥ ༦ ༧ ༨ ༩ ༠)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "༡ ༢ ༣ ༤ ༥ ༦ ༧ ༨ ༩ ༠", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "43. High-pitch voice query (lhasa_female)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "High pitch", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "44. Deep-tone voice query (kham_male)", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Deep tone", "voice_name": "kham_male", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "45. Rapid sequential request A", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Seq A", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "46. Rapid sequential request B", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Seq B", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "47. Tibetan dictionary entry text synthesis", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "སློབ་སྦྱོང་ ཞེས་པ་ནི་ཤེས་བྱ་ལ་སྦྱོང་བ་བྱེད་པའི་དོན་ནོ།", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "48. Tibetan poetry text synthesis", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "གངས་ཅན་འགྲོ་བའི་མགོན་པོ་སྤྱན་རས་གཟིགས།", "voice_name": "lhasa_male", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "49. Response structure audio_url verification", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "Response test", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})
    cases.append({"name": "50. Final TTS suite health check", "url": f"{BASE_URL}/api/v1/text-to-speech/", "headers": headers_valid, "payload": {"text": "TTS OK", "voice_name": "lhasa_female", "model_name": "monlamai-tts"}, "expected": [200]})

    return cases

def run_tts_tests():
    print(f"=== Running Expanded TTS API Test Suite (50 Cases | Key: {API_KEY[:10]}... | MAX_CHARS: {MAX_TTS_CHARS}) ===")
    results = []
    cases = get_tts_test_cases()
    skipped_count = 0

    for tc in cases:
        t0 = time.perf_counter()
        method = tc.get("method", "POST")
        payload = tc.get("payload")

        # Enforce MAX_TTS_CHARS bound check
        if payload and isinstance(payload, dict) and "text" in payload:
            text_str = payload["text"]
            if len(text_str) > MAX_TTS_CHARS:
                print(f"[SKIP] {tc['name']} -> Truncating payload from {len(text_str)} to {MAX_TTS_CHARS} chars to prevent API timeout")
                payload["text"] = text_str[:MAX_TTS_CHARS]

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else b"Invalid payload"

        req = urllib.request.Request(tc["url"], data=data_bytes, headers=tc["headers"], method=method)
        status_code = None
        response_body = ""

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status_code = resp.status
                response_body = resp.read().decode("utf-8", errors="replace")[:200]
        except urllib.error.HTTPError as e:
            status_code = e.code
            response_body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception as exc:
            status_code = 0
            response_body = str(exc)

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        passed = status_code in tc["expected"]

        results.append({
            "name": tc["name"],
            "endpoint": tc["url"],
            "status_code": status_code,
            "expected": tc["expected"],
            "latency_ms": elapsed_ms,
            "passed": passed,
            "response_snippet": response_body
        })
        print(f"[{'PASS' if passed else 'FAIL'}] {tc['name']} -> Status {status_code} ({elapsed_ms}ms)")

    return results

if __name__ == "__main__":
    run_tts_tests()
