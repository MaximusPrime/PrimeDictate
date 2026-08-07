# -*- mode: python ; coding: utf-8 -*-

import os
from build import write_version_file

version_file = os.path.abspath(os.path.join('build', 'PrimeDictate-Portable.version.txt'))
os.makedirs(os.path.dirname(version_file), exist_ok=True)
write_version_file(version_file, 'PrimeDictate-Portable.exe')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('PrimeDictate-Logo.png', '.'),
        ('assets/maximus-prime-software.png', 'assets'),
        ('assets/PrimeDictate-AppIcon.png', 'assets'),
        ('runtime', 'runtime'),
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
    icon=['PrimeDictate-Logo.ico'],
    version=version_file,
)
