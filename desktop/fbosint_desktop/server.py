"""Local mode: run the shared FastAPI backend inside the desktop process."""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from collections.abc import Callable

import httpx

from .paths import ensure_backend_importable

log = logging.getLogger("fbosint.desktop.server")
APP_NAME = "FBOSINT Analyzer"


def port_free(port: int) -> bool:
    """True when nothing listens on 127.0.0.1:<port> and we are allowed to bind it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:  # reserved by Windows (Hyper-V / WinNAT ranges) or in use
            return False


def health(url: str, timeout: float = 1.5) -> dict | None:
    """Health check that never uses a proxy (loopback traffic)."""
    try:
        r = httpx.get(url.rstrip("/") + "/api/health", timeout=timeout, trust_env=False)
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


class _ErrorCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.exc_info and record.exc_info[1] is not None:
            exc = record.exc_info[1]
            msg = f"{type(exc).__name__}: {exc}"
        else:
            msg = record.getMessage()
            if "Traceback (most recent call last)" in msg:  # keep the line that states the cause
                import re

                errs = [ln.strip() for ln in msg.splitlines() if re.match(r"^[\w.]+(Error|Exception|Exit)\b.*", ln)]
                msg = errs[-1] if errs else msg.strip().splitlines()[-1]
        if "Application startup failed" in msg:
            return
        self.messages.append(msg.split("\n")[0][:300])


class LocalServer:
    def __init__(self, port: int = 8765, data_dir: str | None = None, extra_env: dict[str, str] | None = None):
        self.port = port
        self.data_dir = data_dir
        self.extra_env = extra_env or {}
        self.server = None
        self.thread: threading.Thread | None = None
        self.error: str = ""
        self.reused_existing = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def already_running(self) -> bool:
        h = health(self.url)
        return bool(h and h.get("status") == "ok" and h.get("app") == APP_NAME)

    def _pick_port(self) -> None:
        """Keep the configured port if possible; otherwise use the next free one."""
        if port_free(self.port):
            return
        for p in list(range(self.port + 1, self.port + 50)) + list(range(18765, 18815)):
            if port_free(p):
                log.warning("port %s is used by another program; using %s", self.port, p)
                self.port = p
                return
        raise RuntimeError(f"no_free_port_near:{self.port}")

    def start(self, timeout: float = 120.0, on_wait: Callable[[], None] | None = None) -> None:
        if self.already_running():  # e.g. FBOSINT-Server.exe already serving this machine
            self.reused_existing = True
            return
        self._pick_port()
        ensure_backend_importable()
        import uvicorn
        from fbosint.config import load_settings, set_settings

        env = dict(os.environ)
        if self.data_dir:
            env["FBO_DATA_DIR"] = self.data_dir
        env.update({"FBO_HOST": "127.0.0.1", "FBO_PORT": str(self.port), "FBO_MODE": "local"})
        env.update(self.extra_env)
        set_settings(load_settings(env))
        from fbosint.main import create_app

        console = sys.stdout is not None and sys.stderr is not None and hasattr(sys.stderr, "isatty")
        config = uvicorn.Config(create_app(), host="127.0.0.1", port=self.port, log_level="info", server_header=False, **({} if console else {"log_config": None}))
        self.server = uvicorn.Server(config)
        collector = _ErrorCollector()  # attached after uvicorn configured logging (dictConfig resets handlers)
        watched = ("uvicorn.error", "fbosint.main", "fbosint.database", "sqlalchemy")
        for name in watched:
            logging.getLogger(name).addHandler(collector)

        def run() -> None:
            try:
                self.server.run()
            except SystemExit as exc:  # uvicorn exits this way when start-up fails
                self.error = f"server_exit_code_{exc.code}"
            except BaseException as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                log.exception("local server crashed")

        self.thread = threading.Thread(target=run, name="fbosint-local-server", daemon=True)
        self.thread.start()
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                if self.already_running():
                    return
                if not self.thread.is_alive():  # failed during startup: report the real reason now
                    reason = " | ".join(m for m in collector.messages[-3:] if m) or self.error or "server_stopped_during_startup"
                    raise RuntimeError(reason)
                if on_wait:
                    on_wait()
                time.sleep(0.2)
            raise RuntimeError(f"local_server_start_timeout ({int(timeout)}s)")
        finally:
            for name in watched:
                logging.getLogger(name).removeHandler(collector)

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
            if self.thread:
                self.thread.join(timeout=10)
            self.server = None
