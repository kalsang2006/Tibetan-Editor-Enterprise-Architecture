"""Test the daemon HTTP response to see what the taskpane receives."""
import sys, json, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

text = (
    "དེ་རིང་ང་ཆོས་སྒོར་བོདག་ཡིནན།\n"
    "ཁྱེད་རང་ཀ་དེ་ཤེས་གི་རེད།"
)

payload = json.dumps({
    "protocol_version": "1.0",
    "method": "analysis.run",
    "params": {"text": text},
    "request_id": "req-test-001",
}).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:50505/api/analysis/run",
    data=payload,
    headers={"Content-Type": "application/json"},
)

res = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
result = res.get("result", {})
suggestions = result.get("suggestions", [])
patch = result.get("patch", {})
ops = patch.get("operations", [])

print(f"Total suggestions in result.suggestions: {len(suggestions)}")
for i, s in enumerate(suggestions):
    src = s.get("source", "?")
    span = s.get("span", {})
    repl = s.get("replacement")
    priority = s.get("priority", "?")
    score = s.get("score", 0)
    msg = s.get("message", "")[:80]
    cs = span.get("char_start", "?")
    ce = span.get("char_end", "?")
    print(f"  {i+1}. [{src}] chars[{cs}-{ce}] repl={repl!r} prio={priority} score={score:.2f}")
    if msg:
        print(f"     msg: {msg}")

print()
print(f"Total patch operations: {len(ops)}")
for i, op in enumerate(ops):
    span = op.get("span", {})
    repl = op.get("replacement", "")
    sources = op.get("sources", [])
    cs = span.get("char_start", "?")
    ce = span.get("char_end", "?")
    orig = text[cs:ce] if isinstance(cs, int) and isinstance(ce, int) else "?"
    print(f"  {i+1}. chars[{cs}-{ce}] {orig!r} => {repl!r}  sources={sources}")
