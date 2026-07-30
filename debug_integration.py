"""Debug Integration Script for TEEA Microsoft Word Add-in.

Simulates the Office.js Add-in API call to http://127.0.0.1:50505/api/analysis/run
and prints the exact JSON payload returned to the frontend.
"""

import json
import sys
import urllib.request
import urllib.error

from teea.engine import TEEAEngine
from teea.suggestion_fusion import SuggestionFusionEngine


def main() -> None:
    # Ensure stdout handles Tibetan UTF-8 text on Windows terminals
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    test_text = "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི། དགེ་གིས་བརྡ་སྤྲོད་སླབས། ཀློ་བོང་བྱས།"
    print("=" * 70)
    print("TEEA INTEGRATION DEBUGGER FOR MICROSOFT WORD ADD-IN")
    print("=" * 70)
    print(f"Target Input Text:\n  {test_text}\n")

    # 1. In-Process Engine Check
    print("Step 1: Running TEEAEngine.analyze() In-Process...")
    engine = TEEAEngine()
    unified = engine.analyze(test_text)
    print(f"  Total Raw Suggestions Emitted: {len(unified.suggestions)}")

    fusion = SuggestionFusionEngine(engine)
    ui_payload = fusion.format_ui_payload(test_text, unified)

    print("\n  Formatted Word Add-in Payload:")
    print("  " + json.dumps(ui_payload, indent=2, ensure_ascii=False))

    # 2. HTTP Endpoint Check (if daemon is running on 127.0.0.1:50505)
    print("\nStep 2: Probing Daemon HTTP Endpoint on http://127.0.0.1:50505/api/analysis/run ...")
    url = "http://127.0.0.1:50505/api/analysis/run"
    req_data = json.dumps(
        {
            "protocol_version": "1.0",
            "request_id": "debug-req-1",
            "method": "analysis.run",
            "params": {"text": test_text},
            "session_id": "http-loopback",
            "expects_response": True,
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw_response = resp.read().decode("utf-8")
            print("  [SUCCESS] Daemon responded with HTTP 200:")
            parsed = json.loads(raw_response)
            print("  " + json.dumps(parsed, indent=2, ensure_ascii=False))
    except urllib.error.URLError as err:
        print(f"  [NOTE] Daemon not currently active on port 50505 ({err}).")
        print("  To start the daemon, run:\n    python start_daemon.py")

    print("\n" * 1)
    print("=" * 70)
    print("SUMMARY OF DETECTED ERRORS FOR WORD ADD-IN:")
    print("=" * 70)
    edits = [s for s in ui_payload["suggestions"] if s.get("replacement")]
    for idx, s in enumerate(edits, 1):
        r = s["range"]
        orig = test_text[r["char_start"]:r["char_end"]]
        print(
            f"  {idx}. Range [{r['char_start']}:{r['char_end']}] '{orig}' → '{s['replacement']}' "
            f"| Category/Type: {s['error_type']} | Source: {s['source']}"
        )


if __name__ == "__main__":
    main()
