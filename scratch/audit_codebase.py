"""Deep forensic code auditor script."""

import os
from pathlib import Path
import re

src_dir = Path("src/teea")

# 1. SQL Injection audit in persistence
print("=== 1. SQL Injection Audit ===")
sql_files = list(src_dir.glob("persistence/**/*.py"))
sql_injection_concerns = []
for file_path in sql_files:
    text = file_path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if ".execute(" in line or ".executemany(" in line:
            if "f\"" in line or "f'" in line or "% " in line or ".format(" in line:
                sql_injection_concerns.append((str(file_path), i, line.strip()))

print(f"SQL Injection Concerns found: {len(sql_injection_concerns)}")
for f, l, content in sql_injection_concerns:
    print(f"  [!] {f}:{l} -> {content}")

# 2. NLP Pipeline Completeness & Placeholder Audit
print("\n=== 2. NLP Pipeline Stubs & TODOs Audit ===")
nlp_files = list(src_dir.glob("nlp/**/*.py"))
todos_stubs = []
for file_path in nlp_files:
    text = file_path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if "TODO" in line or "FIXME" in line or "NotImplementedError" in line or "pass" == line.strip():
            todos_stubs.append((str(file_path), i, line.strip()))

print(f"NLP Stubs/TODOs/NotImplemented found: {len(todos_stubs)}")
for f, l, content in todos_stubs[:10]:
    print(f"  [-] {f}:{l} -> {content}")

# 3. Path Traversal & File I/O Safety
print("\n=== 3. Path Traversal & Unsafe I/O Audit ===")
path_issues = []
for file_path in src_dir.glob("**/*.py"):
    text = file_path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if "open(" in line and "encoding" not in line and "import " not in line and "#" not in line:
            path_issues.append((str(file_path), i, line.strip()))

print(f"Unspecified File Encoding `open()` calls: {len(path_issues)}")
for f, l, content in path_issues:
    print(f"  [!] {f}:{l} -> {content}")

# 4. Error swallow / silent try-except
print("\n=== 4. Silent Exception Swallowing Audit ===")
silent_excepts = []
for file_path in src_dir.glob("**/*.py"):
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "except" in line and "pass" in lines[min(i + 1, len(lines) - 1)].strip():
            silent_excepts.append((str(file_path), i + 1, line.strip()))

print(f"Silent `except ...: pass` blocks: {len(silent_excepts)}")
for f, l, content in silent_excepts:
    print(f"  [!] {f}:{l} -> {content}")
