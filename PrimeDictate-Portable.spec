# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

version_file = os.environ.get("PRIMEDICTATE_VERSION_FILE")
faster_whisper_datas = collect_data_files('faster_whisper')


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('PrimeDictate-Logo.png', '.'), ('assets\\maximus-prime-software.png', 'assets'), ('assets\\PrimeDictate-AppIcon.png', 'assets'), ('src\\locales', 'src\\locales'), ('runtime', 'runtime')] + faster_whisper_datas,
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
    name='PrimeDictate-Portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_file,
    icon=['PrimeDictate-Logo.ico'],
    uac_admin=False,
    uac_uiaccess=False,
)
