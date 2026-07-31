"""Launch TEEA Daemon HTTP Bridge for Microsoft Word Add-in on 127.0.0.1:50505."""
import sys
import time
from teea.engine import TEEAEngine
from teea.transport import serve_http

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("Starting TEEA Daemon for Microsoft Word Add-in on http://127.0.0.1:50505...")
    engine = TEEAEngine()
    loaded_plugins = [p.name for p in engine._plugins]
    print(f"Loaded active plugins: {loaded_plugins}")
    server = serve_http(
        builder=engine._builder,
        plugins=engine._plugin_runtime,
        fusion=engine._fusion,
        host="127.0.0.1",
        port=50505,
    )
    print(f"TEEA Daemon is active and serving complete HTTP+AI bridge at {server.base_url}")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        print("TEEA Daemon stopped.")

if __name__ == "__main__":
    main()
