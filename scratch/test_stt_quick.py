import urllib.request
import json

API_KEY = "REPLACE_WITH_MONLAM_API_KEY"

def test_stt():
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    wav_header = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode("utf-8"),
        wav_header,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nbo\r\n".encode("utf-8"),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"task\"\r\n\r\ntranscribe\r\n".encode("utf-8"),
        f"--{boundary}--\r\n".encode("utf-8")
    ]
    body = b"".join(parts)

    req = urllib.request.Request(
        "https://api-v1.monlamai.studio/api/v1/speech-to-text/",
        data=body,
        headers={
            "X-API-Key": API_KEY,
            "User-Agent": "Mozilla/5.0",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            print("STT Status:", resp.status)
            print("STT Response:", resp.read().decode("utf-8"))
    except Exception as e:
        print("STT Error:", e)
        if hasattr(e, 'read'):
            print("Error body:", e.read().decode('utf-8'))

def test_ocr():
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x03\x00\x05\xfe\x02\xfe\xa7\x96a\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
    
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.png\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8"),
        png_bytes,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"lang_hint\"\r\n\r\nbo\r\n".encode("utf-8"),
        f"--{boundary}--\r\n".encode("utf-8")
    ]
    body = b"".join(parts)

    req = urllib.request.Request(
        "https://api-v1.monlamai.studio/api/v1/ocr/single-page",
        data=body,
        headers={
            "X-API-Key": API_KEY,
            "User-Agent": "Mozilla/5.0",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            print("OCR Status:", resp.status)
            print("OCR Response:", resp.read().decode("utf-8"))
    except Exception as e:
        print("OCR Error:", e)
        if hasattr(e, 'read'):
            print("Error body:", e.read().decode('utf-8'))

if __name__ == "__main__":
    test_stt()
    test_ocr()
