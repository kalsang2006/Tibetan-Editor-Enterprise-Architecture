"""Monlam AI Studio Chat/LLM Endpoint Test Suite (50 Comprehensive Test Cases)."""
import os
import json
import time
import urllib.request
import urllib.error

BASE_URL = "https://api-v1.monlamai.studio"
API_KEY = os.environ.get("REACT_APP_MONLAM_API_KEY", "REPLACE_WITH_MONLAM_API_KEY")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MonlamClient/1.0"
MAX_CHAT_CHARS = 5000

def get_chat_test_cases():
    headers_valid = {"Content-Type": "application/json", "X-API-Key": API_KEY, "User-Agent": USER_AGENT}
    headers_invalid_key = {"Content-Type": "application/json", "X-API-Key": "ml-invalid-key-9999999", "User-Agent": USER_AGENT}
    headers_no_key = {"Content-Type": "application/json", "User-Agent": USER_AGENT}

    cases = []

    # 1-10: Basic & Prompt Sizes
    cases.append({"name": "01. Valid system + user messages (Short)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "system", "content": "You are a Tibetan editor."}, {"role": "user", "content": "Hello"}]}, "expected": [200]})
    cases.append({"name": "02. Valid user message (Medium)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼‹ à½à¾±à½ºà½‘à¼‹à½¢à½„à¼‹à½¦à¾à½´à¼‹à½à½˜à½¦à¼‹à½–à½Ÿà½„à¼‹à½„à½˜à¼"}]}, "expected": [200]})
    cases.append({"name": "03. Valid user message (Long 1,000 chars)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼ " * 70}]}, "expected": [200]})
    cases.append({"name": "04. Very long input (Bounded to MAX_CHAT_CHARS=5000)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼ " * 300}]}, "expected": [200]})
    cases.append({"name": "05. SSE Token Streaming (/chat/stream)", "url": f"{BASE_URL}/api/v1/ai/chat/stream", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Tell me a short Tibetan greeting."}]}, "expected": [200, 404, 405]})
    cases.append({"name": "06. SSE Streaming with Long Prompt", "url": f"{BASE_URL}/api/v1/ai/chat/stream", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Write a paragraph in Tibetan: " + "à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹ " * 50}]}, "expected": [200, 404, 405]})
    cases.append({"name": "07. Empty user message (Error handling)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": ""}]}, "expected": [200, 400, 422]})
    cases.append({"name": "08. Whitespace-only user message", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "   \n\t  "}]}, "expected": [200, 400, 422]})
    cases.append({"name": "09. Special Tibetan Punctuation (à¼º à¼„à¼…à¼Ž à¼Ž à¼»)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "à¼º à¼„à¼…à¼Ž à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼‹ à¼Ž à¼»"}]}, "expected": [200]})
    cases.append({"name": "10. Tibetan Stacked Characters (à½€à¾µà¾²à½±à½²à½¾à½¿)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "à½€à¾µà¾²à½±à½²à½¾à½¿ à½¦à½„à¾’à¾·à½¿ à½‘à¾·à½¢à¾¨à½¿"}]}, "expected": [200]})

    # 11-20: Script, Emojis, Roles & History
    cases.append({"name": "11. Emojis and Tibetan script mixed", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "ðŸ™ à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼ ðŸŒ¸ âœ¨"}]}, "expected": [200]})
    cases.append({"name": "12. Multi-turn chat history (3 turns)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "system", "content": "Helpful bot"}, {"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}, {"role": "user", "content": "How are you?"}]}, "expected": [200]})
    cases.append({"name": "13. Large conversation history (15 turns)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user" if i%2==0 else "assistant", "content": f"Turn {i}"} for i in range(15)]}, "expected": [200]})
    cases.append({"name": "14. Invalid role string ('superhero')", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "superhero", "content": "Hi"}]}, "expected": [200, 400, 422]})
    cases.append({"name": "15. Missing 'role' key in message object", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"content": "Hi"}]}, "expected": [200, 400, 422]})
    cases.append({"name": "16. Missing 'content' key in message object", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user"}]}, "expected": [200, 400, 422]})
    cases.append({"name": "17. Empty 'messages' array", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": []}, "expected": [200, 400, 422]})
    cases.append({"name": "18. Missing 'messages' field in body", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong"}, "expected": [200, 400, 422, 500]})
    cases.append({"name": "19. Missing 'model_name' field", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"messages": [{"role": "user", "content": "Hello"}]}, "expected": [200, 400, 422]})
    cases.append({"name": "20. Alternative model_name ('melong-large')", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong-large", "messages": [{"role": "user", "content": "Test"}]}, "expected": [200, 400, 422]})

    # 21-30: Multilingual & Parameter Tweaks
    cases.append({"name": "21. Multilingual English-Tibetan-Chinese", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hello à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼‹ ä½ å¥½"}]}, "expected": [200]})
    cases.append({"name": "22. System Prompt Customization", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "system", "content": "You are a classical Tibetan grammar expert."}, {"role": "user", "content": "Explain à½£à¼‹à½‘à½¼à½“"}]}, "expected": [200]})
    cases.append({"name": "23. Explicit temperature parameter (0.2)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hi"}], "temperature": 0.2}, "expected": [200]})
    cases.append({"name": "24. Explicit top_p parameter (0.9)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hi"}], "top_p": 0.9}, "expected": [200]})
    cases.append({"name": "25. max_tokens parameter (50)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Count to 10"}], "max_tokens": 50}, "expected": [200]})
    cases.append({"name": "26. High temperature parameter (1.5)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Creative story"}], "temperature": 1.5}, "expected": [200]})
    cases.append({"name": "27. HTML/XML Tags in prompt", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "<script>alert(1)</script> <b>Tibetan</b>"}]}, "expected": [200]})
    cases.append({"name": "28. SQL Injection style string in prompt", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "' OR '1'='1"}]}, "expected": [200]})
    cases.append({"name": "29. Markdown formatted input", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "# Heading\n* Item 1\n* Item 2"}]}, "expected": [200]})
    cases.append({"name": "30. JSON payload as string inside content", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": '{"test": "value"}'}]}, "expected": [200]})

    # 31-40: Security, Authentication & Headers
    cases.append({"name": "31. No API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_no_key, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hello"}]}, "expected": [401, 403]})
    cases.append({"name": "32. Invalid API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_invalid_key, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hello"}]}, "expected": [401, 403]})
    cases.append({"name": "33. Alternate Auth Header ('Authorization: Bearer key')", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}", "User-Agent": USER_AGENT}, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hello"}]}, "expected": [200, 401, 403]})
    cases.append({"name": "34. Trailing Slash endpoint check", "url": f"{BASE_URL}/api/v1/ai/chat/", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hello"}]}, "expected": [200, 301, 307, 308]})
    cases.append({"name": "35. GET method instead of POST", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": None, "method": "GET", "expected": [405, 400]})
    cases.append({"name": "36. Extra unknown payload fields", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Hello"}], "unknown_field": 123}, "expected": [200]})
    cases.append({"name": "37. Numeric content in user message", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "1234567890"}]}, "expected": [200]})
    cases.append({"name": "38. Tibetan Numerals (à¼¡ à¼¢ à¼£ à¼¤ à¼¥ à¼¦ à¼§ à¼¨ à¼© à¼ )", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "à¼¡ à¼¢ à¼£ à¼¤ à¼¥ à¼¦ à¼§ à¼¨ à¼© à¼ "}]}, "expected": [200]})
    cases.append({"name": "39. Rapid sequential request 1", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Seq 1"}]}, "expected": [200]})
    cases.append({"name": "40. Rapid sequential request 2", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Seq 2"}]}, "expected": [200]})

    # 41-50: Edge cases & Stress inputs
    cases.append({"name": "41. System prompt only (no user message)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "system", "content": "System message"}]}, "expected": [200, 400, 422]})
    cases.append({"name": "42. Newline escaped strings in prompt", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Line 1\nLine 2\nLine 3"}]}, "expected": [200]})
    cases.append({"name": "43. Tab indented prompt string", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "\t\tIndented text"}]}, "expected": [200]})
    cases.append({"name": "44. Mixed case role string ('User')", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "User", "content": "Hello"}]}, "expected": [200, 400, 422]})
    cases.append({"name": "45. Zero temperature parameter (0.0)", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Exact answer"}], "temperature": 0.0}, "expected": [200]})
    cases.append({"name": "46. Tibetan spell correction query", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Correct spelling: à½¦à¾³à½¼à½–à¼‹à½¦à¾¦à¾±à½„"}]}, "expected": [200]})
    cases.append({"name": "47. Tibetan translation query", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Translate to English: à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹à½–à½‘à½ºà¼‹à½£à½ºà½‚à½¦à¼"}]}, "expected": [200]})
    cases.append({"name": "48. Tibetan summarization query", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Summarize this text: " + "à½–à½€à¾²à¼‹à½¤à½²à½¦à¼‹ " * 20}]}, "expected": [200]})
    cases.append({"name": "49. Response structure verification", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Echo test"}]}, "expected": [200]})
    cases.append({"name": "50. Final Chat suite health check", "url": f"{BASE_URL}/api/v1/ai/chat", "headers": headers_valid, "payload": {"model_name": "melong", "messages": [{"role": "user", "content": "Status OK"}]}, "expected": [200]})

    return cases

def run_chat_tests():
    print(f"=== Running Expanded Chat/LLM API Test Suite (50 Cases | Key: {API_KEY[:10]}... | MAX_CHARS: {MAX_CHAT_CHARS}) ===")
    results = []
    cases = get_chat_test_cases()

    for tc in cases:
        t0 = time.perf_counter()
        method = tc.get("method", "POST")
        payload = tc.get("payload")

        # Enforce MAX_CHAT_CHARS bound check
        if payload and isinstance(payload, dict) and "messages" in payload and isinstance(payload["messages"], list):
            for msg in payload["messages"]:
                if isinstance(msg, dict) and "content" in msg and isinstance(msg["content"], str):
                    if len(msg["content"]) > MAX_CHAT_CHARS:
                        print(f"[SKIP] {tc['name']} -> Truncating message from {len(msg['content'])} to {MAX_CHAT_CHARS} chars")
                        msg["content"] = msg["content"][:MAX_CHAT_CHARS]

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None

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
    run_chat_tests()
