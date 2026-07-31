#!/usr/bin/env python3
"""Wait until TEEA Daemon HTTP server is active and responding on /health."""

import sys
import time
import urllib.request
import urllib.error

def wait_for_daemon(url: str = "http://127.0.0.1:50505/health", max_wait_sec: float = 30.0) -> bool:
    start_time = time.time()
    print(f"Waiting for TEEA Daemon to become ready on {url}...")
    while time.time() - start_time < max_wait_sec:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TEEA-HealthCheck"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    print(f"TEEA Daemon is READY on {url} ({time.time() - start_time:.1f}s)")
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionRefusedError, OSError):
            time.sleep(0.5)
    print(f"Timed out after {max_wait_sec}s waiting for {url}")
    return False

if __name__ == "__main__":
    success = wait_for_daemon()
    sys.exit(0 if success else 1)
