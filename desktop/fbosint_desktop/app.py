"""Desktop entry point.

  FBOSINT.exe                 normal start (Local or Network mode per desktop.json)
  FBOSINT.exe --self-test     headless smoke test: local server, setup, investigation,
                              report export, every window page; exit code 0 on success
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback

from . import __version__, i18n
from .settings import DesktopConfig


def _verify(cfg: DesktopConfig):
    if cfg.mode == "network" and cfg.ca_bundle:
        return cfg.ca_bundle
    return cfg.verify_tls


def run_gui() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .client import ApiClient, ApiError
    from .server import LocalServer
    from .ui import LoginDialog, MainWindow, apply_language, icon

    cfg = DesktopConfig.load()
    app = QApplication(sys.argv)
    app.setApplicationName("FBOSINT Analyzer")
    app.setWindowIcon(icon())
    apply_language(app, cfg.language)
    server = None
    if cfg.mode == "local":
        server = LocalServer(cfg.local_port)
        try:
            server.start()
        except Exception as e:
            QMessageBox.critical(None, "FBOSINT", f"Local server could not start: {e}")
            server = None
    api = ApiClient(cfg.base_url(), verify=_verify(cfg))
    try:
        api.health()
        online = True
    except ApiError:
        online = False
    if online:
        try:
            dlg = LoginDialog(api, cfg, api.needs_setup())
        except ApiError:
            online = False
    if online:
        if dlg.exec() != dlg.DialogCode.Accepted:
            return 0
        apply_language(app, api.user.get("language") or cfg.language)
    else:
        QMessageBox.information(None, "FBOSINT", f"{i18n.t('err.network')}\n{cfg.base_url()}\n\nOffline mode: previously exported reports are available.")
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


def self_test() -> int:
    """Exercise the packaged application end to end without user interaction."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["FBO_DESKTOP_HEADLESS"] = "1"
    tmp = tempfile.mkdtemp(prefix="fbosint-selftest-")
    os.environ["FBO_DATA_DIR"] = tmp
    from PySide6.QtWidgets import QApplication

    from .client import ApiClient
    from .server import LocalServer, port_free
    from .ui import NAV, MainWindow, apply_language

    port = next(p for p in range(18765, 18865) if port_free(p))
    steps = []
    srv = LocalServer(port, tmp, {"FBO_SCHEDULER_ENABLED": "1", "FBO_BACKUP_INTERVAL_HOURS": "24"})
    try:
        srv.start()
        steps.append("local server started")
        api = ApiClient(srv.url)
        assert api.needs_setup()
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
        assert inv["status"] in ("partial", "completed"), inv["status"]
        steps.append(f"investigation {inv['reference']} -> {inv['status']}")
        pdf, _ = api.download(f"/api/investigations/{inv['id']}/report", format="pdf", lang="ar")
        xlsx, _ = api.download(f"/api/investigations/{inv['id']}/report", format="xlsx", lang="en")
        assert pdf[:4] == b"%PDF" and xlsx[:2] == b"PK"
        steps.append("PDF + Excel export")
        app = QApplication.instance() or QApplication(sys.argv)
        apply_language(app, "ar")
        cfg = DesktopConfig(mode="local", local_port=port, reports_dir=os.path.join(tmp, "reports"))
        win = MainWindow(api, cfg, True)
        win.show()
        win.current_id = inv["id"]
        for key in NAV:
            win.navigate(key)
            app.processEvents()
        saved = win.pages["export"].export("pdf", open_after=False)
        assert saved and saved.exists()
        steps.append("all desktop pages rendered; report cached for offline use")
        from pathlib import Path
        backups = list((Path(tmp) / "backups").glob("*.zip"))
        steps.append(f"automatic backups: {len(backups)}")
        win.close()
        print("SELF-TEST OK\n  " + "\n  ".join(steps))
        return 0
    except Exception:
        print("SELF-TEST FAILED after: " + " | ".join(steps))
        traceback.print_exc()
        return 1
    finally:
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
