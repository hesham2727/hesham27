"""Desktop entry point.

  FBOSINT.exe                 normal start (Local or Network mode per desktop.json)
  FBOSINT.exe --self-test     headless smoke test: local server, setup, investigation,
                              report export, every window page; exit code 0 on success
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

from . import __version__, i18n
from .client import ApiClient, ApiError
from .server import LocalServer
from .settings import DesktopConfig, data_dir


def _verify(cfg: DesktopConfig):
    if cfg.mode == "network" and cfg.ca_bundle:
        return cfg.ca_bundle
    return cfg.verify_tls


def log_path() -> Path:
    return data_dir() / "logs" / "desktop.log"


def setup_logging() -> Path:
    """Always keep a diagnostic log: %APPDATA%\\FBOSINT\\logs\\desktop.log (rotated)."""
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        h = logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)
        root.setLevel(logging.INFO)
    return path


@dataclass
class Connection:
    api: ApiClient | None
    server: LocalServer | None
    error: str = ""

    @property
    def online(self) -> bool:
        return self.api is not None and not self.error


def connect_backend(cfg: DesktopConfig, on_wait=None, extra_env: dict[str, str] | None = None) -> Connection:
    """Shared by the GUI start-up and --self-test, so the tested path is the real one."""
    log = logging.getLogger("fbosint.desktop")
    log.info("FBOSINT Desktop %s starting: mode=%s port=%s frozen=%s", __version__, cfg.mode, cfg.local_port, getattr(sys, "frozen", False))
    server = None
    if cfg.mode == "local":
        server = LocalServer(cfg.local_port, extra_env=extra_env)
        try:
            server.start(on_wait=on_wait)
        except Exception as e:  # noqa: BLE001 - shown to the user with the log path
            log.exception("local server failed to start")
            return Connection(None, None, f"local_server: {e}")
        if server.port != cfg.local_port:  # configured port was taken by another program
            cfg.local_port = server.port
            try:
                cfg.save()
            except OSError:
                log.warning("could not save desktop.json")
        log.info("local server ready at %s (reused existing: %s)", server.url, server.reused_existing)
    api = ApiClient(cfg.base_url(), verify=_verify(cfg))
    try:
        api.health()
    except ApiError as e:
        log.error("health check failed for %s: %s", cfg.base_url(), e.code)
        return Connection(api, server, f"{cfg.base_url()}: {e.code}")
    return Connection(api, server)


def run_gui() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen

    from .ui import LoginDialog, MainWindow, apply_language, icon

    setup_logging()
    cfg = DesktopConfig.load()
    app = QApplication(sys.argv)
    app.setApplicationName("FBOSINT Analyzer")
    app.setWindowIcon(icon())
    apply_language(app, cfg.language)
    t = i18n.t
    while True:
        splash = QSplashScreen(icon().pixmap(256, 256))
        splash.show()
        splash.showMessage(t("startup.starting"), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, Qt.GlobalColor.white)
        app.processEvents()
        conn = connect_backend(cfg, on_wait=app.processEvents)
        splash.close()
        if conn.online:
            break
        box = QMessageBox(QMessageBox.Icon.Warning, t("app.name"), f"{t('startup.failed')}\n\n{conn.error}\n\n{t('startup.log')}:\n{log_path()}")
        retry = box.addButton(t("startup.retry"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(t("startup.offline"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not retry:
            break
    api, server, online = conn.api, conn.server, conn.online
    if online:
        try:
            dlg = LoginDialog(api, cfg, api.needs_setup())
        except ApiError as e:
            QMessageBox.warning(None, t("app.name"), f"{t('startup.failed')}\n{e.code}")
            online = False
    if online:
        if dlg.exec() != dlg.DialogCode.Accepted:
            if server:
                server.stop()
            return 0
        apply_language(app, api.user.get("language") or cfg.language)
    win = MainWindow(api if online else None, cfg, online)
    win.show()
    code = app.exec()
    if online:
        try:
            api.logout()
        except ApiError:
            pass
    if server:
        server.stop()
    return code


def _check(cond, msg="self-test assertion failed") -> None:
    if not cond:
        raise RuntimeError(str(msg))


def _report(text: str) -> None:
    """Windowed builds have no console: also write to FBO_SELFTEST_LOG if given."""
    log = os.environ.get("FBO_SELFTEST_LOG")
    if log:
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    if sys.stdout is not None:
        print(text)


def self_test() -> int:
    """Exercise the packaged application end to end without user interaction."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["FBO_DESKTOP_HEADLESS"] = "1"
    tmp = tempfile.mkdtemp(prefix="fbosint-selftest-")
    os.environ["FBO_DATA_DIR"] = tmp
    from PySide6.QtWidgets import QApplication

    from .ui import NAV, MainWindow, apply_language

    setup_logging()
    steps = []
    srv = None
    cfg = DesktopConfig(mode="local", reports_dir=os.path.join(tmp, "reports"))  # default port 8765, like a real first start
    try:
        conn = connect_backend(cfg, extra_env={"FBO_SCHEDULER_ENABLED": "1", "FBO_BACKUP_INTERVAL_HOURS": "24"})
        srv = conn.server
        _check(conn.online, f"start-up path failed: {conn.error}")
        steps.append(f"local server started on port {srv.port} via the normal start-up path")
        api = conn.api
        _check(api.needs_setup())
        api.setup("admin", "SelfTest12345", "Self Test")
        api.login("admin", "SelfTest12345")
        steps.append("setup + login")
        inv = api.post("/api/investigations", {"target": "https://www.facebook.com/example.page", "target_type": "page_url", "purpose": "Installation self-test", "options": {"download_media": False}})
        for _ in range(100):
            inv = api.get(f"/api/investigations/{inv['id']}")
            if inv["status"] not in ("pending", "running"):
                break
            import time
            time.sleep(0.2)
        _check(inv["status"] in ("partial", "completed"), inv["status"])
        steps.append(f"investigation {inv['reference']} -> {inv['status']}")
        pdf, _ = api.download(f"/api/investigations/{inv['id']}/report", format="pdf", lang="ar")
        xlsx, _ = api.download(f"/api/investigations/{inv['id']}/report", format="xlsx", lang="en")
        _check(pdf[:4] == b"%PDF" and xlsx[:2] == b"PK")
        steps.append("PDF + Excel export")
        app = QApplication.instance() or QApplication(sys.argv)
        apply_language(app, "ar")
        win = MainWindow(api, cfg, True)
        win.show()
        win.current_id = inv["id"]
        for key in NAV:
            win.navigate(key)
            app.processEvents()
        saved = win.pages["export"].export("pdf", open_after=False)
        _check(saved and saved.exists())
        steps.append("all desktop pages rendered; report cached for offline use")
        from pathlib import Path
        backups = list((Path(tmp) / "backups").glob("*.zip"))
        steps.append(f"automatic backups: {len(backups)}")
        win.close()
        _report("SELF-TEST OK\n  " + "\n  ".join(steps))
        return 0
    except Exception:
        _report("SELF-TEST FAILED after: " + " | ".join(steps) + "\n" + traceback.format_exc())
        return 1
    finally:
        if srv:
            srv.stop()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="FBOSINT", description=f"FBOSINT Analyzer Desktop {__version__}")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--version", action="store_true")
    a = p.parse_args(argv)
    if a.version:
        print(__version__)
        return 0
    if a.self_test:
        return self_test()
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
