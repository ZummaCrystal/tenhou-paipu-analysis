# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:/coding/dsh_workspace/simple/tenhou-paipu-analysis/server.py'],
    pathex=[],
    binaries=[('D:/coding/anaconda3/envs/py314_null/Library/bin/libssl-3-x64.dll', '.'), ('D:/coding/anaconda3/envs/py314_null/Library/bin/libcrypto-3-x64.dll', '.'), ('D:/Program Files/nodejs/node.exe', 'node')],
    datas=[('D:/coding/dsh_workspace/simple/tenhou-paipu-analysis/web', 'web'), ('D:/coding/dsh_workspace/simple/tenhou-paipu-analysis/media', 'media'), ('D:/coding/dsh_workspace/simple/tenhou-paipu-analysis/mjscore/node_harness.js', 'mjscore')],
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
    [],
    exclude_binaries=True,
    name='tenhou-paipu-analysis-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='tenhou-paipu-analysis-server',
)
