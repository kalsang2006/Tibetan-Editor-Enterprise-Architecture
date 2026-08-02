import urllib.request
import json
import sys

BASE_URL = "http://127.0.0.1:50505"

def send_request(path, payload):
    req = urllib.request.Request(f"{BASE_URL}{path}", method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=json.dumps(payload).encode('utf-8')) as res:
            return res.read().decode('utf-8'), res.status
    except Exception as e:
        return str(e), 500

def test():
    print("Testing Daemon Endpoints...")
    
    # 1. Health
    print("1. Health Check")
    try:
        res = urllib.request.urlopen(f"{BASE_URL}/health")
        print(f"Health status: {res.status}")
    except Exception as e:
        print(f"Health check failed: {e}")
        
    # 2. Dictionary Lookup
    print("\n2. Dictionary Lookup")
    payload = {
        "protocol_version": "1.0",
        "request_id": "test-1",
        "method": "dictionary.lookup",
        "params": {"query": "བཀྲ་ཤིས་བདེ་ལེགས", "language": "bo-en"}
    }
    body, status = send_request("/api/dictionary/lookup", payload)
    print(f"Status: {status}\nResponse: {body[:200]}")

if __name__ == "__main__":
    test()
