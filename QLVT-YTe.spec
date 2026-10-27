# -*- mode: python ; coding: utf-8 -*-
"""
spec file cho PyInstaller — đóng gói src/app_desktop.py thành 1 file .exe

Build (từ thư mục gốc dự án):
    python -m PyInstaller QLVT-YTe.spec --clean
Output:
    dist/QLVT-YTe.exe

SỬA (V3):
  - datas BẮT BUỘC có neutral_theme.json: app_desktop nạp theme ở cấp module;
    bản cũ thiếu file này -> exe onefile FileNotFoundError ngay khi khởi động
    (chết im lặng vì console=False). GUI nay có fallback nên không crash nữa,
    nhưng thiếu datas thì mất theme trung tính.
  - upx=False: UPX nén binary hay bị antivirus nhận diện nhầm (false
    positive) — tối kỵ khi phân phối vào bệnh viện. Đổi cũ: upx=True.
  - hiddenimports thêm 'i18n' (module cục bộ) và 'babel' (tkcalendar cần).
  - DB KHÔNG nằm trong datas: core._db_dir() đặt qlvt.db cạnh .exe khi chạy
    (fallback %LOCALAPPDATA% nếu không ghi được). Tuyệt đối không trỏ DB vào
    sys._MEIPASS — thư mục tạm bị xoá khi thoát -> mất dữ liệu.
"""

block_cipher = None

SRC = 'src'

a = Analysis(
    [SRC + '/app_desktop.py'],
    pathex=[SRC],
    binaries=[],
    datas=[
        (SRC + '/schema.sql', '.'),           # app đọc schema khi tạo DB mới
        (SRC + '/neutral_theme.json', '.'),   # theme trung tính (V3: bắt buộc)
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'reportlab',
        'bcrypt',
        'qlvt_core',
        'i18n',
        'tkcalendar',
        'babel',
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
    upx=False,             # V3: tránh antivirus false-positive
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
