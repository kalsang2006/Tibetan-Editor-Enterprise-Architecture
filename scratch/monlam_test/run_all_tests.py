"""Master Test Runner for Monlam AI Studio API Test Harness (250 Test Cases Total)."""
import os
import sys
import json
import time
from pathlib import Path

# Ensure scratch/monlam_test is in sys.path
TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR))

from test_chat import run_chat_tests
from test_tts import run_tts_tests
from test_stt import run_stt_tests
from test_ocr import run_ocr_tests
from test_dictionary import run_dictionary_tests

def main():
    api_key = os.environ.get("REACT_APP_MONLAM_API_KEY", "REPLACE_WITH_MONLAM_API_KEY")
    key_preview = f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 14 else "*****"

    print("===============================================================")
    print("   MONLAM AI STUDIO AUTOMATED TEST HARNESS (250 TEST CASES)   ")
    print(f"   API Key: {key_preview}")
    print("===============================================================\n")

    t_start = time.perf_counter()

    chat_results = run_chat_tests()
    print()
    tts_results = run_tts_tests()
    print()
    stt_results = run_stt_tests()
    print()
    ocr_results = run_ocr_tests()
    print()
    dict_results = run_dictionary_tests()

    total_time = round(time.perf_counter() - t_start, 2)

    suites = {
        "Chat / LLM": chat_results,
        "Text-to-Speech (TTS)": tts_results,
        "Speech-to-Text (STT)": stt_results,
        "OCR (Optical Character Recognition)": ocr_results,
        "Dictionary Search": dict_results
    }

    total_tests = 0
    total_passed = 0
    total_failed = 0
    summary_table = []

    for suite_name, results in suites.items():
        n_tests = len(results)
        n_pass = sum(1 for r in results if r["passed"])
        n_fail = n_tests - n_pass
        avg_lat = round(sum(r["latency_ms"] for r in results) / n_tests, 2) if n_tests else 0.0

        total_tests += n_tests
        total_passed += n_pass
        total_failed += n_fail

        summary_table.append({
            "suite": suite_name,
            "total": n_tests,
            "passed": n_pass,
            "failed": n_fail,
            "avg_latency_ms": avg_lat
        })

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api_key_preview": key_preview,
        "total_execution_seconds": total_time,
        "summary": {
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "pass_rate": round((total_passed / total_tests) * 100, 2) if total_tests else 0.0
        },
        "suite_breakdown": summary_table,
        "details": suites
    }

    out_file = TEST_DIR / "monlam_test_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n===============================================================")
    print("              CONSOLIDATED TEST HARNESS REPORT                  ")
    print("===============================================================")
    print(f"Total Tests Executed : {total_tests}")
    print(f"Total Passed         : {total_passed}")
    print(f"Total Failed         : {total_failed}")
    print(f"Overall Pass Rate    : {report['summary']['pass_rate']}%")
    print(f"Total Execution Time : {total_time} seconds")
    print("---------------------------------------------------------------")
    print(f"{'Endpoint Suite':<36} | {'Total':<6} | {'Pass':<5} | {'Fail':<5} | {'Avg Latency (ms)'}")
    print("---------------------------------------------------------------")
    for row in summary_table:
        print(f"{row['suite']:<36} | {row['total']:<6} | {row['passed']:<5} | {row['failed']:<5} | {row['avg_latency_ms']} ms")
    print("---------------------------------------------------------------")
    print(f"Full structured JSON report saved to: {out_file}\n")

if __name__ == "__main__":
    main()
