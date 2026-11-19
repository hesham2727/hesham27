"""Phase 5: desktop client, shared backend synchronisation, UI pages, offline mode."""
import time

import httpx
import pytest
from PySide6.QtCore import Qt

from fbosint_desktop import i18n, offline, updates
from fbosint_desktop.client import ApiClient, ApiError
from fbosint_desktop.settings import DesktopConfig
from fbosint_desktop.ui import NAV, LoginDialog, MainWindow, apply_language

PW = "Desk7opPassw0rd"


def wait_done(api, iid):
    for _ in range(150):
        inv = api.get(f"/api/investigations/{iid}")
        if inv["status"] not in ("pending", "running"):
            return inv
        time.sleep(0.1)
    raise AssertionError("investigation did not finish")


@pytest.fixture(scope="module")
def desk(live_server):
    api = ApiClient(live_server.url)
    if api.needs_setup():
        api.setup("admin", PW, "Desktop Admin")
    api.login("admin", PW)
    api.put("/api/settings/meta", {"access_token": "PAGE_TOKEN"})
    inv = api.post("/api/investigations", {"target": "https://www.facebook.com/qusoorfacades", "target_type": "page_url", "purpose": "Desktop sync test", "extra_urls": ["https://directory.example.org/q"]})
    return api, wait_done(api, inv["id"])


def web_session(url):
    """A browser-like client: cookie session + CSRF header (what the React app does)."""
    c = httpx.Client(base_url=url)
    r = c.post("/api/auth/login", json={"username": "admin", "password": PW, "client": "web"})
    assert r.status_code == 200 and r.json()["token"] is None
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


def test_web_and_desktop_share_records(live_server, desk):
    api, inv = desk
    assert inv["status"] == "completed"
    web = web_session(live_server.url)
    listed = web.get("/api/investigations").json()["items"]
    assert any(i["reference"] == inv["reference"] for i in listed)
    # web adds a manual observation -> desktop sees it immediately
    r = web.post(f"/api/investigations/{inv['id']}/datapoints", json={"category": "observation", "field": "web_note", "value": "added from browser", "source_url": "https://example.org/x"})
    assert r.status_code == 201
    assert any(d["field"] == "web_note" for d in api.get(f"/api/investigations/{inv['id']}/datapoints"))
    # desktop creates an investigation -> web sees it
    created = api.post("/api/investigations", {"target": "qusoorfacades", "purpose": "created on desktop", "start": False})
    assert web.get(f"/api/investigations/{created['id']}").json()["reference"] == created["reference"]
    # both export identical-content reports from the same data
    pdf_web = web.get(f"/api/investigations/{inv['id']}/report", params={"format": "xlsx", "lang": "en"})
    data, name = api.download(f"/api/investigations/{inv['id']}/report", format="xlsx", lang="en")
    assert pdf_web.status_code == 200 and data[:2] == b"PK" and name.startswith(inv["reference"])
    api.delete(f"/api/investigations/{created['id']}")
    assert web.get(f"/api/investigations/{created['id']}").status_code == 404


def test_client_errors(live_server):
    api = ApiClient(live_server.url)
    with pytest.raises(ApiError) as e:
        api.login("admin", "wrong-password")
    assert e.value.code == "invalid_credentials"
    with pytest.raises(ApiError) as e:
        api.get("/api/dashboard")
    assert e.value.status == 401
    dead = ApiClient("http://127.0.0.1:9")
    with pytest.raises(ApiError) as e:
        dead.health()
    assert e.value.code == "network"


def test_login_dialog(qtbot, live_server):
    i18n.set_lang("ar")
    api = ApiClient(live_server.url)
    cfg = DesktopConfig()
    cfg.save = lambda: None
    dlg = LoginDialog(api, cfg, needs_setup=False)
    qtbot.addWidget(dlg)
    dlg.username.setText("admin")
    dlg.password.setText("bad")
    dlg.submit()
    assert "غير صحيحة" in dlg.err.text()  # Arabic error message
    dlg.password.setText(PW)
    dlg.submit()
    assert api.token and dlg.result() == dlg.DialogCode.Accepted


def test_main_window_pages(qtbot, desk, tmp_path):
    from PySide6.QtWidgets import QApplication
    api, inv = desk
    apply_language(QApplication.instance(), "ar")
    assert QApplication.instance().layoutDirection() == Qt.LayoutDirection.RightToLeft
    cfg = DesktopConfig(reports_dir=str(tmp_path / "reports"))
    win = MainWindow(api, cfg, True)
    qtbot.addWidget(win)
    win.show()
    dash = win.navigate("dashboard")
    assert int(dash.stats["investigations"].text()) >= 1
    hist = win.navigate("history")
    assert hist.table.rowCount() >= 1
    win.open_investigation(inv["id"])
    prof = win.pages["profile"]
    assert prof.table.rowCount() > 5 and inv["reference"] in prof.header.text()
    texts = {prof.table.item(r, 1).text() for r in range(prof.table.rowCount())}
    assert "Qusoor Facades Co." in texts
    contacts = win.navigate("contacts")
    vals = {contacts.table.item(r, 1).text() for r in range(contacts.table.rowCount())}
    assert "sales@qusoor.example.sa" in vals
    posts = win.navigate("posts")
    assert posts.table.rowCount() == 3
    posts.q.setText("glazing")
    posts.refresh()
    assert posts.table.rowCount() == 1
    media = win.navigate("media")
    assert media.table.rowCount() >= 4 and media.table.cellWidget(0, 0) is not None  # thumbnail
    sources = win.navigate("sources")
    assert sources.table.rowCount() >= 4
    exp = win.navigate("export")
    path = exp.export("pdf", open_after=False)
    assert path.exists() and path.read_bytes()[:4] == b"%PDF"
    assert exp.local.rowCount() == 1
    win.navigate("settings")
    win.grab().save(str(tmp_path / "desktop.png"))


def test_offline_mode_lists_cached_reports(qtbot, tmp_path):
    offline.save_report(str(tmp_path), "INV-20260101-ABCDEF-ar.pdf", b"%PDF-1.4 test")
    cfg = DesktopConfig(reports_dir=str(tmp_path), mode="network", server_url="https://unreachable.invalid")
    win = MainWindow(None, cfg, online=False)
    qtbot.addWidget(win)
    assert set(win.pages) == {"export", "settings"}
    exp = win.pages["export"]
    assert exp.local.rowCount() == 1 and not exp.pdf.isEnabled()
    assert [win.nav.item(i).isHidden() for i in range(len(NAV))].count(False) == 2


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FBO_DATA_DIR", str(tmp_path))
    c = DesktopConfig(mode="network", server_url="https://srv:8765/", language="en")
    c.save()
    c2 = DesktopConfig.load()
    assert c2.mode == "network" and c2.base_url() == "https://srv:8765"
    (tmp_path / "desktop.json").write_text("{corrupt")
    assert DesktopConfig.load().mode == "local"


def test_update_check():
    def h(req):
        return httpx.Response(200, json={"version": "9.9.0", "url": "https://downloads.example.com/FBOSINT-Setup-9.9.0.exe"})
    assert updates.check("https://updates.example.com/m.json", transport=httpx.MockTransport(h))["version"] == "9.9.0"
    assert updates.check("http://insecure.example.com/m.json") is None
    old = httpx.MockTransport(lambda r: httpx.Response(200, json={"version": "0.9.0", "url": "https://x"}))
    assert updates.check("https://u.example.com/m.json", transport=old) is None


def test_shared_dictionary_used():
    i18n.set_lang("en")
    assert i18n.t("nav.dashboard") == "Investigation Dashboard"
    i18n.set_lang("ar")
    assert i18n.t("nav.dashboard") == "لوحة التحقيقات"
    assert i18n.enum("status", "partial") == "جزئي"


def test_windowed_build_without_console(tmp_path):
    """Regression: windowed Windows builds run with sys.stdout/stderr = None."""
    import os, subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    code = ("import sys, runpy; sys.stdout = None; sys.stderr = None; sys.argv = ['FBOSINT', '--self-test']\n"
            "try:\n    runpy.run_path(r'%s', run_name='__main__')\nexcept SystemExit as e:\n    open(r'%s', 'w').write(str(e.code))\n") % (root / "desktop" / "run_desktop.py", tmp_path / "rc")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "FBO_SELFTEST_LOG": str(tmp_path / "st.log"), "FBO_DATA_DIR": str(tmp_path / "d")}
    subprocess.run([sys.executable, "-c", code], env=env, timeout=240, check=False)
    assert (tmp_path / "rc").read_text() == "0", (tmp_path / "st.log").read_text() if (tmp_path / "st.log").exists() else "no log"
    assert "SELF-TEST OK" in (tmp_path / "st.log").read_text()
    assert (tmp_path / "d" / "logs" / "desktop.log").exists()


def _run_isolated(code: str, tmp_path, extra_env: dict | None = None, timeout=240):
    """Run start-up code in a fresh process (LocalServer sets process-wide settings)."""
    import os, subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    prelude = f"import sys; sys.path[:0] = [r'{root / 'desktop'}', r'{root / 'backend'}']\n"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "FBO_DATA_DIR": str(tmp_path / "d"), **(extra_env or {})}
    return subprocess.run([sys.executable, "-c", prelude + code], env=env, timeout=timeout, capture_output=True, text=True)


def test_direct_connection_rules():
    from fbosint_desktop.client import direct_connection
    for u in ["http://127.0.0.1:8765", "http://localhost:8765", "https://192.168.1.10:8765", "https://10.0.0.5", "https://fbosint-server:8765", "https://srv.local"]:
        assert direct_connection(u), u
    for u in ["https://fbosint.example.com", "https://8.8.8.8"]:
        assert not direct_connection(u), u


def test_startup_with_system_proxy_and_busy_port(tmp_path):
    """Regression for 'cannot reach the server' on first launch: Windows proxy + port 8765 taken."""
    import socket
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 8765))
    blocker.listen()
    try:
        r = _run_isolated(
            "from fbosint_desktop.app import connect_backend, setup_logging\n"
            "from fbosint_desktop.settings import DesktopConfig\n"
            "setup_logging(); cfg = DesktopConfig()\n"
            "c = connect_backend(cfg, extra_env={'FBO_SCHEDULER_ENABLED': '0'})\n"
            "print('RESULT', c.online, cfg.local_port, c.error)\n"
            "print('SAVED', DesktopConfig.load().local_port)\n"
            "c.server.stop()\n",
            tmp_path, {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "", "no_proxy": ""})
    finally:
        blocker.close()
    out = r.stdout
    assert "RESULT True" in out, r.stdout + r.stderr
    port = int(out.split("RESULT True ")[1].split()[0])
    assert port != 8765 and f"SAVED {port}" in out  # moved to a free port and remembered it


def test_startup_failure_reports_reason_quickly(tmp_path):
    import time
    t0 = time.time()
    r = _run_isolated(
        "from fbosint_desktop.app import connect_backend, setup_logging, log_path\n"
        "from fbosint_desktop.settings import DesktopConfig\n"
        "setup_logging(); c = connect_backend(DesktopConfig(local_port=19777), extra_env={'FBO_SCHEDULER_ENABLED': '0', 'FBO_DATABASE_URL': 'sqlite:////nonexistent-dir/x/y.db'})\n"
        "print('RESULT', c.online, '|', c.error); print('LOG', log_path().exists())\n",
        tmp_path)
    assert "RESULT False" in r.stdout and "local_server" in r.stdout, r.stdout + r.stderr
    assert "unable to open database" in r.stdout.lower() or "operationalerror" in r.stdout.lower(), r.stdout
    assert "LOG True" in r.stdout
    assert time.time() - t0 < 60  # not the full start-up timeout
