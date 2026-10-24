# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

用法（仓库根目录）：
    python -m PyInstaller build/mijia_desktop.spec --noconfirm --clean
产物：
    dist/MijiaConsole/MijiaConsole.exe
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - SPECPATH 由 PyInstaller 注入

APP_NAME = "MijiaConsole"

# 明显用不到、体积又大的 Qt 模块，排除后包体约减半
QT_EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
]

PY_EXCLUDES = ["tkinter", "matplotlib", "numpy", "pandas", "scipy", "IPython", "pytest"]

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "app", "resources"), "resources"),
        (os.path.join(ROOT, "LICENSE"), "."),
    ],
    hiddenimports=[
        "mijiaAPI",
        "mijiaAPI.apis",
        "mijiaAPI.devices",
        "mijiaAPI.miutils",
        "mijiaAPI.errors",
        "mijiaAPI.logger",
        "mijiaAPI.version",
        "Crypto.Cipher.ARC4",
        "qrcode",
        "qrcode.image.pil",
        "PIL.Image",
        "tzlocal",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=QT_EXCLUDES + PY_EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "app", "resources", "app.ico"),
    version=os.path.join(ROOT, "build", "version_info.txt"),
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
