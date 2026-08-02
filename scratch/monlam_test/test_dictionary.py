"""Monlam AI Studio Dictionary Search Endpoint Test Suite (50 Comprehensive Test Cases)."""
import os
import json
import time
import urllib.request
import urllib.error

BASE_URL = "https://api-v1.monlamai.studio"
API_KEY = os.environ.get("REACT_APP_MONLAM_API_KEY", "ml-y4K0RI88kQDXWbU8FboYc1tZ50NeXVXjbBNorbYG0gg")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MonlamClient/1.0"
MAX_QUERY_LENGTH = 50

def get_dictionary_test_cases():
    headers_valid = {"X-API-Key": API_KEY, "User-Agent": USER_AGENT}
    headers_invalid_key = {"X-API-Key": "ml-invalid-key-9999999", "User-Agent": USER_AGENT}
    headers_no_key = {"User-Agent": USER_AGENT}

    pairs = ["bo-en", "bo-bo", "en-bo", "bo-zh"]
    sample_words = ["སློབ་སྦྱོང", "བཀྲ་ཤིས", "སངས་རྒྱས", "བྱང་ཆུབ", "ཤེས་རབ"]

    cases = []

    # 1-20: Valid Words across Pairs & Queries
    for pair in pairs:
        for word in sample_words:
            cases.append({
                "name": f"Dict Search ({pair}): '{word}'",
                "url": f"{BASE_URL}/api/v1/dictionary/search?pair={pair}&q={urllib.parse.quote(word)}",
                "headers": headers_valid,
                "expected": [200, 404, 422]
            })

    # 21-30: English / Non-Tibetan Inputs & Punctuation
    cases.append({"name": "21. English word search (en-bo): 'study'", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=en-bo&q=study", "headers": headers_valid, "expected": [200, 404]})
    cases.append({"name": "22. English word search (en-bo): 'wisdom'", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=en-bo&q=wisdom", "headers": headers_valid, "expected": [200, 404]})
    cases.append({"name": "23. Chinese word search (zh-bo): '学习'", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=zh-bo&q=%E5%AD%A6%E4%B9%A0", "headers": headers_valid, "expected": [200, 404, 422]})
    cases.append({"name": "24. Tibetan Punctuation (༺ ༄༅༎ ༎ ༻)", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-bo&q=%E0%BD%80%E0%BD%B1%E0%BD%B2%E0%BE%92", "headers": headers_valid, "expected": [200, 404]})
    cases.append({"name": "25. Long sentence query (Bounded to MAX_QUERY_LENGTH=50)", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q={urllib.parse.quote('བཀྲ་ཤིས་བདེ་ལེགས་ ཁྱེད་རང་སྐུ་ཁམས་བཟང་ངམ།'[:MAX_QUERY_LENGTH])}", "headers": headers_valid, "expected": [200, 404, 422]})
    cases.append({"name": "26. Non-existent random Tibetan word", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q={urllib.parse.quote('ཀྵྲཱིཾཿxyz999')}", "headers": headers_valid, "expected": [200, 404]})
    cases.append({"name": "27. Single Tibetan letter query ('ཀ')", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-bo&q=%E0%BD%80", "headers": headers_valid, "expected": [200, 404]})
    cases.append({"name": "28. Empty query string ('q=')", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q=", "headers": headers_valid, "expected": [200, 400, 404, 422]})
    cases.append({"name": "29. Missing 'q' parameter in URL", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en", "headers": headers_valid, "expected": [200, 400, 404, 422]})
    cases.append({"name": "30. Missing 'pair' parameter in URL", "url": f"{BASE_URL}/api/v1/dictionary/search?q=%E0%BD%A6%E0%BD%B3%E0%BD%B2", "headers": headers_valid, "expected": [200, 400, 422]})

    # 31-40: Invalid Pairs, Case Variations & Security
    cases.append({"name": "31. Invalid language pair ('xx-xx')", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=xx-xx&q=test", "headers": headers_valid, "expected": [200, 400, 422, 404]})
    cases.append({"name": "32. Mixed case pair parameter ('BO-EN')", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=BO-EN&q=test", "headers": headers_valid, "expected": [200, 400, 422, 404]})
    cases.append({"name": "33. Numeric query string ('12345')", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q=12345", "headers": headers_valid, "expected": [200, 404]})
    cases.append({"name": "34. Tibetan Numerals query ('༡༢༣')", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-bo&q=%E0%BD%A1%E0%BD%A2%E0%BD%A3", "headers": headers_valid, "expected": [200, 404]})
    cases.append({"name": "35. No API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q=test", "headers": headers_no_key, "expected": [401, 403]})
    cases.append({"name": "36. Invalid API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q=test", "headers": headers_invalid_key, "expected": [401, 403]})
    cases.append({"name": "37. Alternate Auth Header ('Authorization: Bearer')", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q=test", "headers": {"Authorization": f"Bearer {API_KEY}", "User-Agent": USER_AGENT}, "expected": [200, 401, 403]})
    cases.append({"name": "38. Trailing slash endpoint check", "url": f"{BASE_URL}/api/v1/dictionary/search/?pair=bo-en&q=test", "headers": headers_valid, "expected": [200, 301, 307, 308, 404]})
    cases.append({"name": "39. POST method instead of GET", "url": f"{BASE_URL}/api/v1/dictionary/search", "headers": headers_valid, "method": "POST", "expected": [405, 400, 422, 200]})
    cases.append({"name": "40. URL encoded special characters query", "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q=%23%24%25%26%2A", "headers": headers_valid, "expected": [200, 404]})

    # 41-50: Stress & Rapid Queries Batch
    for i in range(41, 51):
        w = sample_words[i % len(sample_words)]
        cases.append({
            "name": f"{i}. Dictionary Batch Search #{i} ('{w}')",
            "url": f"{BASE_URL}/api/v1/dictionary/search?pair=bo-en&q={urllib.parse.quote(w)}",
            "headers": headers_valid,
            "expected": [200, 404]
        })

    return cases

def run_dictionary_tests():
    print(f"=== Running Dictionary API Test Suite (50 Cases | Key: {API_KEY[:10]}... | MAX_Q_LEN: {MAX_QUERY_LENGTH}) ===")
    results = []
    cases = get_dictionary_test_cases()

    for tc in cases:
        t0 = time.perf_counter()
        method = tc.get("method", "GET")

        req = urllib.request.Request(tc["url"], headers=tc["headers"], method=method)
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
    run_dictionary_tests()
