"""PySide6 user interface. All data comes from the shared REST API via ApiClient."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import __version__, i18n, offline, updates
from .client import ApiClient, ApiError
from .i18n import enum, t
from .paths import resource_root
from .settings import DesktopConfig

STYLE = """
QMainWindow, QDialog { background: #f3f5f9; }
#sidebar { background: #1f3a5f; color: #dfe8f3; border: none; font-size: 13px; }
#sidebar::item { padding: 9px 10px; border-radius: 6px; margin: 1px 6px; }
#sidebar::item:selected { background: #2f86d6; color: white; }
#brand { color: white; font-weight: bold; font-size: 15px; padding: 14px; background: #1f3a5f; }
QGroupBox { background: white; border: 1px solid #dde3ec; border-radius: 8px; margin-top: 14px; padding: 10px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; right: 10px; padding: 0 4px; color: #1f3a5f; }
QPushButton { background: white; border: 1px solid #c9d3e0; border-radius: 6px; padding: 6px 14px; }
QPushButton:hover { border-color: #2f86d6; }
QPushButton#primary { background: #2f86d6; color: white; border-color: #2f86d6; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: white; border: 1px solid #c9d3e0; border-radius: 6px; padding: 5px; }
QTableWidget { background: white; border: 1px solid #dde3ec; gridline-color: #eef1f5; }
QHeaderView::section { background: #f6f8fb; border: none; border-bottom: 1px solid #dde3ec; padding: 6px; color: #6b7686; font-weight: bold; }
#statValue { font-size: 24px; font-weight: bold; color: #1f3a5f; }
#banner { background: #fff4d6; color: #9a6a00; padding: 8px; border-radius: 6px; }
#info { background: #e6f0fb; color: #1d5fa3; padding: 8px; border-radius: 6px; }
"""


def icon() -> QIcon:
    for p in (resource_root() / "assets" / "fbosint.ico", resource_root() / "assets" / "fbosint.png"):
        if p.exists():
            return QIcon(str(p))
    return QIcon()


def error_text(e: ApiError) -> str:
    k = f"err.{e.code}"
    msg = t(k)
    return msg if msg != k else f"{t('err.generic')} ({e.code})"


def show_error(parent: QWidget, e: Exception) -> None:
    QMessageBox.warning(parent, t("common.error"), error_text(e) if isinstance(e, ApiError) else str(e))


def make_table(headers: list[str]) -> QTableWidget:
    tbl = QTableWidget(0, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tbl.setWordWrap(True)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    tbl.horizontalHeader().setStretchLastSection(True)
    tbl.verticalHeader().setVisible(False)
    tbl.setAlternatingRowColors(True)
    return tbl


def fill_table(tbl: QTableWidget, rows: list[list], data: list | None = None) -> None:
    tbl.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            item = QTableWidgetItem("" if v is None else str(v))
            if data is not None and c == 0:
                item.setData(Qt.ItemDataRole.UserRole, data[r])
            tbl.setItem(r, c, item)
    tbl.resizeColumnsToContents()
    for c in range(tbl.columnCount()):
        if tbl.columnWidth(c) > 360:
            tbl.setColumnWidth(c, 360)
    tbl.resizeRowsToContents()


def short_dt(iso: str | None) -> str:
    return (iso or "")[:16].replace("T", " ") or "—"


# ---------------------------------------------------------------- dialogs
class LoginDialog(QDialog):
    def __init__(self, client: ApiClient, cfg: DesktopConfig, needs_setup: bool):
        super().__init__()
        self.client, self.cfg, self.needs_setup = client, cfg, needs_setup
        self.setWindowTitle(t("app.name"))
        self.setWindowIcon(icon())
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        title = QLabel(t("auth.setup_title") if needs_setup else t("auth.title"))
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)
        lay.addWidget(QLabel(f"{t('app.tagline')}\n{client.base_url}"))
        form = QFormLayout()
        self.full_name = QLineEdit()
        self.username = QLineEdit(cfg.last_username)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        if needs_setup:
            form.addRow(t("auth.full_name"), self.full_name)
        form.addRow(t("auth.username"), self.username)
        form.addRow(t("auth.password"), self.password)
        lay.addLayout(form)
        if needs_setup:
            lay.addWidget(QLabel(t("auth.password_hint")))
        self.err = QLabel()
        self.err.setStyleSheet("color:#b42335")
        self.err.setWordWrap(True)
        lay.addWidget(self.err)
        lay.addWidget(QLabel(t("auth.legal")))
        btns = QDialogButtonBox()
        self.ok = btns.addButton(t("auth.create_admin") if needs_setup else t("auth.login"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setObjectName("primary")
        btns.addButton(t("common.cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.submit)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def submit(self) -> None:
        try:
            if self.needs_setup:
                self.client.setup(self.username.text().strip(), self.password.text(), self.full_name.text().strip())
            self.client.login(self.username.text().strip(), self.password.text())
        except ApiError as e:
            self.err.setText(error_text(e))
            return
        self.cfg.last_username = self.username.text().strip()
        self.cfg.save()
        self.accept()


# ---------------------------------------------------------------- pages
class Page(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.api = win.api
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(18, 14, 18, 14)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def heading(self, text: str) -> QLabel:
        h = QLabel(text)
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        h.setFont(f)
        h.setStyleSheet("color:#1f3a5f")
        self.lay.addWidget(h)
        return h

    def refresh(self) -> None:  # override
        pass


class DashboardPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.heading(t("dash.title"))
        grid = QGridLayout()
        self.stats: dict[str, QLabel] = {}
        for i, k in enumerate(["investigations", "data_points", "contacts", "posts", "media", "sources"]):
            box = QGroupBox()
            bl = QVBoxLayout(box)
            v = QLabel("0")
            v.setObjectName("statValue")
            bl.addWidget(v)
            bl.addWidget(QLabel(t(f"dash.{k}")))
            self.stats[k] = v
            grid.addWidget(box, i // 3, i % 3)
        self.lay.addLayout(grid)
        self.status = QLabel()
        self.lay.addWidget(self.status)
        g = QGroupBox(t("dash.recent"))
        gl = QVBoxLayout(g)
        self.table = make_table([t("inv.reference"), t("inv.target"), t("inv.status"), t("inv.created")])
        self.table.cellDoubleClicked.connect(lambda r, _c: self.win.open_investigation(self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)))
        gl.addWidget(self.table)
        self.lay.addWidget(g)

    def refresh(self):
        d = self.api.get("/api/dashboard")
        for k, lbl in self.stats.items():
            lbl.setText(str(d["totals"].get(k, 0)))
        self.status.setText("   ".join(f"{enum('status', s)}: {n}" for s, n in d["by_status"].items()))
        items = d["recent"]
        fill_table(self.table, [[i["reference"], i["title"] or i["target_input"], enum("status", i["status"]), short_dt(i["created_at"])] for i in items], [i["id"] for i in items])


class NewInvestigationPage(Page):
    TYPES = ["auto", "profile_url", "page_url", "username", "numeric_id", "authorized_account"]
    OPTS = ["collect_posts", "collect_photos", "collect_comments", "download_media", "follow_official_website"]

    def __init__(self, win):
        super().__init__(win)
        self.heading(t("new.title"))
        info = QLabel(t("new.policy"))
        info.setObjectName("info")
        info.setWordWrap(True)
        self.lay.addWidget(info)
        form = QFormLayout()
        self.target = QLineEdit()
        self.target.setPlaceholderText(t("new.target_placeholder"))
        self.target.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ttype = QComboBox()
        for x in self.TYPES:
            self.ttype.addItem(t(f"new.type.{x}"), x)
        self.title = QLineEdit()
        self.purpose = QPlainTextEdit()
        self.purpose.setFixedHeight(60)
        self.legal = QLineEdit()
        self.urls = QPlainTextEdit()
        self.urls.setFixedHeight(70)
        self.urls.setPlaceholderText("https://example.com/contact")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(50)
        form.addRow(t("new.target"), self.target)
        form.addRow(t("new.target_type"), self.ttype)
        form.addRow(t("new.title_field"), self.title)
        form.addRow(t("new.purpose"), self.purpose)
        form.addRow(t("new.legal_basis"), self.legal)
        form.addRow(t("new.extra_urls"), self.urls)
        form.addRow(t("new.notes"), self.notes)
        self.lay.addLayout(form)
        g = QGroupBox(t("new.options"))
        gl = QVBoxLayout(g)
        self.checks = {}
        for o in self.OPTS:
            cb = QCheckBox(t(f"new.opt.{o}"))
            cb.setChecked(o != "collect_comments")
            gl.addWidget(cb)
            self.checks[o] = cb
        self.max_posts = QSpinBox()
        self.max_posts.setRange(0, 1000)
        self.max_posts.setValue(100)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("new.opt.max_posts")))
        row.addWidget(self.max_posts)
        row.addStretch()
        gl.addLayout(row)
        self.lay.addWidget(g)
        btn = QPushButton(t("new.start"))
        btn.setObjectName("primary")
        btn.clicked.connect(self.submit)
        self.lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeading)
        self.lay.addStretch()

    def submit(self):
        tt = self.ttype.currentData()
        body = {
            "target": "me" if tt == "authorized_account" else self.target.text().strip(), "target_type": tt,
            "title": self.title.text().strip(), "purpose": self.purpose.toPlainText().strip(), "legal_basis": self.legal.text().strip(),
            "notes": self.notes.toPlainText().strip(), "extra_urls": [u for u in self.urls.toPlainText().split() if u.strip()],
            "options": {**{o: cb.isChecked() for o, cb in self.checks.items()}, "max_posts": self.max_posts.value()},
        }
        try:
            inv = self.api.post("/api/investigations", body)
        except ApiError as e:
            show_error(self, e)
            return
        for w in (self.target, self.title, self.legal):
            w.clear()
        for w in (self.purpose, self.urls, self.notes):
            w.clear()
        self.win.open_investigation(inv["id"])


class InvestigationPage(Page):
    """Profile / Contacts / Posts / Media / Sources for the current investigation."""

    def __init__(self, win, section: str):
        super().__init__(win)
        self.section = section
        self.title_lbl = self.heading(t(f"nav.{section}"))
        self.header = QLabel()
        self.header.setWordWrap(True)
        self.header.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lay.addWidget(self.header)
        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        self.lay.addWidget(self.banner)
        bar = QHBoxLayout()
        self.rerun = QPushButton(t("inv.rerun"))
        self.rerun.clicked.connect(self.do_rerun)
        bar.addWidget(self.rerun)
        bar.addStretch()
        self.lay.addLayout(bar)
        self.body = QVBoxLayout()
        self.lay.addLayout(self.body)
        self.build()

    def build(self):
        s = self.section
        if s in ("profile", "contacts"):
            self.table = make_table([t("dp.field"), t("dp.value"), t("dp.source"), t("dp.collected"), t("dp.availability"), t("dp.verification"), t("dp.confidence"), t("dp.classification")])
            self.body.addWidget(self.table)
            if s == "contacts":
                note = QLabel(t("contacts.note"))
                note.setObjectName("info")
                note.setWordWrap(True)
                self.body.insertWidget(0, note)
        elif s == "posts":
            bar = QHBoxLayout()
            self.q = QLineEdit()
            self.q.setPlaceholderText(t("posts.search"))
            self.order = QComboBox()
            self.order.addItem(t("posts.order_desc"), "desc")
            self.order.addItem(t("posts.order_asc"), "asc")
            go = QPushButton(t("common.search"))
            go.clicked.connect(self.refresh)
            self.q.returnPressed.connect(self.refresh)
            for w in (self.q, self.order, go):
                bar.addWidget(w)
            self.body.addLayout(bar)
            self.timeline = QLabel()
            self.body.addWidget(self.timeline)
            self.table = make_table([t("dp.collected"), t("posts.kind"), t("dp.value"), t("posts.permalink"), t("posts.shared_link")])
            self.body.addWidget(self.table)
        elif s == "media":
            note = QLabel(t("media.policy"))
            note.setObjectName("info")
            note.setWordWrap(True)
            self.body.addWidget(note)
            up = QPushButton(t("media.upload"))
            up.clicked.connect(self.upload)
            self.body.addWidget(up, alignment=Qt.AlignmentFlag.AlignLeading)
            self.table = make_table(["", t("posts.kind"), t("dp.source"), t("media.duplicate_group"), "pHash", "SHA-256", t("sources.status")])
            self.table.verticalHeader().setDefaultSectionSize(96)
            self.body.addWidget(self.table)
        elif s == "sources":
            self.summary = QLabel()
            self.body.addWidget(self.summary)
            self.table = make_table([t("sources.url"), t("sources.type"), t("sources.status"), t("sources.http"), t("sources.points"), t("sources.fetched"), t("sources.hash")])
            self.body.addWidget(self.table)
        self.table.setMinimumHeight(420)

    def inv_id(self):
        return self.win.current_id

    def do_rerun(self):
        try:
            self.api.post(f"/api/investigations/{self.inv_id()}/run")
        except ApiError as e:
            show_error(self, e)
        self.refresh()

    def refresh(self):
        iid = self.inv_id()
        if not iid:
            self.header.setText(t("common.select_investigation"))
            self.table.setRowCount(0)
            self.rerun.setEnabled(False)
            return
        inv = self.api.get(f"/api/investigations/{iid}")
        u = self.win.api.user
        can_edit = u.get("role") == "admin" or (u.get("role") == "investigator" and inv["created_by_id"] == u.get("id"))
        self.rerun.setEnabled(can_edit and inv["status"] not in ("running", "pending"))
        counts = " · ".join(f"{t('count.' + k)}: {v}" for k, v in inv["counts"].items())
        d = "rtl" if i18n.lang() == "ar" else "ltr"
        self.header.setAlignment(Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignTop)
        self.header.setText(f"<div dir='{d}'><b>{inv['reference']}</b> — {inv['title'] or inv['identifier']}<br>{inv['normalized_url']}<br>"
                            f"{t('inv.status')}: <b>{enum('status', inv['status'])}</b> · {enum('obj', inv['object_type'])}<br>{t('inv.purpose')}: {inv['purpose']}<br>{counts}</div>")
        if inv["limitations"]:
            self.banner.setText(t("inv.limitations") + ":\n" + "\n".join(f"• {x['code']}: {x['message']}" for x in inv["limitations"]))
            self.banner.show()
        else:
            self.banner.hide()
        if inv["status"] in ("running", "pending"):
            QTimer.singleShot(2000, self.refresh)
        getattr(self, f"load_{self.section}")(iid)

    def load_profile(self, iid, category=""):
        dps = self.api.get(f"/api/investigations/{iid}/datapoints", category=category)
        if self.section == "profile":
            dps = [d for d in dps if d["category"] != "contact"]
        else:
            dps = [d for d in dps if d["availability"] == "available"]
        fill_table(self.table, [[d["field"], d["value"], d["source_url"], short_dt(d["collected_at"]), enum("avail", d["availability"]), enum("ver", d["verification_status"]), enum("conf", d["confidence"]), enum("cls", d["classification"])] for d in dps])

    def load_contacts(self, iid):
        self.load_profile(iid, "contact")

    def load_posts(self, iid):
        r = self.api.get(f"/api/investigations/{iid}/posts", q=self.q.text().strip(), order=self.order.currentData(), limit=500)
        fill_table(self.table, [[short_dt(p["created_time"]), enum("posts", p["kind"]), p["message"], p["permalink"], p["shared_link"]] for p in r["items"]])
        tl = self.api.get(f"/api/investigations/{iid}/timeline")
        self.timeline.setText(t("posts.timeline") + ": " + "  ".join(f"{m['month']} ({m['count']})" for m in tl["months"]))

    def load_media(self, iid):
        items = self.api.get(f"/api/investigations/{iid}/media")
        fill_table(self.table, [["", m["kind"], m["source_url"], m["duplicate_group"] or "", m["phash"], m["sha256"][:16], m["status"]] for m in items])
        for r, m in enumerate(items):
            if m["status"] == "stored":
                try:
                    data, _ = self.api.download(f"/api/investigations/{iid}/media/{m['id']}/file")
                    pm = QPixmap()
                    pm.loadFromData(data)
                    lbl = QLabel()
                    lbl.setPixmap(pm.scaled(120, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    self.table.setCellWidget(r, 0, lbl)
                except ApiError:
                    pass
        self.table.setColumnWidth(0, 128)
        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, 96)

    def load_sources(self, iid):
        r = self.api.get(f"/api/investigations/{iid}/sources")
        self.summary.setText("  ".join(f"{enum('ver', k)}: {v}" for k, v in r["verification"].items()) + "   |   " + "  ".join(f"{enum('conf', k)}: {v}" for k, v in r["confidence"].items()))
        fill_table(self.table, [[s["url"], enum("src", s["source_type"]), enum("st", s["status"]), s["http_status"] or "", s["data_points"], short_dt(s["fetched_at"]), (s["content_sha256"] or "")[:16]] for s in r["items"]])

    def upload(self):
        if not self.inv_id():
            return
        path, _ = QFileDialog.getOpenFileName(self, t("media.upload"), "", "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                self.api._req("POST", f"/api/investigations/{self.inv_id()}/media/upload", files={"file": (Path(path).name, fh.read())})
        except ApiError as e:
            show_error(self, e)
        self.refresh()


class HistoryPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.heading(t("history.title"))
        bar = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText(t("history.search"))
        self.q.returnPressed.connect(self.refresh)
        go = QPushButton(t("common.search"))
        go.clicked.connect(self.refresh)
        self.delete_btn = QPushButton(t("common.delete"))
        self.delete_btn.clicked.connect(self.delete)
        for w in (self.q, go, self.delete_btn):
            bar.addWidget(w)
        self.lay.addLayout(bar)
        self.table = make_table([t("inv.reference"), t("inv.target"), t("inv.object_type"), t("inv.status"), t("inv.created_by"), t("inv.created")])
        self.table.setMinimumHeight(500)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.win.open_investigation(self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)))
        self.lay.addWidget(self.table)
        self.lay.addWidget(QLabel(t("common.open") + ": double-click"))

    def refresh(self):
        r = self.api.get("/api/investigations", q=self.q.text().strip(), page_size=200)
        items = r["items"]
        fill_table(self.table, [[i["reference"], i["target_input"], enum("obj", i["object_type"]), enum("status", i["status"]), i["created_by_username"], short_dt(i["created_at"])] for i in items], [i["id"] for i in items])

    def delete(self):
        row = self.table.currentRow()
        if row < 0:
            return
        iid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, t("common.delete"), t("common.confirm_delete")) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.api.delete(f"/api/investigations/{iid}")
        except ApiError as e:
            show_error(self, e)
        if self.win.current_id == iid:
            self.win.current_id = None
        self.refresh()


class ExportPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.heading(t("export.title"))
        note = QLabel(t("export.note"))
        note.setWordWrap(True)
        self.lay.addWidget(note)
        self.current = QLabel()
        self.lay.addWidget(self.current)
        row = QHBoxLayout()
        self.lang = QComboBox()
        self.lang.addItem("العربية", "ar")
        self.lang.addItem("English", "en")
        row.addWidget(QLabel(t("export.lang")))
        row.addWidget(self.lang)
        self.pdf = QPushButton("⇩ " + t("export.pdf"))
        self.xlsx = QPushButton("⇩ " + t("export.xlsx"))
        self.pdf.setObjectName("primary")
        self.xlsx.setObjectName("primary")
        self.pdf.clicked.connect(lambda: self.export("pdf"))
        self.xlsx.clicked.connect(lambda: self.export("xlsx"))
        row.addWidget(self.pdf)
        row.addWidget(self.xlsx)
        row.addStretch()
        self.lay.addLayout(row)
        g = QGroupBox(t("export.title") + " — offline")
        gl = QVBoxLayout(g)
        self.local = make_table([t("export.title"), "KB", t("dp.collected")])
        self.local.cellDoubleClicked.connect(self.open_local)
        gl.addWidget(self.local)
        self.lay.addWidget(g)
        self.last_saved: Path | None = None

    def refresh(self):
        iid = self.win.current_id
        self.current.setText(f"{t('nav.current')}: #{iid}" if iid else t("common.select_investigation"))
        self.pdf.setEnabled(bool(iid) and self.win.api is not None and self.win.online)
        self.xlsx.setEnabled(self.pdf.isEnabled())
        items = offline.list_reports(self.win.cfg.reports_dir)
        fill_table(self.local, [[r["name"], f"{r['size'] / 1024:.1f}", r["modified"]] for r in items], [r["path"] for r in items])

    def export(self, fmt: str, open_after: bool = True) -> Path | None:
        try:
            data, name = self.api.download(f"/api/investigations/{self.win.current_id}/report", format=fmt, lang=self.lang.currentData())
        except ApiError as e:
            show_error(self, e)
            return None
        path = offline.save_report(self.win.cfg.reports_dir, name, data)
        self.last_saved = path
        self.refresh()
        if open_after and not os.environ.get("FBO_DESKTOP_HEADLESS"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        return path

    def open_local(self, row, _col):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.local.item(row, 0).data(Qt.ItemDataRole.UserRole)))


class SettingsPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.heading(t("settings.title"))
        cfg = win.cfg
        g = QGroupBox(t("settings.system"))
        f = QFormLayout(g)
        self.mode = QComboBox()
        self.mode.addItem("Local (127.0.0.1)", "local")
        self.mode.addItem("Network (server)", "network")
        self.mode.setCurrentIndex(0 if cfg.mode == "local" else 1)
        self.server_url = QLineEdit(cfg.server_url)
        self.ca = QLineEdit(cfg.ca_bundle)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(cfg.local_port)
        self.lang = QComboBox()
        self.lang.addItem("العربية", "ar")
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(0 if cfg.language == "ar" else 1)
        self.reports_dir = QLineEdit(cfg.reports_dir)
        self.manifest = QLineEdit(cfg.update_manifest_url)
        f.addRow("Mode", self.mode)
        f.addRow("Server URL", self.server_url)
        f.addRow("CA certificate (.crt)", self.ca)
        f.addRow("Local port", self.port)
        f.addRow(t("settings.default_language"), self.lang)
        f.addRow("Reports folder", self.reports_dir)
        f.addRow("Update manifest URL", self.manifest)
        save = QPushButton(t("common.save"))
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        f.addRow(save)
        self.lay.addWidget(g)
        self.meta_box = QGroupBox(t("settings.meta"))
        mf = QFormLayout(self.meta_box)
        self.meta_status = QLabel()
        self.meta_status.setWordWrap(True)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_id = QLineEdit()
        self.app_secret = QLineEdit()
        self.app_secret.setEchoMode(QLineEdit.EchoMode.Password)
        mf.addRow(self.meta_status)
        mf.addRow(t("settings.app_id"), self.app_id)
        mf.addRow(t("settings.app_secret"), self.app_secret)
        mf.addRow(t("settings.access_token"), self.token)
        row = QHBoxLayout()
        ms = QPushButton(t("common.save"))
        ms.clicked.connect(self.save_meta)
        mt = QPushButton(t("settings.test"))
        mt.clicked.connect(self.test_meta)
        row.addWidget(ms)
        row.addWidget(mt)
        mf.addRow(row)
        self.lay.addWidget(self.meta_box)
        tools = QGroupBox(t("settings.backups"))
        tl = QHBoxLayout(tools)
        for text, fn in ((t("settings.backup_now"), self.backup), ("Web dashboard ↗", self.open_web), ("Check for updates", self.check_updates)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            tl.addWidget(b)
        tl.addStretch()
        self.lay.addWidget(tools)
        self.lay.addWidget(QLabel(f"{t('app.name')} Desktop {__version__}"))
        self.lay.addStretch()

    def refresh(self):
        if not self.win.online:
            self.meta_box.setEnabled(False)
            return
        s = self.api.get("/api/settings")
        m = s["meta"]
        self.app_id.setText(m["app_id"])
        self.meta_status.setText(f"{t('settings.access_token')}: {t('settings.configured') if m['access_token_set'] else t('settings.not_configured')} {m['access_token_masked']} · Graph {m['graph_version']}\n{t('settings.meta_note')}")
        self.meta_box.setEnabled(self.api.user.get("role") == "admin")

    def save(self):
        c = self.win.cfg
        c.mode, c.server_url, c.ca_bundle = self.mode.currentData(), self.server_url.text().strip(), self.ca.text().strip()
        c.local_port, c.language = self.port.value(), self.lang.currentData()
        c.reports_dir, c.update_manifest_url = self.reports_dir.text().strip(), self.manifest.text().strip()
        c.save()
        QMessageBox.information(self, t("common.saved"), t("common.saved") + " — restart the application to apply mode/language changes.")

    def save_meta(self):
        body = {"app_id": self.app_id.text().strip()}
        if self.app_secret.text():
            body["app_secret"] = self.app_secret.text()
        if self.token.text():
            body["access_token"] = self.token.text()
        try:
            self.api.put("/api/settings/meta", body)
        except ApiError as e:
            show_error(self, e)
            return
        self.token.clear()
        self.app_secret.clear()
        self.refresh()

    def test_meta(self):
        try:
            r = self.api.post("/api/settings/meta/test")
            QMessageBox.information(self, t("settings.test"), str(r.get("info") or r.get("error")))
        except ApiError as e:
            show_error(self, e)

    def backup(self):
        try:
            r = self.api.post("/api/admin/backups")
            QMessageBox.information(self, t("settings.backups"), r["name"])
        except ApiError as e:
            show_error(self, e)

    def open_web(self):
        QDesktopServices.openUrl(QUrl(self.win.cfg.base_url()))

    def check_updates(self):
        try:
            info = updates.check(self.win.cfg.update_manifest_url)
        except Exception as e:  # network/JSON errors
            QMessageBox.warning(self, "Update", str(e))
            return
        if info:
            if QMessageBox.question(self, "Update", f"Version {info['version']} is available. Download now?") == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(info["url"]))
        else:
            QMessageBox.information(self, "Update", f"{__version__} is up to date (or no manifest URL configured).")


# ---------------------------------------------------------------- main window
NAV = ["dashboard", "new", "profile", "contacts", "posts", "media", "sources", "history", "export", "settings"]


class MainWindow(QMainWindow):
    def __init__(self, api: ApiClient | None, cfg: DesktopConfig, online: bool = True):
        super().__init__()
        self.api = api
        self.cfg = cfg
        self.online = online
        self.current_id: int | None = None
        self.setWindowTitle(f"{t('app.name')} — {cfg.base_url()}" + ("" if online else " (offline)"))
        self.setWindowIcon(icon())
        self.resize(1320, 840)
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QVBoxLayout()
        side.setSpacing(0)
        brand = QLabel(f"🔍 {t('app.name')}")
        brand.setObjectName("brand")
        side.addWidget(brand)
        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setFixedWidth(250)
        for key in NAV:
            self.nav.addItem(QListWidgetItem(t(f"nav.{key}")))
        side.addWidget(self.nav)
        self.user_lbl = QLabel()
        self.user_lbl.setStyleSheet("background:#1f3a5f;color:#b5c3d4;padding:8px")
        side.addWidget(self.user_lbl)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(250)
        h.addWidget(sw)
        self.stack = QStackedWidget()
        h.addWidget(self.stack)
        self.setCentralWidget(central)
        self.pages: dict[str, Page] = {}
        if online:
            self.pages = {
                "dashboard": DashboardPage(self), "new": NewInvestigationPage(self),
                **{s: InvestigationPage(self, s) for s in ("profile", "contacts", "posts", "media", "sources")},
                "history": HistoryPage(self), "export": ExportPage(self), "settings": SettingsPage(self),
            }
            role = api.user.get("role") if api else ""
            self.user_lbl.setText(f"{api.user.get('username')} · {t('role.' + role)}" if api else "")
            if role == "viewer":
                self.nav.item(NAV.index("new")).setHidden(True)
        else:
            self.pages = {"export": ExportPage(self), "settings": SettingsPage(self)}
            for i, k in enumerate(NAV):
                self.nav.item(i).setHidden(k not in self.pages)
            self.user_lbl.setText("offline")
        for k in NAV:
            if k in self.pages:
                self.stack.addWidget(self.pages[k])
        self.nav.currentRowChanged.connect(self.on_nav)
        self.nav.setCurrentRow(0 if online else NAV.index("export"))

    def on_nav(self, row: int) -> None:
        key = NAV[row]
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        try:
            page.refresh()
        except ApiError as e:
            if e.status == 401:
                QMessageBox.warning(self, t("common.error"), t("err.session_invalid_or_expired"))
                self.close()
                return
            show_error(self, e)

    def open_investigation(self, inv_id: int) -> None:
        self.current_id = inv_id
        self.nav.setCurrentRow(NAV.index("profile"))
        self.on_nav(NAV.index("profile"))

    def navigate(self, key: str) -> Page:
        self.nav.setCurrentRow(NAV.index(key))
        return self.pages[key]


def apply_language(app, lang: str) -> None:
    i18n.set_lang(lang)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if lang == "ar" else Qt.LayoutDirection.LeftToRight)
    app.setStyleSheet(STYLE)
    f = app.font()
    f.setFamily("Segoe UI" if sys.platform.startswith("win") else f.family())
    f.setPointSize(10)
    app.setFont(f)
