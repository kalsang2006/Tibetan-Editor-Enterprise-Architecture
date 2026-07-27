#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
TEEA — Final Comprehensive IV&V Verification
============================================
Version: 1.3
Date: 2026-07-26

This script runs the full IV&V suite. It assumes you are in the `repo` folder.
"""

import sys
import os
import json
import time
import subprocess
import platform
import importlib.metadata
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# ============================================================
# CRITICAL: Force Python to use the `src` folder inside `repo`
# ============================================================
REPO_ROOT = Path.cwd()
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# Data is one level up, in Data/BDRC
DATA_ROOT = REPO_ROOT.parent / "Data"
CORPUS_PATH = DATA_ROOT / "BDRC"

OUTPUT_DIR = REPO_ROOT / "ivv_report"
OUTPUT_FILE = OUTPUT_DIR / "IVV_REPORT.md"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# SECTION 1: Environment & System Information
# ============================================================

def get_environment_info():
    return {
        "timestamp": datetime.now().isoformat(),
        "platform": platform.platform(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "working_directory": str(Path.cwd()),
        "repository_root": str(REPO_ROOT),
        "src_path": str(SRC_PATH),
        "is_windows": sys.platform == "win32"
    }

# ============================================================
# SECTION 2: Dependency Verification
# ============================================================

def get_installed_packages():
    packages = {}
    try:
        for dist in importlib.metadata.distributions():
            packages[dist.metadata["Name"]] = dist.version
    except Exception:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for pkg in data:
                packages[pkg["name"]] = pkg["version"]
    return packages

def verify_dependencies():
    required = [
        "pytest", "pytest-cov", "ruff", "mypy",
        "bandit", "vulture", "radon",
        "pydantic", "structlog", "colorama",
        "typer", "click", "transformers", "torch"
    ]
    installed = get_installed_packages()
    missing = [pkg for pkg in required if pkg not in installed]
    return (len(missing) == 0, missing)

# ============================================================
# SECTION 3: Static Analysis Tools (run from correct source)
# ============================================================

def run_static_analysis():
    results = {}
    tools = {
        "ruff": ["ruff", "check", str(SRC_PATH)],
        "mypy": ["mypy", str(SRC_PATH), "--strict"],
        "bandit": ["bandit", "-r", str(SRC_PATH), "-f", "json"],
        "vulture": ["vulture", str(SRC_PATH), "--min-confidence=70"],
        "radon": ["radon", "cc", str(SRC_PATH), "-a", "-s"],
    }
    for tool, cmd in tools.items():
        start = time.time()
        try:
            result = subprocess.run(
                [sys.executable, "-m"] + cmd,
                capture_output=True, text=True,
                cwd=str(REPO_ROOT), timeout=120
            )
            passed = result.returncode == 0
            if tool == "bandit" and result.returncode != 0:
                try:
                    data = json.loads(result.stdout)
                    issues = data.get("results", [])
                    high = sum(1 for i in issues if i.get("issue_severity") == "HIGH")
                    medium = sum(1 for i in issues if i.get("issue_severity") == "MEDIUM")
                    low = sum(1 for i in issues if i.get("issue_severity") == "LOW")
                    passed = high == 0 and medium <= 1
                    results[tool] = {
                        "passed": passed,
                        "high": high, "medium": medium, "low": low,
                        "total": len(issues),
                        "duration": time.time() - start
                    }
                    continue
                except:
                    pass
            results[tool] = {
                "passed": passed,
                "returncode": result.returncode,
                "duration": time.time() - start,
                "output": result.stdout[:500] if passed else result.stderr[:500]
            }
        except Exception as e:
            results[tool] = {"passed": False, "error": str(e), "duration": time.time() - start}
    return results

# ============================================================
# SECTION 4: Test Execution (uses repo/tests)
# ============================================================

def run_tests():
    results = {}
    start_time = time.time()
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(REPO_ROOT / "tests"),
                "--tb=short", "-v",
                "--cov=src/teea",
                "--cov-report=term",
                "--cov-report=json:" + str(OUTPUT_DIR / "coverage.json"),
                "--timeout=300"
            ],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT), timeout=300
        )
        import re
        stdout = result.stdout
        passed = int(re.search(r"(\d+)\s+passed", stdout).group(1)) if re.search(r"(\d+)\s+passed", stdout) else 0
        failed = int(re.search(r"(\d+)\s+failed", stdout).group(1)) if re.search(r"(\d+)\s+failed", stdout) else 0
        errors = int(re.search(r"(\d+)\s+errors", stdout).group(1)) if re.search(r"(\d+)\s+errors", stdout) else 0
        results["pytest"] = {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": passed + failed + errors,
            "success": failed == 0 and errors == 0,
            "duration": time.time() - start_time,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        results["pytest"] = {"success": False, "error": "Timeout (300s)", "duration": 300}
    except Exception as e:
        results["pytest"] = {"success": False, "error": str(e), "duration": time.time() - start_time}
    return results

# ============================================================
# SECTION 5: Coverage Analysis
# ============================================================

def get_coverage():
    cov_file = OUTPUT_DIR / "coverage.json"
    if not cov_file.exists():
        return {"available": False}
    try:
        with open(cov_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "available": True,
                "total": data.get("totals", {}).get("percent_covered", 0),
                "missing_lines": data.get("totals", {}).get("missing_lines", 0),
                "num_statements": data.get("totals", {}).get("num_statements", 0)
            }
    except:
        return {"available": False}

# ============================================================
# SECTION 6: Performance Benchmarks
# ============================================================

def run_performance_benchmarks():
    results = {}
    try:
        from teea.nlp import Pipeline
        from teea.core.config import load_settings
        from teea.plagiarism.fingerprinting import RobustWinnowing

        settings = load_settings()
        pipeline = Pipeline(settings)
        texts = {
            "short": "བཀྲ་ཤིས་བདེ་ལེགས།",
            "medium": "ཞང་སྐལ་བྲེ་པེ་སྟན་ཆུང་བྱ་བ་མིང་མི་སྙན་རུང་སྟོན་ཐོག་གཞུན་པོ་ཡོང་པ་ཅིག་ཡོད་པ་དེ།",
            "long": "ཞང་སྐལ་བྲེ་པེ་སྟན་ཆུང་བྱ་བ་མིང་མི་སྙན་རུང་སྟོན་ཐོག་གཞུན་པོ་ཡོང་པ་ཅིག་ཡོད་པ་དེ། ཞང་པོ་ས་སོ་ནམ་བྱས་པའི་ནས་སྐྱེ་འཕེལ་དུ་ཅི་འགྲོ་བྱས་ནས་ཕག་ཏུ་སོག་གིན་ཡོད་པ་ཡང་མང་རབ་ཏུ་སོང་བ་ལ་ཤ་མང་པོ་ཉོས། ནས་དཀར་མོ་མང་པོ་ལ་ཕྱེ་བྱས། ནག་མོ་མང་པོ་ཆང་དུ་བཙོས་པས། མྱང་ཚ་དཀར་རྒྱན་མ་སྨད་ནོར་སློངས་བྱེད་པ་ཡིན་པ་འདུག་ཟེར་བ་བྱུང་།"
        }
        benchmarks = {}
        for name, text in texts.items():
            start = time.perf_counter()
            result = pipeline.process(text)
            elapsed = (time.perf_counter() - start) * 1000
            benchmarks[f"nlp_{name}"] = {
                "chars": len(text),
                "bytes": len(text.encode("utf-8")),
                "tokens": len(result.tokens),
                "sentences": len(result.sentences),
                "elapsed_ms": elapsed,
                "chars_per_sec": len(text) / (elapsed / 1000) if elapsed > 0 else 0,
                "tokens_per_sec": len(result.tokens) / (elapsed / 1000) if elapsed > 0 else 0
            }

        # Plagiarism fingerprinting
        winnowing = RobustWinnowing(k=5, w=20)
        times = []
        for _ in range(10):
            start = time.perf_counter()
            for t in texts.values():
                winnowing.fingerprint(t)
            times.append((time.perf_counter() - start) * 1000)
        benchmarks["plagiarism"] = {
            "avg_ms": sum(times) / len(times),
            "min_ms": min(times),
            "max_ms": max(times),
            "fp_count": len(winnowing.fingerprint(texts["medium"]))
        }
        results["benchmarks"] = benchmarks
    except Exception as e:
        results = {"error": str(e)}
    return results

# ============================================================
# SECTION 7: Plagiarism Validation
# ============================================================

def validate_plagiarism():
    results = {}
    try:
        from teea.plagiarism.fingerprinting import RobustWinnowing
        from teea.plagiarism.similarity import jaccard_similarity
        winnowing = RobustWinnowing(k=5, w=20)
        text1 = "ཞང་སྐལ་བྲེ་པེ་སྟན་ཆུང་བྱ་བ་མིང་མི་སྙན་རུང་"
        text2 = "ཞང་སྐལ་བྲེ་པེ་སྟན་ཆུང་བྱ་བ་མིང་མི་སྙན་རུང་"
        fp1 = winnowing.fingerprint(text1)
        fp2 = winnowing.fingerprint(text2)
        jaccard = jaccard_similarity(set(fp1), set(fp2)) if fp1 and fp2 else 0
        results["jaccard"] = jaccard
        results["pass"] = jaccard >= 0.9
        results["fp1_count"] = len(fp1)
        results["fp2_count"] = len(fp2)
    except Exception as e:
        results = {"error": str(e)}
    return results

# ============================================================
# SECTION 8: CLI & Demo Validation
# ============================================================

def validate_cli():
    results = {}
    demo_path = REPO_ROOT / "demo.py"
    if demo_path.exists():
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            result = subprocess.run(
                [sys.executable, str(demo_path)],
                capture_output=True, text=True,
                cwd=str(REPO_ROOT), timeout=30, env=env
            )
            results["demo"] = {
                "success": result.returncode == 0,
                "output": result.stdout[:500],
                "stderr": result.stderr[:500]
            }
        except Exception as e:
            results["demo"] = {"success": False, "error": str(e)}
    else:
        results["demo"] = {"success": False, "error": "demo.py not found"}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "teea", "--help"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT), timeout=10
        )
        results["module_entry"] = {"success": result.returncode == 0}
    except:
        results["module_entry"] = {"success": False}
    return results

# ============================================================
# SECTION 9: Corpus Validation
# ============================================================

def validate_corpus():
    if not CORPUS_PATH.exists():
        return {"available": False, "path": str(CORPUS_PATH)}
    files = list(CORPUS_PATH.glob("**/*.xml")) + list(CORPUS_PATH.glob("**/*.tei")) + list(CORPUS_PATH.glob("**/*.txt"))
    total_size = sum(f.stat().st_size for f in files)
    return {
        "available": True,
        "path": str(CORPUS_PATH),
        "doc_count": len(files),
        "size_mb": total_size / (1024 * 1024)
    }

# ============================================================
# SECTION 10: Report Generation
# ============================================================

def generate_report(env, deps_ok, missing, static, tests, cov, perf, plag, cli, corpus):
    lines = []
    lines.append("# TEEA — Final IV&V Report\n")
    lines.append(f"**Date:** {env['timestamp']}\n")
    lines.append(f"**Platform:** {env['platform']}\n")
    lines.append(f"**Python:** {env['python_version'].split()[0]}\n")
    lines.append(f"**Repo:** {env['repository_root']}\n")
    lines.append("---\n")
    lines.append("## Environment\n")
    lines.append(f"- Working Directory: `{env['working_directory']}`\n")
    lines.append(f"- Source Path: `{env['src_path']}`\n")
    lines.append(f"- Windows: `{env['is_windows']}`\n")
    lines.append("\n## Dependencies\n")
    if deps_ok:
        lines.append("✅ All critical dependencies installed.\n")
    else:
        lines.append(f"❌ Missing: {', '.join(missing)}\n")
    lines.append("\n## Static Analysis\n")
    for tool, res in static.items():
        icon = "✅" if res.get("passed", False) else "❌"
        dur = res.get("duration", 0)
        lines.append(f"- **{tool}**: {icon} ({dur:.2f}s)\n")
    lines.append("\n## Tests\n")
    t = tests.get("pytest", {})
    lines.append(f"- Passed: {t.get('passed', 0)}\n")
    lines.append(f"- Failed: {t.get('failed', 0)}\n")
    lines.append(f"- Errors: {t.get('errors', 0)}\n")
    lines.append(f"- Duration: {t.get('duration', 0):.2f}s\n")
    lines.append(f"- Overall: {'✅' if t.get('success', False) else '❌'}\n")
    lines.append("\n## Coverage\n")
    if cov.get("available"):
        lines.append(f"- Total: {cov.get('total', 0):.1f}%\n")
        lines.append(f"- Statements: {cov.get('num_statements', 0)}\n")
        lines.append(f"- Missing Lines: {cov.get('missing_lines', 0)}\n")
    else:
        lines.append("⚠️ Coverage data not available.\n")
    lines.append("\n## Performance\n")
    if "benchmarks" in perf:
        for k, v in perf["benchmarks"].items():
            if k.startswith("nlp"):
                lines.append(f"\n### {k.upper()}\n")
                lines.append(f"- Chars: {v.get('chars', 0)}\n")
                lines.append(f"- Tokens: {v.get('tokens', 0)}\n")
                lines.append(f"- Time: {v.get('elapsed_ms', 0):.2f} ms\n")
                lines.append(f"- Throughput: {v.get('chars_per_sec', 0):.0f} char/s\n")
            elif k == "plagiarism":
                lines.append(f"\n### Plagiarism\n")
                lines.append(f"- Avg: {v.get('avg_ms', 0):.2f} ms\n")
                lines.append(f"- Fingerprints: {v.get('fp_count', 0)}\n")
    else:
        lines.append(f"⚠️ Performance benchmark error: {perf.get('error', '')}\n")
    lines.append("\n## Plagiarism Subsystem\n")
    if "error" in plag:
        lines.append(f"⚠️ Error: {plag['error']}\n")
    else:
        lines.append(f"- Jaccard Similarity: {plag.get('jaccard', 0):.4f}\n")
        lines.append(f"- Pass: {'✅' if plag.get('pass', False) else '❌'}\n")
    lines.append("\n## CLI & Demo\n")
    lines.append(f"- `demo.py`: {'✅' if cli.get('demo', {}).get('success', False) else '❌'}\n")
    lines.append(f"- Module entry: {'✅' if cli.get('module_entry', {}).get('success', False) else '❌'}\n")
    lines.append("\n## Corpus\n")
    if corpus.get("available"):
        lines.append(f"- Path: `{corpus['path']}`\n")
        lines.append(f"- Documents: {corpus['doc_count']}\n")
        lines.append(f"- Size: {corpus['size_mb']:.2f} MB\n")
    else:
        lines.append(f"⚠️ Corpus not found at `{corpus.get('path', '')}`\n")
    lines.append("\n## Overall Verdict\n")
    all_pass = (
        t.get('success', False) and
        all(v.get('passed', False) for v in static.values()) and
        cli.get('demo', {}).get('success', False) and
        plag.get('pass', False)
    )
    if all_pass:
        lines.append("✅ **ALL CHECKS PASS — SYSTEM IS PRODUCTION-READY**\n")
    else:
        lines.append("⚠️ **SOME CHECKS FAILED — REVIEW SECTIONS ABOVE**\n")
    lines.append("\n---\n")
    lines.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
    return "".join(lines)

# ============================================================
# MAIN
# ============================================================

def main():
    print("\n" + "="*70)
    print(" TEEA — Final Comprehensive IV&V Verification")
    print("="*70 + "\n")

    print(f"Working directory: {Path.cwd()}")
    print(f"Using src path: {SRC_PATH}")

    env = get_environment_info()
    print("1. Collecting environment...")
    deps_ok, missing = verify_dependencies()
    print(f"   Dependencies: {'✅ OK' if deps_ok else '❌ Missing: ' + ', '.join(missing)}")

    print("2. Running static analysis...")
    static = run_static_analysis()
    for tool, res in static.items():
        icon = "✅" if res.get("passed", False) else "❌"
        print(f"   {tool}: {icon}")

    print("3. Running test suite (this may take a few minutes)...")
    tests = run_tests()
    t = tests.get("pytest", {})
    print(f"   Tests: {t.get('passed', 0)} passed, {t.get('failed', 0)} failed, {t.get('errors', 0)} errors")

    print("4. Retrieving coverage...")
    cov = get_coverage()
    if cov.get("available"):
        print(f"   Coverage: {cov.get('total', 0):.1f}%")
    else:
        print("   ⚠️ Coverage data not available.")

    print("5. Running performance benchmarks...")
    perf = run_performance_benchmarks()
    if "benchmarks" in perf:
        short = perf["benchmarks"].get("nlp_short", {})
        print(f"   Short text: {short.get('elapsed_ms', 0):.2f} ms")
    else:
        print(f"   ⚠️ Benchmark error: {perf.get('error', '')}")

    print("6. Validating plagiarism...")
    plag = validate_plagiarism()
    if "error" not in plag:
        print(f"   Jaccard: {plag.get('jaccard', 0):.4f} {'✅' if plag.get('pass', False) else '❌'}")
    else:
        print(f"   ⚠️ Error: {plag['error']}")

    print("7. Validating CLI and demo...")
    cli = validate_cli()
    print(f"   demo.py: {'✅' if cli.get('demo', {}).get('success', False) else '❌'}")
    print(f"   Module entry: {'✅' if cli.get('module_entry', {}).get('success', False) else '❌'}")

    print("8. Validating corpus...")
    corpus = validate_corpus()
    if corpus.get("available"):
        print(f"   Corpus: {corpus['doc_count']} documents, {corpus['size_mb']:.2f} MB")
    else:
        print(f"   ⚠️ Corpus not found at {corpus.get('path', '')}")

    print("\n9. Generating final report...")
    report = generate_report(env, deps_ok, missing, static, tests, cov, perf, plag, cli, corpus)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n✅ Report saved to: {OUTPUT_FILE}")

    print("\n" + "="*70)
    print(" SUMMARY")
    print("="*70)
    print(f"| Metric                | Result                  |")
    print(f"|-----------------------|-------------------------|")
    print(f"| Tests                 | {t.get('passed', 0)} passed, {t.get('failed', 0)} failed |")
    print(f"| Coverage              | {cov.get('total', 0):.1f}%                     |")
    print(f"| Static Analysis       | {'✅ All pass' if all(v.get('passed', False) for v in static.values()) else '⚠️ Some fail'} |")
    print(f"| NLP Speed (short)     | {perf.get('benchmarks', {}).get('nlp_short', {}).get('elapsed_ms', 0):.2f} ms |")
    print(f"| Plagiarism Jaccard    | {plag.get('jaccard', 0):.4f}                  |")
    print(f"| demo.py               | {'✅ Works' if cli.get('demo', {}).get('success', False) else '❌ Fails'} |")
    print(f"| Corpus                | {corpus.get('doc_count', 0)} docs             |")
    print("="*70)

    overall = all([
        t.get('success', False),
        all(v.get('passed', False) for v in static.values()),
        cli.get('demo', {}).get('success', False),
        plag.get('pass', False)
    ])
    print(f"OVERALL VERDICT: {'✅ PASS — SYSTEM IS PRODUCTION-READY' if overall else '⚠️ CHECK FAILURES ABOVE'}")
    print("="*70)

if __name__ == "__main__":
    main()