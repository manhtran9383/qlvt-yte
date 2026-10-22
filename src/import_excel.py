"""
Script import dữ liệu từ Excel VBA (Quan ly vat tu V13.xlsm) vào SQLite DB.
Chạy: python import_excel.py
"""
import os
import sys
import sqlite3
from datetime import datetime
from openpyxl import load_workbook

# Tìm file Excel mới nhất (V13 > V12 > V11...) — dùng glob để tránh lỗi encoding path
def find_excel_file():
    import glob
    base = "E:/1. Work/Old Work/KINDAKARE"
    files = glob.glob(base + "/**/*.xlsm", recursive=True)
    # Lọc bỏ file temp (~$)
    files = [f for f in files if not os.path.basename(f).startswith("~$")]
    if not files:
        return None
    # Sắp xếp: ưu tiên V13, rồi V12, rồi V11...
    def version_key(f):
        name = os.path.basename(f).lower()
        for v in range(20, 0, -1):
            if f"v{v}" in name:
                return v
        return 0
    files.sort(key=version_key, reverse=True)
    return files[0]

EXCEL_PATH = None  # Sẽ được set trong main()
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qlvt.db")

def norm(s):
    """Chuẩn hóa tên để so sánh."""
    if s is None:
        return ""
    return str(s).strip().lower().replace("  ", " ")

def to_float(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default

def excel_date(v):
    """Convert Excel date → ISO string."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def load_excel(path):
    """Load workbook, trả dict {sheet_name: [(row_tuple), ...]}."""
    wb = load_workbook(path, data_only=True, read_only=True)
    data = {}
    for name in wb.sheetnames:
        ws = wb[name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(tuple(row))
        data[name] = rows
    wb.close()
    return data

def find_col(header_row, keywords):
    """Tìm index cột theo từ khóa (không phân biệt hoa thường)."""
    if not header_row:
        return None
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        s = str(cell).strip().lower()
        for kw in keywords:
            if kw.lower() in s:
                return i
    return None

def import_products(ws_rows):
    """Sheet Product → dm_vattu. Header R2, data R3+.
    Cột: 0=Mã VT, 1=Tên VT, 2=Hãng SX, 3=Nước SX, 6=ĐVT, 10=Đơn giá."""
    rows = ws_rows
    if not rows:
        return 0
    count = 0
    for row in rows[2:]:
        if not row or not row[0]:
            continue
        ma = str(row[0]).strip()
        if not ma:
            continue
        ten = str(row[1]).strip() if row[1] else ""
        hang = str(row[2]).strip() if row[2] else ""
        nuoc = str(row[3]).strip() if row[3] else ""
        dvt = str(row[6]).strip() if len(row) > 6 and row[6] else ""
        gia = to_float(row[10] if len(row) > 10 else 0)
        yield (ma, ten, dvt, hang, nuoc, "", "", gia, 0)
        count += 1
    return count

def import_customers(ws_rows):
    """Sheet Customer → dm_khachhang. Header R2, data R3+.
    Cột: 0=Tên KH, 1=Mã KH, 2=Địa chỉ, 3=MST, 4=Khu vực."""
    rows = ws_rows
    if not rows:
        return 0
    count = 0
    for row in rows[2:]:
        if not row or not row[1]:
            continue
        ten = str(row[0]).strip() if row[0] else ""
        ma = str(row[1]).strip()
        if not ma:
            continue
        dc = str(row[2]).strip() if len(row) > 2 and row[2] else ""
        thue = str(row[3]).strip() if len(row) > 3 and row[3] else ""
        kv = str(row[4]).strip() if len(row) > 4 and row[4] else ""
        yield (ma, ten, dc, thue, kv)
        count += 1
    return count

def import_stock(ws_rows):
    """Sheet Stock → phieu_giaodich (NHAP). Header R2, data R3+.
    Cột: 0=Mã VT, 3=Tổng tồn, 9=Tối thiểu, 10=Đơn giá."""
    rows = ws_rows
    if not rows:
        return 0
    count = 0
    for row in rows[2:]:
        if not row or not row[0]:
            continue
        ma = str(row[0]).strip()
        sl = to_float(row[3] if len(row) > 3 else 0)
        gia = to_float(row[10] if len(row) > 10 else 0)
        toithieu = to_float(row[9] if len(row) > 9 else 0)
        if sl == 0:
            continue
        yield ("NHAP", "2026-01-01", ma, sl, gia, None, None, None, toithieu)
        count += 1
    return count

def import_sales(ws_rows):
    """Sheet Sale → phieu_giaodich (XUAT). Header R5, data R6+.
    Cột: 0=Thời điểm, 1=Mã VT, 4=Xuất, 5=Xuất ký gửi, 6=Doanh số, 7=KH, 8=Khoa, 9=Bác sĩ."""
    rows = ws_rows
    if not rows:
        return 0
    count = 0
    for row in rows[5:]:
        if not row or not row[1]:
            continue
        ma = str(row[1]).strip()
        sl = to_float(row[4] if len(row) > 4 else 0)
        sl_kygui = to_float(row[5] if len(row) > 5 else 0)
        gia = to_float(row[6] if len(row) > 6 else 0) / sl if sl > 0 else 0
        kh = str(row[7]).strip() if len(row) > 7 and row[7] else None
        khoa = str(row[8]).strip() if len(row) > 8 and row[8] else None
        nguoi = str(row[9]).strip() if len(row) > 9 and row[9] else None
        ngay = excel_date(row[0] if len(row) > 0 else None) or "2026-01-01"
        if sl_kygui > 0 and sl_kygui == sl:
            yield ("XUAT_KYGUI", ngay, ma, sl, gia, None, None, kh, khoa, nguoi, None)
        else:
            yield ("XUAT", ngay, ma, sl, gia, None, None, kh, khoa, nguoi, None)
        count += 1
    return count

def import_consignment(ws_rows):
    """Sheet Consignment → phieu_giaodich (KYGUI). Header R3, data R4+.
    Cột: 0=Thời gian, 1=Mã VT, 5=SL, 6=KH, 7=Khoa."""
    rows = ws_rows
    if not rows:
        return 0
    count = 0
    for row in rows[3:]:
        if not row or not row[1]:
            continue
        ma = str(row[1]).strip()
        sl = to_float(row[5] if len(row) > 5 else 0)
        if sl == 0:
            continue
        kh = str(row[6]).strip() if len(row) > 6 and row[6] else None
        khoa = str(row[7]).strip() if len(row) > 7 and row[7] else None
        ngay = excel_date(row[0] if len(row) > 0 else None) or "2026-01-01"
        yield ("KYGUI", ngay, ma, sl, 0, None, None, kh, khoa, None, None)
        count += 1
    return count

def import_contracts(ws_rows):
    """Sheet Contracts → hop_dong. Header R3, data R4+.
    Cột: 0=KH, 1=Số HĐ, 4=Ngày ký, 9=Mã VT."""
    rows = ws_rows
    if not rows:
        return 0
    count = 0
    for row in rows[3:]:
        if not row or not row[1]:
            continue
        kh = str(row[0]).strip() if row[0] else None
        hd = str(row[1]).strip()
        ngay = excel_date(row[4] if len(row) > 4 else None)
        ma = str(row[9]).strip() if len(row) > 9 and row[9] else None
        if not kh or not hd or not ma:
            continue
        yield (hd, kh, ma, 0, 0, ngay)
        count += 1
    return count

def main():
    excel_path = find_excel_file()
    if not excel_path:
        print("ERROR: Không tìm thấy file Excel nào!")
        sys.exit(1)
    print(f"Đọc Excel: {excel_path}")
    if not os.path.exists(excel_path):
        print("ERROR: File Excel không tồn tại!")
        sys.exit(1)
    
    data = load_excel(excel_path)
    print(f"Sheets: {list(data.keys())}")
    
    # Kết nối DB
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Tạo schema nếu chưa có
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        conn.executescript(f.read())
    
    # Build tên KH → ma_kh mapping
    ten_to_ma = {}
    for row in conn.execute("SELECT ma_kh, ten_kh FROM dm_khachhang"):
        ten_to_ma[norm(row[1])] = row[0]
    print(f"Khách hàng có sẵn: {len(ten_to_ma)}")
    
    # Import products
    ws = data.get("Product", [])
    n = 0
    for r in import_products(ws):
        conn.execute("INSERT OR REPLACE INTO dm_vattu VALUES (?,?,?,?,?,?,?,?,?)", r)
        n += 1
    print(f"  Product → dm_vattu: {n} dòng")
    
    # Import customers
    ws = data.get("Customer", [])
    n = 0
    for r in import_customers(ws):
        conn.execute("INSERT OR REPLACE INTO dm_khachhang VALUES (?,?,?,?,?)", r)
        n += 1
    print(f"  Customer → dm_khachhang: {n} dòng")
    
    # Rebuild mapping sau khi import KH mới
    for row in conn.execute("SELECT ma_kh, ten_kh FROM dm_khachhang"):
        ten_to_ma[norm(row[1])] = row[0]
    
    # Import stock (NHAP)
    ws = data.get("Stock", [])
    n = 0
    for loai, ngay, ma, sl, gia, lo, hsd, kh, toithieu in import_stock(ws):
        conn.execute("UPDATE dm_vattu SET ton_toi_thieu=? WHERE ma_vt=?", (toithieu, ma))
        so_phieu = f"IMP-{n+1:04d}"
        conn.execute(
            "INSERT OR REPLACE INTO phieu_giaodich (so_phieu,loai_phieu,ngay_phieu,ma_vt,so_lo,han_su_dung,so_luong,don_gia,ma_kh,ngay_lap) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (so_phieu, loai, ngay, ma, lo, hsd, sl, gia, None, datetime.now().strftime("%Y-%m-%d"))
        )
        n += 1
    print(f"  Stock → phieu_giaodich (NHAP): {n} dòng")

    # Import sales (XUAT)
    ws = data.get("Sale", [])
    n = 0
    auto_kh = 0
    for loai, ngay, ma, sl, gia, lo, hsd, kh, khoa, nguoi, hd in import_sales(ws):
        ma_kh = ten_to_ma.get(norm(kh)) if kh else None
        if kh and not ma_kh:
            # Tự động tạo KH mới nếu chưa có
            ma_kh = f"NEW{auto_kh+1:03d}"
            conn.execute("INSERT OR IGNORE INTO dm_khachhang (ma_kh,ten_kh) VALUES (?,?)",
                         (ma_kh, str(kh).strip()))
            ten_to_ma[norm(kh)] = ma_kh
            auto_kh += 1
        so_phieu = f"SAL-{n+1:04d}"
        try:
            conn.execute(
                "INSERT OR REPLACE INTO phieu_giaodich (so_phieu,loai_phieu,ngay_phieu,ma_vt,so_lo,han_su_dung,so_luong,don_gia,ma_kh,khoa_nhan,nguoi_goi,so_hop_dong,ngay_lap) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (so_phieu, loai, ngay, ma, lo, hsd, sl, gia, ma_kh, khoa, nguoi, hd, datetime.now().strftime("%Y-%m-%d"))
            )
            n += 1
        except sqlite3.IntegrityError:
            pass
    print(f"  Sale → phieu_giaodich (XUAT): {n} dòng (tự tạo {auto_kh} KH mới)")

    # Import consignment
    ws = data.get("Consignment", [])
    n = 0
    for loai, ngay, ma, sl, gia, lo, hsd, kh, khoa, nguoi, hd in import_consignment(ws):
        ma_kh = ten_to_ma.get(norm(kh)) if kh else None
        if kh and not ma_kh:
            continue
        so_phieu = f"CS-{n+1:04d}"
        conn.execute(
            "INSERT OR REPLACE INTO phieu_giaodich (so_phieu,loai_phieu,ngay_phieu,ma_vt,so_lo,han_su_dung,so_luong,don_gia,ma_kh,khoa_nhan,nguoi_goi,so_hop_dong,ngay_lap) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (so_phieu, loai, ngay, ma, lo, hsd, sl, gia, ma_kh, khoa, nguoi, hd, datetime.now().strftime("%Y-%m-%d"))
        )
        n += 1
    print(f"  Consignment → phieu_giaodich: {n} dòng")
    
    # Import contracts
    ws = data.get("Contracts", [])
    n = 0
    for hd, kh, ma, sl, gia, ngay in import_contracts(ws):
        ma_kh = ten_to_ma.get(norm(kh)) if kh else None
        if not ma_kh:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO hop_dong (so_hd,ma_kh,ma_vt,so_luong,don_gia,ngay_ky) VALUES (?,?,?,?,?,?)",
            (hd, ma_kh, ma, sl, gia, ngay)
        )
        n += 1
    print(f"  Contracts → hop_dong: {n} dòng")
    
    conn.commit()
    
    # Thống kê
    print("\n=== THỐNG KÊ SAU IMPORT ===")
    for table in ("dm_vattu", "dm_khachhang", "phieu_giaodich", "hop_dong"):
        c = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {c} dòng")
    
    conn.close()
    print(f"\nDB lưu tại: {DB_PATH}")
    print("Hoàn thành!")

if __name__ == "__main__":
    main()
