"""Launch TEEA Daemon HTTP Bridge for Microsoft Word Add-in on 127.0.0.1:50505."""
import os
import sys
import time
from pathlib import Path
from teea.engine import TEEAEngine
from teea.transport import serve_http


def default_db_path() -> Path:
    """Locate the plagiarism fingerprint database (built by ``teea plagiarism build-index``)."""
    env_path = os.environ.get("TEEA_DB_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent / "Data" / "Processed" / "teea.db"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("Starting TEEA Daemon for Microsoft Word Add-in on http://127.0.0.1:50505...")
    db_path = default_db_path()
    print(f"Plagiarism database: {db_path} (exists: {db_path.exists()})")
    engine = TEEAEngine(db_path=db_path)
    loaded_plugins = [p.name for p in engine._plugins]
    print(f"Loaded active plugins: {loaded_plugins}")
    corpus_size = engine.plagiarism_engine.size if engine.plagiarism_engine is not None else 0
    print(f"Plagiarism corpus documents loaded: {corpus_size}")
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
