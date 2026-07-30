"""Performance and Capacity Stress Test for TEEA Daemon (/api/analysis/run).

Measures latency, throughput, suggestion scaling, and max capacity limits
for the Tibetan Editor Enterprise Architecture (TEEA) daemon.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from typing import Any

BASE_TIBETAN_TEXT = "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི། དགེ་གིས་བརྡ་སྤྲོད་སླབས། ཀློ་བོང་བྱས། "

MULTIPLIERS = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
ENDPOINT_URL = "http://127.0.0.1:50505/api/analysis/run"
TIMEOUT_SECONDS = 60.0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 80)
    print("TEEA DAEMON PERFORMANCE & CAPACITY STRESS TEST")
    print("=" * 80)
    print(f"Endpoint URL: {ENDPOINT_URL}")
    print(f"Base Paragraph ({len(BASE_TIBETAN_TEXT)} chars): {BASE_TIBETAN_TEXT.strip()}")
    print(f"Request Timeout: {TIMEOUT_SECONDS}s")
    print("=" * 80 + "\n")

    results: list[dict[str, Any]] = []
    max_safe_chars = 0

    for mult in MULTIPLIERS:
        text_payload = BASE_TIBETAN_TEXT * mult
        char_count = len(text_payload)
        req_id = f"stress-test-{mult}x"

        payload_bytes = json.dumps(
            {
                "protocol_version": "1.0",
                "request_id": req_id,
                "method": "analysis.run",
                "params": {"text": text_payload},
                "session_id": "stress-test",
                "expects_response": True,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            ENDPOINT_URL,
            data=payload_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

        status_code = 0
        elapsed_ms = 0.0
        suggestion_count = 0
        error_msg = ""

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                status_code = resp.status
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw)
                
                if parsed.get("ok") is True:
                    suggestions = parsed.get("result", {}).get("suggestions", [])
                    suggestion_count = len(suggestions)
                    max_safe_chars = max(max_safe_chars, char_count)
                else:
                    error_msg = str(parsed.get("error", "Unknown daemon error"))
        except urllib.error.HTTPError as http_err:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            status_code = http_err.code
            error_msg = f"HTTP Error {http_err.code}: {http_err.reason}"
        except urllib.error.URLError as url_err:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            status_code = 0
            error_msg = f"Connection Failed / Timeout ({url_err.reason})"
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            status_code = 0
            error_msg = f"Exception: {type(exc).__name__} - {exc}"

        record = {
            "multiplier": mult,
            "char_count": char_count,
            "elapsed_ms": elapsed_ms,
            "suggestions": suggestion_count,
            "status_code": status_code,
            "error": error_msg,
        }
        results.append(record)

        # Print live progress line
        if status_code == 200 and not error_msg:
            print(
                f"  [{mult:>4}x]  Chars: {char_count:>7,d} | Time: {elapsed_ms:>9.2f} ms | "
                f"Suggestions: {suggestion_count:>6,d} | Status: 200 OK"
            )
        else:
            print(
                f"  [{mult:>4}x]  Chars: {char_count:>7,d} | Time: {elapsed_ms:>9.2f} ms | "
                f"FAILED (Status: {status_code}) -> {error_msg}"
            )
            print("  --> Stopping further stress testing due to failure/timeout.")
            break

    print("\n" + "=" * 80)
    print("STRESS TEST RESULTS SUMMARY")
    print("=" * 80)
    print(
        f"{'Mult':<6} | {'Char Count':<12} | {'Time (ms)':<12} | {'Throughput (char/s)':<20} | {'Suggestions':<12} | {'Status':<8}"
    )
    print("-" * 80)

    for r in results:
        t_sec = r["elapsed_ms"] / 1000.0
        throughput = (r["char_count"] / t_sec) if t_sec > 0 else 0
        status_str = "200 OK" if r["status_code"] == 200 and not r["error"] else f"FAIL ({r['status_code']})"
        print(
            f"{r['multiplier']:<6} | {r['char_count']:<12,d} | {r['elapsed_ms']:<12.2f} | {throughput:<20,.1f} | {r['suggestions']:<12,d} | {status_str:<8}"
        )

    print("=" * 80)
    print("CAPACITY CONCLUSION:")
    if max_safe_chars > 0:
        print(f"  Maximum Verified Capacity: ~{max_safe_chars:,d} Tibetan characters")
        print(f"  Approximate Volume Equivalent: ~{max_safe_chars // 2500:,d} standard document pages (assuming ~2,500 chars/page)")
    else:
        print("  Daemon was unreachable. Ensure 'python start_daemon.py' is running on port 50505.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
