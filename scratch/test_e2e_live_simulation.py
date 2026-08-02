import requests
import psutil
import time
import json
import io
import sys

# Fix stdout for windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DAEMON_URL = "http://localhost:50505"

def get_daemon_process():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info['cmdline']
            if cmd and 'python' in proc.info['name'].lower() and any('server.py' in c for c in cmd):
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None

def wait_for_daemon():
    print("Waiting for daemon to become healthy...")
    for _ in range(30):
        try:
            res = requests.get(f"{DAEMON_URL}/health")
            if res.status_code == 200:
                print("Daemon is UP and HEALTHY!")
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False

def test_nlp_pipeline(proc):
    print("\n--- Sending E2E Requests to Daemon ---")
    
    # Generate a large Tibetan document simulation
    payload_text = "བཀྲ་ཤིས་བདེ་ལེགས hello world སློབ་སྦྱོང " * 500
    
    start_time = time.time()
    
    response = requests.post(f"{DAEMON_URL}/api/analysis/run", json={"text": payload_text})
    
    end_time = time.time()
    
    print(f"Request took {end_time - start_time:.2f} seconds")
    print(f"Response Status: {response.status_code}")
    
    if proc:
        cpu = proc.cpu_percent(interval=0.1)
        mem = proc.memory_info().rss / (1024 * 1024)
        print(f"Daemon Metrics -> CPU: {cpu}% | RAM: {mem:.2f} MB")
        
    data = response.json()
    suggestions = data.get("suggestions", [])
    print(f"Found {len(suggestions)} suggestions via the live HTTP IPC bridge.")
    
    if len(suggestions) > 0:
        print("E2E Integration Success: IPC returning valid results!")
    else:
        print("E2E Integration Warning: No suggestions found, but request succeeded.")
        
    return data

if __name__ == "__main__":
    if not wait_for_daemon():
        print("Error: Daemon did not start.")
        sys.exit(1)
        
    proc = get_daemon_process()
    if proc:
        print(f"Tracking Daemon Process ID: {proc.pid}")
        # Initialize CPU percent
        proc.cpu_percent(interval=None)
    else:
        print("Warning: Could not find daemon process for telemetry.")
        
    test_nlp_pipeline(proc)
