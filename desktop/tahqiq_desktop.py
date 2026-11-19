"""Tahqiq – Windows desktop shell.

Runs the shared FastAPI backend locally on 127.0.0.1 (random free port) and
shows the same React production build inside Qt WebEngine. No external
service is required; data lives in %LOCALAPPDATA%\\Tahqiq.

Optional: run with --public-port 8001 (or set TAHQIQ_PUBLIC_PORT) to also start the PUBLIC-ONLY
consent server on 127.0.0.1:<port>, which can be exposed with a free
Cloudflare quick tunnel for customer invitations (see docs).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("TAHQIQ_MODE", "desktop")


def _ensure_std_streams() -> None:
    """A windowed (no-console) Windows build starts with sys.stdout/stderr = None.

    Uvicorn's logging setup calls sys.stdout.isatty() and would crash, so send
    all output to <data dir>/logs/desktop.log instead.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    base = os.environ.get("TAHQIQ_DATA_DIR")
    if not base:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = str(Path(local) / "Tahqiq") if sys.platform == "win32" else str(Path.home() / ".tahqiq")
    log_dir = Path(base) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = open(log_dir / "desktop.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_ensure_std_streams()

# Make the backend package importable when running from source.
_HERE = Path(__file__).resolve().parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(_HERE.parent / "backend"))

import uvicorn  # noqa: E402
from PySide6.QtCore import QUrl, Qt  # noqa: E402
from PySide6.QtGui import QDesktopServices, QIcon  # noqa: E402
from PySide6.QtWebEngineCore import (  # noqa: E402
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox  # noqa: E402

from app import __version__  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import create_app, create_public_app  # noqa: E402

APP_NAME = "Tahqiq – منصة التحقق من الأرقام"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BackendThread(threading.Thread):
    def __init__(self, app_factory, port: int) -> None:
        super().__init__(daemon=True)
        config = uvicorn.Config(app_factory(), host="127.0.0.1", port=port, log_level="warning", access_log=False)
        self.server = uvicorn.Server(config)
        self.port = port

    def run(self) -> None:
        self.server.run()

    def wait_ready(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=1)
                return True
            except Exception:
                time.sleep(0.15)
        return False

    def stop(self) -> None:
        self.server.should_exit = True


class Page(QWebEnginePage):
    """Keeps the app inside the window; opens external links in the system browser."""

    def __init__(self, profile: QWebEngineProfile, origin: str, parent=None) -> None:
        super().__init__(profile, parent)
        self.origin = origin

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # noqa: N802
        if url.toString().startswith(self.origin):
            return True
        QDesktopServices.openUrl(url)  # wa.me, sms:, https source links
        return False

    def createWindow(self, _type):  # noqa: N802  (target=_blank)
        popup = Page(self.profile(), self.origin, self)
        popup.urlChanged.connect(lambda u: (QDesktopServices.openUrl(u), popup.deleteLater()))
        return popup


class MainWindow(QMainWindow):
    def __init__(self, base_url: str, data_dir: Path) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} – {__version__}")
        self.resize(1366, 860)
        self.setLayoutDirection(Qt.RightToLeft)
        icon = _HERE / "tahqiq.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.profile = QWebEngineProfile("tahqiq", self)
        self.profile.setPersistentStoragePath(str(data_dir / "webengine"))
        self.profile.setCachePath(str(data_dir / "webengine-cache"))
        self.profile.downloadRequested.connect(self.on_download)
        s = self.profile.settings()
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)

        self.view = QWebEngineView(self)
        self.view.setPage(Page(self.profile, base_url, self.view))
        self.view.setUrl(QUrl(base_url + "/"))
        self.setCentralWidget(self.view)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Delete the page before its profile to avoid WebEngine shutdown warnings.
        page = self.view.page()
        self.view.setPage(QWebEnginePage(self.view))
        page.deleteLater()
        super().closeEvent(event)

    def on_download(self, req: QWebEngineDownloadRequest) -> None:
        suggested = str(Path.home() / "Documents" / req.suggestedFileName())
        path, _ = QFileDialog.getSaveFileName(self, "حفظ الملف", suggested)
        if not path:
            req.cancel()
            return
        p = Path(path)
        req.setDownloadDirectory(str(p.parent))
        req.setDownloadFileName(p.name)
        req.accept()
        req.isFinishedChanged.connect(
            lambda: req.isFinished() and req.state() == QWebEngineDownloadRequest.DownloadCompleted
            and QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        )


def main() -> int:
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Tahqiq")
    qt_app.setLayoutDirection(Qt.RightToLeft)

    settings = get_settings()
    settings.ensure_dirs()
    port = free_port()
    backend = BackendThread(create_app, port)
    backend.start()
    if not backend.wait_ready():
        QMessageBox.critical(None, "Tahqiq", "تعذر تشغيل الخادم المحلي. راجع صلاحيات مجلد البيانات:\n" + str(settings.data_dir))
        return 1

    public = None
    public_port = os.environ.get("TAHQIQ_PUBLIC_PORT")
    if "--public-port" in sys.argv:
        idx = sys.argv.index("--public-port")
        public_port = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
    if public_port:
        # Requests on the public port arrive through a local tunnel (cloudflared),
        # so the real client IP is in CF-Connecting-IP / X-Forwarded-For.
        settings.trust_proxy = True
        public = BackendThread(create_public_app, int(public_port))
        public.start()
        public.wait_ready()

    win = MainWindow(f"http://127.0.0.1:{port}", settings.data_dir)
    win.show()
    if os.environ.get("TAHQIQ_DESKTOP_SMOKE"):  # used by automated checks: quit after load
        from PySide6.QtCore import QTimer

        def report(ok: bool) -> None:
            def dump(text) -> None:
                print(("LOAD_OK " if ok else "LOAD_FAIL ") + str(text)[:200].replace("\n", " | "), flush=True)
                win.close()
                qt_app.quit()

            QTimer.singleShot(2500, lambda: win.view.page().runJavaScript("document.body.innerText", 0, dump))

        win.view.loadFinished.connect(report)
    code = qt_app.exec()
    backend.stop()
    if public:
        public.stop()
    backend.join(timeout=5)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
