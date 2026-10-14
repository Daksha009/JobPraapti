"""Launch the local website and open a tab when it is ready."""

import json
import socket
import threading
import time
from urllib.request import urlopen
import asyncio

from jobpilot.config import settings
from jobpilot.dashboard.app import create_app
from waitress import serve
from jobpilot.workspace_browser import open_workspace


def open_chrome(url):
    """Open the workspace in installed Chrome without changing browser defaults."""
    asyncio.run(open_workspace())


def ready(url):
    try:
        with urlopen(url + "/api/bootstrap", timeout=1) as response:
            data = json.load(response)
        return "token" in data and "timezone" in data and data.get("version") == "0.3.0"
    except Exception:
        return False


def main():
    port = settings.dashboard_port
    url = f"http://127.0.0.1:{port}"
    if ready(url):
        open_chrome(url)
        print("Opened your running JobPraapti workspace.")
        return
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(
                f"Port {port} is in use. Set DASHBOARD_PORT in .env to an unused port."
            )

    def open_when_ready():
        for _ in range(40):
            if ready(url):
                open_chrome(url)
                return
            time.sleep(0.25)

    threading.Thread(target=open_when_ready, daemon=True).start()
    print(
        f"JobPraapti: {url}\nKeep this window open. Press Ctrl+C to stop the website."
    )
    serve(
        create_app(),
        host="127.0.0.1",
        port=port,
        threads=6,
        max_request_body_size=6 * 1024 * 1024,
    )


if __name__ == "__main__":
    main()
