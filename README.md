# QLVT Y Tế

**Phần mềm Quản lý Vật tư Y tế** — phiên bản 1.1  
**Công nghệ:** Python + CustomTkinter + SQLite (không cần server, không cài Python)

---

## 1. Giới thiệu

QLVT Y tế là phần mềm quản lý vật tư y tế toàn diện cho bệnh viện, phòng khám, nhà thuốc.
Thay thế Excel truyền thống với giao diện desktop hiện đại, bảo mật qua phân quyền
5 vai trò: `admin`, `kinhdoanh`, `ketoan`, `kho`, `nhanvien`.

### 4 Giao diện, 1 bộ nghiệp vụ
| Giao diện | Mô tả |
|---|---|
| **Desktop** | `src/app_desktop.py` — ứng dụng GUI CustomTkinter |
| **Web** | Django/FastAPI + frontend — web app tương thích đầy đủ quyền |
| **CLI** | `import_excel.py` — quản lý từ terminal |
| **Import Excel** | Dựng sẵn giao diện nhập dữ liệu |

---

## 2. Cấu trúc dự án

```
QLVT-YTe/
├── QLVT-YTe.spec          # PyInstaller build spec
├── .gitignore
├── README.md
└── src/
    ├── app_desktop.py     # Giao diện desktop (CustomTkinter)
    ├── qlvt_core.py       # Nền tảng nghiệp vụ + bảo mật
    ├── schema.sql         # Schema SQLite (6 bảng + 7 view, không dữ liệu mẫu)
    ├── test_core.py       # Unit tests
    ├── test_desktop.py    # GUI headless tests
    ├── import_excel.py    # CLI import từ Excel
    ├── import_v8adj.py    # Import file Excel V8-ADJ
    ├── import_desktop.py  # GUI import từ Excel
    └── __pycache__/       # (không versioned)
```

---

## 3. Yêu cầu hệ thống

- **Hệ điều hành:** Windows 10/11 (64-bit)
- **RAM:** ≥ 2 GB
- **Ổ cứng:** ≥ 100 MB trống
- **Python:** 3.11+ (nếu chạy từ source)
- Không cần Internet, không cần MySQL (SQLite đã có sẵn)

---

## 4. Cài đặt & Khởi động

### Từ source
```bash
cd src
pip install customtkinter reportlab bcrypt
python app_desktop.py
```

### Biên dịch thành .exe
```bash
pip install pyinstaller
python -m PyInstaller QLVT-YTe.spec --clean
# Output: dist/QLVT-YTe.exe
```

### Cài đặt bằng Inno Setup
```bash
# Cần Inno Setup 6+
ISCC QLVT-YTe.iss
# Output: dist/QLVT-YTe-Setup.exe
```

---

## 5. Dữ liệu cơ sở

- **Database:** `qlvt.db` (SQLite, tạo tự động nếu chưa có)
- **Schema:** `src/schema.sql` — 6 bảng + 7 view
- **Vị trí mặc định:** cùng thư mục với executable (`dist/qlvt.db` trong bản `.exe`)
- **Admin mặc định:** `admin` / `admin123` — **bắt buộc đổi mật khẩu** lần đầu
- **Dữ liệu có sẵn:** khi cài đặt từ Inno Setup, một DB mẫu sẽ được copy từ
  `build_desktop/qlvt.db`. Để xóa toàn bộ dữ liệu, xóa file `qlvt.db` và khởi động lại.

> ✅ *Bản repository này đã xóa toàn bộ dữ liệu sản phẩm / khách hàng / doanh số.*
> Chỉ còn schema + account `admin` (được tự tạo lại khi khởi động lần đầu).

---

## 6. Tính năng chính

| Tính năng | Mô tả |
|---|---|
| **Bán hàng (POS)** | Tạo phiếu xuất, giá tự động theo hợp đồng |
| **Nhập kho** | Phiếu nhập vật tư từ nhà cung cấp |
| **Tồn kho** | Realtime, cảnh báo hết hạn, nhóm hạn sử dụng |
| **Khách hàng** | Quản lý bệnh viện, phòng khám, nhà thuốc |
| **Hợp đồng thầu** | Theo dõi tiến độ giao hàng từng hợp đồng |
| **Ký gửi** | Gửi hàng bệnh viện giữ, xuất ký gửi khi bán |
| **Hóa đơn trước** | Xuất HĐ trước, giao hàng sau, chặn giao vượt HĐ |
| **Lịch sử khách hàng** | Tra cứu giao dịch theo KH + khoảng thời gian |
| **Công việc** | Task list theo khoa và bác sĩ |
| **Báo cáo** | Doanh thu tháng/quý, thị phần, tồn kho, biểu đồ thực |
| **Biên bản giao hàng** | In PDF có chữ ký số (Desktop) |
| **Đăng nhập & phân quyền** | 5 vai trò, chặn truy cập không đủ quyền |

---

## 7. Xử lý sự cố

| Lỗi | Fix |
|---|---|
| `ModuleNotFoundError: tkinter` | Cài: `pip install tk` |
| `ModuleNotFoundError: customtkinter` | `pip install customtkinter` |
| `database is locked` | Tắt các cửa sổ khác, xóa `*.db-wal` |
| Login thất bại | Đổi lại mật khẩu: `admin` → `doi_mat_khau` → `admin123` |
| File `.exe` không chạy | Cài `Microsoft Visual C++ Redistributable` |

---

## 8. Liên hệ

**Tổng hợp:**
- GitHub: `manhtran9383/qlvt-yte`
- Email: `manhtran9383@gmail.com`

**Mô tả & video demo:**
- **Tên:** QLVT Y tế
- **Phát triển bởi:** AI + phần mềm open-source
- **License:** MIT
