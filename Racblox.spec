# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("app_icon.png", "."),
        ("Palette.png", "."),
        ("Endesga 32 Palette color palette.txt", "."),
        ("library", "library"),
        ("models", "models"),
        ("tool_icon", "tool_icon"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Racblox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["app_icon.png"],
)
