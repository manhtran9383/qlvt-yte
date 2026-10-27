# Hướng dẫn tích hợp — `app_desktop.py` bản viết lại (V3)

File: `app_v3/src/app_desktop.py` (3.371 dòng) — thay thế trực tiếp `src/app_desktop.py` trong repo.
Test đi kèm: `app_v3/src/test_v3_fixes.py` (33 test regression cho các bug đã sửa).

---

## 1. Bằng chứng nghiệm thu (đã chạy thật trên Linux + Xvfb, 27/10/2026)

| Gate | Lệnh | Kết quả |
|---|---|---|
| Test GUI **của chính repo** (không sửa một chữ nào) | `xvfb-run -a python3 test_desktop.py` | **33/33 PASS** |
| Test core của repo (core không bị sửa) | `python3 test_core.py` | **45/45 PASS** |
| Regression test mới cho các bug đã sửa | `xvfb-run -a python3 -m pytest test_v3_fixes.py -q` | **33/33 passed** |
| Lint | `ruff check app_desktop.py --select F,E7,E9,B,E501,W6` | **All checks passed** |
| Smoke test sâu (không mock UI) | `App()` thật → đăng nhập `admin/admin123` → render **cả 11 màn hình** → tạo user mới qua UI | **OK toàn bộ** (4 màn `kygui/hoadontruoc/lichsu/users` mà test repo chưa từng chạm tới đều render được) |

## 2. Bug đã sửa (đối chiếu review V1/V2)

| # | Bug | Cách sửa | Test chứng minh |
|---|---|---|---|
| 1 | Exe crash lúc khởi động vì `load_theme` không có fallback | `_load_theme()` try/except, thử `_MEIPASS` rồi thư mục cạnh exe, fallback theme mặc định + ghi log cảnh báo | smoke `App()` |
| 2 | Exe mất dữ liệu (DB trong `_MEIPASS`) | `DB_PATH = core.DB_PATH` — dùng `core._db_dir()` đã viết sẵn (cạnh exe, fallback `%LOCALAPPDATA%`) | `test_db_path_dung` |
| 3 | 2 nút PDF `TypeError` (GUI gọi 3/5 tham số, core nhận 2/4) | GUI **tự render PDF** (`pdf_bien_ban`, `pdf_baocao`) — không phụ thuộc chữ ký core; kiến trúc đúng hơn (PDF là tầng trình bày) | `test_pdf_bien_ban_unicode`, `test_pdf_baocao` |
| 4 | PDF tiếng Việt vỡ glyph (Helvetica/WinAnsi) | `pdf_fonts()` đăng ký TTF Unicode: Arial/Segoe/Times (Windows), DejaVu (Linux), fallback Helvetica | `test_pdf_bien_ban_unicode` (assert font == "Uni") |
| 5 | Biên bản THIẾU HÀNG khi giỏ >1 mặt (chỉ in phiếu cuối) | `_lap_bien_ban` thu thập **mọi** số phiếu đã ghi; `_bien_ban_data` gộp đủ mặt hàng; preview + PDF in đủ, liệt kê đủ số phiếu | `test_bien_ban_nhieu_mat` |
| 6 | Màn Lịch sử KH `IndexError` (`r["loai"]`, `r["ngay"]` không tồn tại) | Đọc đúng `r["loai_phieu"]`, `r["ngay_phieu"]` + map nhãn loại phiếu | `test_lichsu_hien_ket_qua` |
| 7 | `to_float` phá số (`147000.00`→×100, `1.5`→×10, `15.000`→÷1000) | Bản parse tất định: đuôi 1-2 số = thập phân, đuôi đúng 3 số + nhóm chuẩn = hàng nghìn, hỗn hợp theo dấu cuối, **mơ hồ → raise ValueError**; mọi call-site bắt lỗi và báo đỏ | 14 case đúng + 9 case phải raise |
| 8 | Âm thầm đổi input sai thành 1/0 (SL, giá, ngày) | `parse_so_luong` (>0, raise), `ngay_hop_le` (YYYY-MM-DD, raise) — báo lỗi đỏ, KHÔNG ghi, KHÔNG sửa giỏ | `test_add_cart_chan_sl_sai`, `test_add_cart_chan_gia_mo_ho`, `test_lap_bien_ban_chan_ngay_sai` |
| 9 | Check "giao vượt hóa đơn" cộng gộp xuyên mặt hàng | Ô **"Số hóa đơn"** mới trên màn Bán hàng + `_kiem_tra_giao_hoadon` check đúng `(so_hoa_don, ma_vt)` qua view, gộp SL các dòng cùng mặt, **pre-check trước khi ghi bất kỳ phiếu nào** | `test_giao_theo_hoadon_truoc` (3 kịch bản: mặt lạ → chặn; trong hạn → ghi; vượt → chặn) |
| 10 | `_luu_nhap`/`_lap_bien_ban` lỗi giữa chừng → giỏ không nhất quán, lưu lại = trùng | Pre-validate toàn bộ; ghi đến đâu gỡ khỏi giỏ đến đó; lỗi → thông báo rõ "đã ghi được: PX-…", phần chưa ghi ở lại | smoke nhập kho trong test repo |
| 11 | Đổi ngôn ngữ chỉ rebuild màn home (sidebar nửa nạc nửa mỡ) | `_doi_ngon_ngu` rebuild **toàn bộ** UI + giữ màn hiện tại; `SCREEN_INFO` dịch lazy; ngôn ngữ **lưu `settings.json` cạnh DB** (khởi động lại vẫn nhớ) | `test_doi_ngon_ngu_rebuild` |
| 12 | `_save_kh`/`_luu_hop_dong`/`_sua_toi_thieu` gọi thẳng `scr_x()` → **nhân đôi cả màn hình** mỗi lần lưu | `_reload_screen()` = clear `main` rồi render lại một lần | smoke cust/contract |
| 13 | Log ghi vào thư mục cài Python (`dirname(sys.executable)`) | Log cạnh DB (thư mục đã đảm bảo ghi được); `__main__` có try/except + hộp thoại lỗi + exit 1 | smoke |
| 14 | Code chết: `_token`/`xoa_session` (không phiên nào tồn tại), `SCREEN_INFO` class-attr, `import tkinter` lặp trong hàm | Đã gỡ; docstring module ghi rõ lý do | — |
| 15 | Chữ ✕ trong giỏ xuất chỉ để trang trí (không xóa được dòng) | Nút xóa dòng thật `_xoa_dong_cart` | — |

**Cộng thêm (không đổi hành vi cũ):** ô VAT % trên màn Bán hàng (mặc định 8, sửa được — hết hardcode `0.08` ở tầng GUI); ô Ngày cho phiếu ký gửi; bảng "Quyền theo vai trò" hiển thị trên màn Tài khoản; cache danh sách khách hàng theo màn hình (hết cảnh query full bảng mỗi lần gõ phím); progress bar hợp đồng không còn đè lên chữ %.

## 3. Tương thích — những gì được GIỮ NGUYÊN có chủ đích

- Toàn bộ tên widget/hàm mà `test_desktop.py` của repo truy cập (`v_kh, v_ma, v_sl, v_gia, v_tong, v_hd, v_ngay, n_ma, n_gia, n_sl, n_hsd, n_lo, n_msg, r_tab, r_nam, r_box, ls_*, kg_*, hd_*, cart, cart_nhap, _build, show, _add_cart, _on_ma_typed, _lap_bien_ban, _luu_nhap, _draw_report…`) → **test cũ chạy không sửa một chữ nào, 33/33**.
- Chuỗi hiển thị mà test assert (`"Đã lưu"`, `"Tổng: … ₫"`, KPI labels, `"Ổn định"/"Cần nhập"`…) giữ nguyên văn → i18n `_EN` sẵn có vẫn khớp key.
- Hành vi nghiệp vụ gây tranh cãi giữ nguyên để không phá test repo: **cảnh báo** (không chặn) khi xuất vượt tồn — việc CHẶN thuộc về `core.ghi_phieu` (xem mục 4).
- Không sửa `qlvt_core.py`, `schema.sql`, `i18n.py` — file này drop-in độc lập.

## 4. Những thứ file này KHÔNG tự sửa được (việc còn lại, theo thứ tự ưu tiên)

1. **`QLVT-YTe.spec`**: thêm `(SRC + '/neutral_theme.json', '.')` vào `datas`. GUI giờ không crash nếu thiếu (đã fallback) nhưng exe sẽ chạy theme xanh mặc định thay vì theme trung tính.
2. **`qlvt_core.ghi_phieu`**: chặn tồn kho âm (`XUAT` mà `ton < sl` → raise, trừ khi có cờ cho phép ghi rõ) và `CHECK (so_luong > 0)` cho mọi loại phiếu trong schema — GUI chỉ là lớp cảnh báo, core mới là chốt chặn cuối.
3. **`test_desktop.py:202`**: sau khi core chặn âm kho, đổi assertion `ton == -25` thành "mong `ValueError`/mong bị chặn".
4. **`qlvt_core.xoa_khachhang`**: thêm `con.commit()` (GUI hiện không gọi hàm này — màn KH không có nút xóa, như bản gốc).
5. **`qlvt_core.ghi_phieu` + `xuat_hoadon_truoc`**: sửa check hóa đơn theo `(so_hoa_don, ma_vt)` ngay trong core (GUI đã chặn đúng cho luồng của mình, nhưng bản web/CLI gọi thẳng core vẫn hở).
6. **`qlvt_core.xuat_pdf`/`xuat_baocao_pdf`**: GUI không dùng nữa → xóa, hoặc sửa chữ ký + font Unicode nếu muốn giữ cho CLI.
7. **`i18n.py`**: regenerate key (các key chứa `\\n` literal không bao giờ khớp); cân nhắc chuyển sang file JSON + khóa ổn định.
8. **Repo**: thêm `requirements.txt` (customtkinter, reportlab, bcrypt, tkcalendar, openpyxl, pyinstaller — pin version), CI GitHub Actions chạy đúng 3 lệnh ở mục 1 + build exe + smoke-run exe.

## 5. Chạy kiểm chứng (mọi máy có Python 3.11+)

```bash
pip install customtkinter reportlab bcrypt tkcalendar openpyxl pytest ruff
cd src
# Windows:
python test_desktop.py            # 33/33
python test_core.py               # 45/45
python -m pytest test_v3_fixes.py -q   # 33 passed
ruff check app_desktop.py --select F,E7,E9,B,E501,W6
# Linux headless: thêm xvfb-run -a trước mỗi lệnh GUI
```

---

# PHẦN 2 — PATCH `qlvt_core.py` + SPEC + CI (27/10, đã chạy kiểm chứng)

## 2.1. `qlvt_core.py` — 14 thay đổi, mỗi thay đổi có test kèm

| # | Thay đổi | Test chứng minh (`test_core_v3_fixes.py`) |
|---|---|---|
| 1 | `ghi_phieu` mặc định **CHẶN xuất vượt tồn kho** (ValueError); tham số mới `cho_am_kho=False` chỉ bật khi người dùng đã xác nhận tường minh trên UI | `test_chan_xuat_vuot_ton`, `test_cho_am_kho_explicit` |
| 2 | **Chặn `so_luong <= 0` mọi loại phiếu** (bug V1: XUAT −500 được nhận và tồn kho TĂNG ngược) | `test_chan_so_luong_khong_duong`, `test_xuat_am_khong_lam_tang_ton` |
| 3 | Check "giao vượt hóa đơn" sửa đúng granularity **`(so_hoa_don, ma_vt)`** ở cả `ghi_phieu` lẫn `xuat_hoadon_truoc` (bug V1: giao B trên hóa đơn của A vẫn lọt) | `test_hoadon_truoc_dung_mat_hang` |
| 4 | `xoa_khachhang` **thêm `commit()`** (bug V1: xóa không có tác dụng) | `test_xoa_khachhang_commit` |
| 5 | `backup_db` dùng **sqlite3 backup API** thay `shutil.copy2` file sống; xóa dòng chết `src = getattr(con,"execute",None) and None` | `test_backup_db_mở_được_và_đủ_dữ_liệu` (+ integrity_check) |
| 6 | `bien_ban(con, so_phieu=None, **vat_pct=8.0**)` — thuế suất hết hardcode, dict trả về có thêm `vat_pct` | `test_bien_ban_vat_pct` |
| 7 | `xuat_pdf` viết lại: tham số `so_phieu` (hết cảnh luôn in phiếu cuối), `vat_pct`, `lang`; **font Unicode** qua `dang_ky_font_pdf()`; nhãn thuế động | `test_xuat_pdf_theo_phieu_unicode` |
| 8 | `xuat_baocao_pdf` thêm `lang` (không rò rỉ trạng thái ngôn ngữ global — có `finally` khôi phục) | `test_xuat_baocao_pdf_3_loai`, `test_lang_param_khong_lam_ro_lang_global` |
| 9 | `dang_ky_font_pdf()` **public** — GUI delegate về đây, một nguồn sự thật cho font PDF | (GUI test `test_pdf_bien_ban_unicode` assert font "Uni") |
| 10 | `next_so_phieu`: `XUAT_HOADON_TRUOC` có prefix riêng **`XH-`** (hết cảnh dùng chung dãy số với PX) | `test_prefix_xuat_hoadon_truoc` |
| 11 | `luu_hop_dong`: validate (SL>0, KH/VT tồn tại, số hợp lệ) + ghi **audit log** + tham số `nguoi_thao_tac` | `test_luu_hop_dong_validate` |
| 12 | `ton_kho()`: `gia_tri_ton` = tồn × **giá danh mục** — nhất quán 1-1 với view `v_tonkho` (bug V1: nhân `MAX(don_gia)` của cả lịch sử giao dịch gồm giá bán → KPI thổi phồng) | `test_ton_kho_nhat_quan_voi_view` |
| 13 | `authenticate`: nâng cấp hash **cả pbkdf2 → bcrypt** (bản cũ không bao giờ nâng cấp pbkdf2) | (hành vi phụ thuộc bcrypt có sẵn; không phá test cũ) |
| 14 | Docstring sai được sửa thật: bỏ chữ Hán "按月", `ds_khachhang`/`ds_phieu` mô tả đúng `sqlite3.Row`, `tien_do_hop_dong` hết tuyên bố "phần trăm"; typo "hóa độn" → "hóa đơn"; alias **`phan_quyen`** (tên đúng chính tả, `phan_quyyen` giữ vì tương thích) | `test_phan_quyen_alias` |

**Quyết định có chủ đích (ghi rõ, không sửa ngầm):**
- Schema KHÔNG đổi (`CHECK so_luong <> 0` giữ nguyên) — SQLite không sửa được CHECK tanpa rebuild bảng; enforcement chuyển lên core, an toàn cho DB cũ. Việc thêm `CHECK so_luong > 0` khi rebuild schema để lại như một migration riêng.
- `sessions`/token HMAC/`with_lock` giữ nguyên (dead code cho bản desktop nhưng được tuyên bố dành cho bản web) — quyết định xóa hay làm bản web là của chủ repo, review chỉ nêu.
- `verify_password` vẫn nhận legacy `sha256$` (đường upgrade DB cũ) — nhưng đã có lộ trình tự nâng cấp lên bcrypt khi đăng nhập (mục 13).

## 2.2. `app_desktop.py` — 4 điểm đồng bộ với core mới

1. `_add_cart`: người dùng bấm "Vẫn tiếp tục" khi vượt tồn → item mang cờ `cho_am_kho=True`.
2. `_lap_bien_ban`: truyền cờ xuống `core.ghi_phieu` (mặc định vẫn là CHẶN).
3. `pdf_fonts()` delegate về `core.dang_ky_font_pdf()` (một nguồn sự thật).
4. `_luu_hop_dong` truyền `nguoi_thao_tac` (audit log hết trống tên).

## 2.3. `QLVT-YTe.spec`

- `datas` **+ `neutral_theme.json`** (nguyên nhân exe cũ chết lúc khởi động).
- **`upx=False`** (UPX hay bị antivirus nhận diện nhầm — tối kỵ khi đưa vào bệnh viện).
- `hiddenimports` + `i18n`, `babel` (tkcalendar cần).
- Comment ghi rõ: DB KHÔNG bao giờ nằm trong `_MEIPASS`.

## 2.4. `requirements.txt` / `requirements-dev.txt`

Pin đúng bộ đã kiểm chứng: customtkinter 6.0.0, reportlab 5.0.1, bcrypt 5.0.0, tkcalendar 1.6.1, openpyxl 3.1.5 (+ pytest/ruff/pyinstaller cho dev).

## 2.5. `.github/workflows/ci.yml`

Matrix **ubuntu + windows**; mỗi push/PR chạy: ruff → `test_core.py` (45) → pytest core-fixes (19) → `test_desktop.py` (33, Xvfb trên Linux) → pytest gui-fixes (33) → **build PyInstaller** → **SMOKE-RUN BINARY 2 LẦN**: kiểm `app.log` có `MAIN START`, không `FATAL ERROR`, `qlvt.db` nằm cạnh exe và bền qua lần chạy thứ 2. Từ nay chữ "Tests PASS" trong commit message phải là CI xanh thật.

## 2.6. Bằng chứng build + smoke (chạy thật trong sandbox, 27/10)

```
$ python3 -m PyInstaller QLVT-YTe.spec --clean --noconfirm
Build complete! dist/QLVT-YTe (34 MB)

$ xvfb-run -a timeout 25 ./dist/QLVT-YTe      # lần 1
app.log: [08:09:37] === MAIN START ===        # không FATAL, không cảnh báo theme
qlvt.db: 4 KB cạnh exe — users: [('admin','admin')] — đủ 9 bảng + sessions

$ xvfb-run -a timeout 15 ./dist/QLVT-YTe      # lần 2
app.log: 2 × MAIN START; qlvt.db: 106 KB      # DB BỀN qua 2 lần chạy
SMOKE OK: exe khởi động, theme nạp được, DB cạnh exe, bền, không FATAL
```

(Đây chính là kịch bản giết bản đóng gói cũ: exe cũ crash lúc khởi động vì thiếu theme trong datas, và kể cả sống thì DB trong `_MEIPASS` sẽ mất sạch khi thoát.)

## 2.7. Cổng nghiệm thu cuối của toàn bộ Phần 2

| Gate | Kết quả |
|---|---|
| `python3 test_core.py` (repo, không sửa) | **45/45 PASS** |
| `xvfb-run -a python3 test_desktop.py` (repo, không sửa) | **33/33 PASS** |
| `pytest test_core_v3_fixes.py` (mới) | **19/19 passed** |
| `pytest test_v3_fixes.py` (GUI, mới) | **33/33 passed** |
| `ruff check qlvt_core.py app_desktop.py test_*v3*.py --select F,E7,E9,B,W6` | **All checks passed** |
| Build PyInstaller + smoke-run 2 lần | **OK** (log ở mục 2.6) |

## 2.8. Việc còn lại (không thuộc phạm vi được yêu cầu)

1. `i18n.py`: regenerate key (các key chứa `\\n` literal không bao giờ khớp — 1 dialog khôi phục vẫn ra tiếng Việt ở chế độ EN).
2. `README.md`: sửa các claim sai (bản Web không tồn tại, "6 bảng" → 9, `pip install tk`, "chữ ký số", hướng dẫn `.iss` — file `.iss` vẫn bị `.gitignore` loại trừ: hoặc bỏ ignore, hoặc bỏ mục đó).
3. 3 script `import_*`: xóa đường dẫn cá nhân (`C:\Users\manht`, `E:/1. Work/Old Work/KINDAKARE`), chuyển vào `scripts/` + argparse + xác nhận trước khi DELETE.
4. Quyết định số phận `sessions`/token (xóa hoặc làm bản web thật).
5. Migration schema riêng nếu muốn `CHECK so_luong > 0` ở tầng DB.
