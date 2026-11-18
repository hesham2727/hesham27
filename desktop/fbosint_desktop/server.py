"""Local mode: run the shared FastAPI backend inside the desktop process."""
from __future__ import annotations

import socket
import threading
import time

import httpx

from .paths import ensure_backend_importable


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


class LocalServer:
    def __init__(self, port: int = 8765, data_dir: str | None = None, extra_env: dict[str, str] | None = None):
        self.port = port
        self.data_dir = data_dir
        self.extra_env = extra_env or {}
        self.server = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def already_running(self) -> bool:
        try:
            return httpx.get(self.url + "/api/health", timeout=1.5).json().get("status") == "ok"
        except Exception:
            return False

    def start(self, timeout: float = 30.0) -> None:
        if self.already_running():  # e.g. FBOSINT-Server.exe already serving this machine
            return
        if not port_free(self.port):
            raise RuntimeError(f"port_in_use:{self.port}")
        ensure_backend_importable()
        import uvicorn
        from fbosint.config import load_settings, set_settings
        import os

        env = dict(os.environ)
        if self.data_dir:
            env["FBO_DATA_DIR"] = self.data_dir
        env.update({"FBO_HOST": "127.0.0.1", "FBO_PORT": str(self.port), "FBO_MODE": "local"})
        env.update(self.extra_env)
        set_settings(load_settings(env))
        from fbosint.main import create_app

        config = uvicorn.Config(create_app(), host="127.0.0.1", port=self.port, log_level="warning", server_header=False)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="fbosint-local-server", daemon=True)
        self.thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.already_running():
                return
            time.sleep(0.2)
        raise RuntimeError("local_server_failed_to_start")

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
            if self.thread:
                self.thread.join(timeout=10)
            self.server = None
