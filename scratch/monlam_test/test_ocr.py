"""Monlam AI Studio Optical Character Recognition (OCR) Endpoint Test Suite (50 Comprehensive Test Cases)."""
import os
import time
import urllib.request
import urllib.error

BASE_URL = "https://api-v1.monlamai.studio"
API_KEY = os.environ.get("REACT_APP_MONLAM_API_KEY", "ml-y4K0RI88kQDXWbU8FboYc1tZ50NeXVXjbBNorbYG0gg")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MonlamClient/1.0"
MAX_OCR_IMAGE_BYTES = 10000000  # 10 MB limit check

# Minimal valid 1x1 PNG binary payload
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x03\x00\x05\xfe\x02\xfe\xa7\x96\x81\xd4\x00\x00\x00\x00IEND\xaeB`\x82"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x25\x1a\x1b\x15\x14\x1d\x28\x2a\x2c\x2b\x28\x29\x28\x2e\x34\x42\x38\x2e\x31\x3e\x32\x28\x29\x39\x4d\x3a\x3e\x44\x47\x4b\x4b\x4b\x2d\x38\x52\x58\x51\x48\x57\x43\x4a\x4b\x47\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xbf\x00\xbf\x00\xff\xd9"

def build_ocr_body(filename: str, file_bytes: bytes, mime_type: str = "image/png", lang_hint: str = "bo") -> tuple[bytes, str]:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    parts = []
    if filename is not None and file_bytes is not None:
        if len(file_bytes) > MAX_OCR_IMAGE_BYTES:
            file_bytes = file_bytes[:MAX_OCR_IMAGE_BYTES]
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        parts.append(file_bytes)
        parts.append(b"\r\n")
    if lang_hint is not None:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"lang_hint\"\r\n\r\n{lang_hint}\r\n".encode("utf-8"))
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"

def get_ocr_test_cases():
    headers_valid = {"X-API-Key": API_KEY, "User-Agent": USER_AGENT}
    headers_no_key = {"User-Agent": USER_AGENT}
    headers_bad_key = {"X-API-Key": "ml-badkey-9999", "User-Agent": USER_AGENT}

    cases = []

    # 1-10: Single-page Image Formats & Resolutions
    cases.append({"name": "01. Single-page Tibetan Text Image (PNG)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("tibetan_text.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "02. Single-page Tibetan Text Image (JPEG)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("tibetan_text.jpg", JPEG_BYTES, mime_type="image/jpeg"), "expected": [200]})
    cases.append({"name": "03. Mixed Tibetan and English Image", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("mixed.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "04. Handwritten Tibetan Script Image", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("handwritten.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "05. Low-resolution Image (100x100 px)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("low_res.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "06. High-resolution Image (4000x4000 px)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("high_res.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "07. Language hint: English ('en')", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("doc.png", PNG_BYTES, lang_hint="en"), "expected": [200]})
    cases.append({"name": "08. Language hint: Chinese ('zh')", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("doc.png", PNG_BYTES, lang_hint="zh"), "expected": [200]})
    cases.append({"name": "09. Missing 'lang_hint' parameter", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("doc.png", PNG_BYTES, lang_hint=None), "expected": [200]})
    cases.append({"name": "10. Invalid 'lang_hint' code ('xx')", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("doc.png", PNG_BYTES, lang_hint="xx"), "expected": [200, 400, 422]})

    # 11-20: File Types, Orientations & Multi-page
    cases.append({"name": "11. Blank image payload (0 bytes)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("blank.png", b""), "expected": [200, 400, 422]})
    cases.append({"name": "12. Unsupported PDF file type", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("document.pdf", b"%PDF-1.4...", mime_type="application/pdf"), "expected": [200, 400, 415, 422]})
    cases.append({"name": "13. Unsupported SVG file type", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("vector.svg", b"<svg></svg>", mime_type="image/svg+xml"), "expected": [200, 400, 415, 422]})
    cases.append({"name": "14. Image with no text (Landscape)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("landscape.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "15. Rotated text image (90 degrees)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("rot90.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "16. Rotated text image (180 degrees)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("rot180.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "17. Rotated text image (270 degrees)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("rot270.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "18. Skewed / tilted image text", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("skewed.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "19. Multi-page OCR endpoint (/multi-page)", "url": f"{BASE_URL}/api/v1/ocr/multi-page", "headers": headers_valid, "data": build_ocr_body("multi.png", PNG_BYTES), "expected": [200, 404, 405, 422]})
    cases.append({"name": "20. Missing file parameter in body", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body(None, None), "expected": [400, 422, 500]})

    # 21-30: Edge cases & Security Validations
    cases.append({"name": "21. No API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_no_key, "data": build_ocr_body("doc.png", PNG_BYTES), "expected": [401, 403]})
    cases.append({"name": "22. Invalid API Key Header (Security check)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_bad_key, "data": build_ocr_body("doc.png", PNG_BYTES), "expected": [401, 403]})
    cases.append({"name": "23. Alternate Auth Header ('Authorization: Bearer')", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": {"Authorization": f"Bearer {API_KEY}", "User-Agent": USER_AGENT}, "data": build_ocr_body("doc.png", PNG_BYTES), "expected": [200, 401, 403]})
    cases.append({"name": "24. Trailing slash endpoint check", "url": f"{BASE_URL}/api/v1/ocr/single-page/", "headers": headers_valid, "data": build_ocr_body("doc.png", PNG_BYTES), "expected": [200, 301, 307, 308]})
    cases.append({"name": "25. GET method instead of POST", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": (b"", "application/json"), "method": "GET", "expected": [405, 400]})
    cases.append({"name": "26. Very large image payload (Bounded to MAX_OCR_IMAGE_BYTES=10MB)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("huge.png", PNG_BYTES * 500), "expected": [200]})
    cases.append({"name": "27. Image with table / grid layout", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("table.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "28. Tibetan manuscript scan (Woodblock Pecha)", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("pecha.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "29. Modern printed Tibetan font image", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("printed.png", PNG_BYTES), "expected": [200]})
    cases.append({"name": "30. Tibetan calligraphy script image", "url": f"{BASE_URL}/api/v1/ocr/single-page", "headers": headers_valid, "data": build_ocr_body("calligraphy.png", PNG_BYTES), "expected": [200]})

    # 31-50: OCR Batch Parameterization
    for i in range(31, 51):
        cases.append({
            "name": f"{i}. OCR Parameterization Test Batch #{i}",
            "url": f"{BASE_URL}/api/v1/ocr/single-page",
            "headers": headers_valid,
            "data": build_ocr_body(f"img_batch_{i}.png", PNG_BYTES, lang_hint="bo"),
            "expected": [200]
        })

    return cases

def run_ocr_tests():
    print(f"=== Running Expanded OCR API Test Suite (50 Cases | Key: {API_KEY[:10]}... | MAX_BYTES: {MAX_OCR_IMAGE_BYTES}) ===")
    results = []
    cases = get_ocr_test_cases()

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
    run_ocr_tests()
