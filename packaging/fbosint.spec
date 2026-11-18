# PyInstaller spec: builds FBOSINT.exe (desktop, windowed) and FBOSINT-Server.exe
# (backend + web dashboard, console) into one folder: dist/FBOSINT/
# Run from the repository root:  pyinstaller packaging/fbosint.spec --noconfirm
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.getcwd())
ICON = os.path.join(ROOT, "assets", "fbosint.ico")
pathex = [os.path.join(ROOT, "backend"), os.path.join(ROOT, "desktop")]
datas = [
    (os.path.join(ROOT, "shared", "i18n"), os.path.join("shared", "i18n")),
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "backend", "fbosint", "assets"), os.path.join("fbosint", "assets")),
    (os.path.join(ROOT, "frontend", "dist"), os.path.join("fbosint", "static")),
]
datas += collect_data_files("reportlab")
hidden = collect_submodules("fbosint") + collect_submodules("uvicorn") + ["arabic_reshaper", "bidi.algorithm", "multipart", "python_multipart"]
excludes = ["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick3D", "PySide6.QtMultimedia"]

desk = Analysis([os.path.join(ROOT, "desktop", "run_desktop.py")], pathex=pathex, datas=datas, hiddenimports=hidden, excludes=excludes)
srv = Analysis([os.path.join(ROOT, "packaging", "server_entry.py")], pathex=pathex, datas=datas, hiddenimports=hidden, excludes=excludes + ["PySide6", "shiboken6"])

desk_exe = EXE(PYZ(desk.pure), desk.scripts, [], exclude_binaries=True, name="FBOSINT", icon=ICON, console=False, version=None)
srv_exe = EXE(PYZ(srv.pure), srv.scripts, [], exclude_binaries=True, name="FBOSINT-Server", icon=ICON, console=True)

coll = COLLECT(desk_exe, desk.binaries, desk.datas, srv_exe, srv.binaries, srv.datas, name="FBOSINT")
