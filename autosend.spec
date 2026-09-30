# PyInstaller build recipe for AutoSend.  Run:  build.ps1
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("neonize")
datas += [("assets/icon.ico", "assets"), ("assets/icon.png", "assets"), ("assets/fonts", "assets/fonts")]
hiddenimports += ["segno", "openpyxl", "PIL"]

EXCLUDES = [
    "tkinter", "unittest", "pytest", "test",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtWebSockets",
    "PySide6.QtWebView", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtNetworkAuth",
    "PySide6.QtHttpServer", "PySide6.QtSpatialAudio", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "PySide6.QtPrintSupport", "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtDBus",
    "numpy.tests", "matplotlib",
]

a = Analysis(
    ["run_autosend.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AutoSend",
    console=False,
    icon="assets/icon.ico",
    version="version_info.txt",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AutoSend", upx=False)
