# -*- mode: python ; coding: utf-8 -*-
"""
spec file cho PyInstaller — đóng gói app_desktop.py thành 1 file .exe

Build (từ thư mục gốc dự án):
    python -m PyInstaller QLVT-YTe.spec --clean
Output:
    dist/QLVT-YTe.exe

QUAN TRỌNG: spec này trỏ vào ../src (thư mục nguồn thật), KHÔNG dùng
bản copy trong build_desktop/ nữa — tránh build nhầm code cũ.
"""

block_cipher = None

SRC = 'src'

a = Analysis(
    [SRC + '/app_desktop.py'],
    pathex=[SRC],
    binaries=[],
    datas=[
        (SRC + '/schema.sql', '.'),   # app đọc schema khi tạo DB mới
        (SRC + '/neutral_theme.json', '.'),  # theme trung tính - preventing exe crash on startup
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'reportlab',
        'bcrypt',
        'qlvt_core',
        'tkcalendar',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='QLVT-YTe',
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
    # icon='assets/logo.ico',
)
