"""Entrypoint:  python app/server.py"""

from __future__ import annotations

import socket
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.adapters.json_config import JsonConfigStore  # noqa: E402
from app.adapters.json_store import StoreError  # noqa: E402
from app.api.application import VERSION, Application  # noqa: E402
from app.api.handlers import Handler  # noqa: E402


def pick_port(preferred: int, attempts: int = 30) -> int:
    for offset in range(attempts):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"no free port in {preferred}..{preferred + attempts - 1}")


def main() -> None:
    config = JsonConfigStore(BASE_DIR / "config.json").load()
    app = Application(config, BASE_DIR)
    Handler.app = app
    try:
        app.repo.load_venues()
    except StoreError as exc:
        print(f"[fatal] {exc}")
        raise SystemExit(1)

    port = pick_port(config.port)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    app.reminders.start()
    app.scheduler.start()
    app.verifier_job.start()

    print("=" * 62)
    print(f"  CFP Keeper  v{VERSION}")
    print(f"  http://127.0.0.1:{port}/")
    print(f"  venues={len(app.repo.load_venues().get('venues', []))}  data={BASE_DIR / 'data'}")
    if port != config.port:
        print(f"  note: preferred port was busy, using {port}")
    print("=" * 62)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down…")
    finally:
        app.reminders.stop()
        app.scheduler.stop()
        app.verifier_job.stop()
        server.server_close()


if __name__ == "__main__":
    main()
