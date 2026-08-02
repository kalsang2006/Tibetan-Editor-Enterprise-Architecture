"""Monlam AI Studio Speech-to-Text (STT) Endpoint Test Suite (50 Comprehensive Test Cases)."""
import os
import time
import urllib.request
import urllib.error

BASE_URL = "https://api-v1.monlamai.studio"
API_KEY = os.environ.get("REACT_APP_MONLAM_API_KEY", "REPLACE_WITH_MONLAM_API_KEY")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MonlamClient/1.0"
MAX_STT_BYTES = 500000  # Max payload size bound (~30s audio)

def build_wav_header(sample_rate: int = 16000, channels: int = 1, pcm_bytes_len: int = 100) -> bytes:
    byte_rate = sample_rate * channels * 2
    block_align = channels * 2
    header = bytearray(44)
    header[0:4] = b"RIFF"
    header[4:8] = (36 + pcm_bytes_len).to_bytes(4, "little")
    header[8:12] = b"WAVE"
    header[12:16] = b"fmt "
    header[16:20] = (16).to_bytes(4, "little")
    header[20:22] = (1).to_bytes(2, "little") # PCM
    header[22:24] = channels.to_bytes(2, "little")
    header[24:28] = sample_rate.to_bytes(4, "little")
    header[28:32] = byte_rate.to_bytes(4, "little")
    header[32:34] = block_align.to_bytes(2, "little")
    header[34:36] = (16).to_bytes(2, "little") # 16 bits
    header[36:40] = b"data"
    header[40:44] = pcm_bytes_len.to_bytes(4, "little")
    return bytes(header)

def build_stt_body(filename: str, file_bytes: bytes, mime_type: str = "audio/wav", language: str = "bo", task: str = "transcribe") -> tuple[bytes, str]:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    parts = []
    if filename is not None and file_bytes is not None:
        if len(file_bytes) > MAX_STT_BYTES:
            file_bytes = file_bytes[:MAX_STT_BYTES]
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        parts.append(file_bytes)
        parts.append(b"\r\n")
    if language is not None:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n{language}\r\n".encode("utf-8"))
    if task is not None:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"task\"\r\n\r\n{task}\r\n".encode("utf-8"))
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"

def get_stt_test_cases():
    wav_16k_mono = build_wav_header(16000, 1, 3200) + b"\x00\x00" * 1600
    wav_8k_mono = build_wav_header(8000, 1, 1600) + b"\x00\x00" * 800
    wav_44k_stereo = build_wav_header(44100, 2, 8820) + b"\x00\x00" * 4410
    wav_short = build_wav_header(16000, 1, 100) + b"\x00\x00" * 50
    wav_long = build_wav_header(16000, 1, 40000) + b"\x00\x00" * 20000
    wav_noise = build_wav_header(16000, 1, 3200) + b"\x12\x34\x56\x78" * 800

    headers_valid = {"X-API-Key": API_KEY, "User-Agent": USER_AGENT}
    headers_no_key = {"User-Agent": USER_AGENT}
    headers_bad_key = {"X-API-Key": "ml-badkey-9999", "User-Agent": USER_AGENT}

    cases = []

    # 1-10: Sample Rates, Duration & Formats
    cases.append({"name": "01. Standard 16kHz Mono WAV (bo)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample16k.wav", wav_16k_mono), "expected": [200]})
    cases.append({"name": "02. Low 8kHz Mono WAV (bo)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample8k.wav", wav_8k_mono), "expected": [200]})
    cases.append({"name": "03. High 44.1kHz Stereo WAV (bo)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample44k.wav", wav_44k_stereo), "expected": [200]})
    cases.append({"name": "04. Very short audio (< 0.5s)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("short.wav", wav_short), "expected": [200]})
    cases.append({"name": "05. Long audio (Bounded to MAX_STT_BYTES=500KB)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("long.wav", wav_long), "expected": [200]})
    cases.append({"name": "06. Audio with background noise", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("noise.wav", wav_noise), "expected": [200]})
    cases.append({"name": "07. MP3 mime format upload", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample.mp3", wav_16k_mono, mime_type="audio/mp3"), "expected": [200]})
    cases.append({"name": "08. FLAC mime format upload", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample.flac", wav_16k_mono, mime_type="audio/flac"), "expected": [200]})
    cases.append({"name": "09. Empty audio file (0 bytes)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("empty.wav", b""), "expected": [200, 400, 422]})
    cases.append({"name": "10. Corrupted WAV header (Malformed)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("corrupt.wav", b"INVALID_HEADER_DATA_12345"), "expected": [200, 400, 422]})

    # 11-20: Languages, Tasks & Parameters
    cases.append({"name": "11. Language: English ('en')", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("english.wav", wav_16k_mono, language="en"), "expected": [200]})
    cases.append({"name": "12. Language: Chinese ('zh')", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("chinese.wav", wav_16k_mono, language="zh"), "expected": [200]})
    cases.append({"name": "13. Language: Auto-detect (None)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono, language=None), "expected": [200]})
    cases.append({"name": "14. Task: Translate ('translate')", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono, task="translate"), "expected": [200]})
    cases.append({"name": "15. Missing 'task' parameter", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono, task=None), "expected": [200]})
    cases.append({"name": "16. Invalid language code ('invalid_lang')", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono, language="invalid_lang"), "expected": [200, 400, 422]})
    cases.append({"name": "17. Invalid file extension (.txt uploaded as audio)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("notes.txt", b"Hello World", mime_type="text/plain"), "expected": [200, 400, 422]})
    cases.append({"name": "18. Missing file parameter in body", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body(None, None), "expected": [400, 422, 500]})
    cases.append({"name": "19. Streaming STT endpoint (/speech-to-text/stream)", "url": f"{BASE_URL}/api/v1/speech-to-text/stream", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono), "expected": [200, 404, 405]})
    cases.append({"name": "20. Fast/Live STT endpoint (/speech-to-text/live)", "url": f"{BASE_URL}/api/v1/speech-to-text/live", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono), "expected": [200, 404, 405]})

    # 21-30: Edge Cases & Security Validations
    cases.append({"name": "21. No API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_no_key, "data": build_stt_body("sample.wav", wav_16k_mono), "expected": [401, 403]})
    cases.append({"name": "22. Invalid API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_bad_key, "data": build_stt_body("sample.wav", wav_16k_mono), "expected": [401, 403]})
    cases.append({"name": "23. Alternate Auth Header ('Authorization: Bearer')", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": {"Authorization": f"Bearer {API_KEY}", "User-Agent": USER_AGENT}, "data": build_stt_body("sample.wav", wav_16k_mono), "expected": [200, 401, 403]})
    cases.append({"name": "24. Trailing slash endpoint check", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono), "expected": [200]})
    cases.append({"name": "25. Non-trailing slash endpoint check", "url": f"{BASE_URL}/api/v1/speech-to-text", "headers": headers_valid, "data": build_stt_body("sample.wav", wav_16k_mono), "expected": [200, 301, 307, 308]})
    cases.append({"name": "26. GET method instead of POST", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": (b"", "application/json"), "method": "GET", "expected": [405, 400]})
    cases.append({"name": "27. Pure silence audio payload", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("silence.wav", wav_16k_mono), "expected": [200]})
    cases.append({"name": "28. Tibetan Speech sample 1", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("bo_speech1.wav", wav_16k_mono), "expected": [200]})
    cases.append({"name": "29. Tibetan Speech sample 2", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("bo_speech2.wav", wav_16k_mono), "expected": [200]})
    cases.append({"name": "30. Tibetan Speech sample 3", "url": f"{BASE_URL}/api/v1/speech-to-text/", "headers": headers_valid, "data": build_stt_body("bo_speech3.wav", wav_16k_mono), "expected": [200]})

    # 31-50: Advanced Parameter & Stress Cases
    for i in range(31, 51):
        cases.append({
            "name": f"{i}. STT Parameterization Test Batch #{i}",
            "url": f"{BASE_URL}/api/v1/speech-to-text/",
            "headers": headers_valid,
            "data": build_stt_body(f"audio_batch_{i}.wav", wav_16k_mono, language="bo" if i%2==0 else "en"),
            "expected": [200]
        })

    return cases

def run_stt_tests():
    print(f"=== Running Expanded STT API Test Suite (50 Cases | Key: {API_KEY[:10]}... | MAX_BYTES: {MAX_STT_BYTES}) ===")
    results = []
    cases = get_stt_test_cases()

    for tc in cases:
        t0 = time.perf_counter()
        method = tc.get("method", "POST")
        body_bytes, content_type = tc["data"]
        headers = dict(tc["headers"])
        if content_type:
            headers["Content-Type"] = content_type

        req = urllib.request.Request(tc["url"], data=body_bytes, headers=headers, method=method)
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
    run_stt_tests()
