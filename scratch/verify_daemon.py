"""Send the same analysis request as the user's PowerShell verification command.

Equivalent to:
    $text = "ང་ཚོས་སློབ་སྦྱངབྱེད།"
    $body = @{ request_id = "test-fix"; method = "analysis.run"; params = @{ text = $text } } |
        ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "http://127.0.0.1:50505/api/analysis/run" -Method Post ...
"""

from __future__ import annotations

import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

TEXT = "ང་ཚོས་སློབ་སྦྱངབྱེད།"


def main() -> None:
    body = json.dumps(
        {"request_id": "test-fix", "method": "analysis.run", "params": {"text": TEXT}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:50505/api/analysis/run",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
