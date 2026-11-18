# PyInstaller spec – builds dist/Tahqiq/ (one-folder, windowed).
# Run from the repository root:  pyinstaller desktop/tahqiq.spec --noconfirm
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend_dist"),
    (str(BACKEND / "migrations"), "migrations"),
    (str(BACKEND / "app" / "assets"), "app/assets"),
]
hidden = collect_submodules("app") + collect_submodules("uvicorn") + [
    "sqlalchemy.dialects.sqlite",
    "alembic.runtime.migration",
    "alembic.ddl.sqlite",
    "alembic.ddl.postgresql",
]

a = Analysis(
    [str(ROOT / "desktop" / "tahqiq_desktop.py")],
    pathex=[str(BACKEND)],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "playwright", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtQuick3D"],
    noarchive=False,
)
# Drop Qt modules the app never loads (widgets + WebEngine only) to shrink the bundle.
_UNUSED = ("Qt63D", "Qt6Charts", "Qt6DataVisualization", "Qt6Graphs", "Qt6Location", "Qt6Multimedia",
           "Qt6Quick3D", "Qt6SpatialAudio", "Qt6Sensors", "Qt6Bluetooth", "Qt6Nfc", "Qt6SerialPort",
           "Qt6Scxml", "Qt6StateMachine", "Qt6TextToSpeech", "Qt6RemoteObjects", "Qt6VirtualKeyboard",
           "Qt6Designer", "Qt6Help", "Qt6Test", "Qt6Labs", "qml/Qt3D", "qml/QtCharts",
           "qml/QtMultimedia", "qml/QtQuick3D", "qml/QtLocation", "qml/QtDataVisualization", "qml/QtGraphs",
           "__never__")
_KEEP_LOCALES = ("ar.pak", "en-US.pak")


def _keep(entry) -> bool:
    name = entry[0].replace("\\", "/")
    if "qtwebengine_locales/" in name:
        return name.endswith(_KEEP_LOCALES)
    return not any(u in name for u in _UNUSED)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]
pyz = PYZ(a.pure)
icon = ROOT / "desktop" / "tahqiq.ico"
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Tahqiq",
    console=False,
    icon=str(icon) if icon.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Tahqiq")
