"""Import từ file Excel trên Desktop (bản mới nhất) vào qlvt.db."""
import os, sys, sqlite3, glob
from datetime import datetime
from openpyxl import load_workbook

EXCEL = r"C:\Users\manht\Desktop\Quan ly vat tu V13.xlsm"
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qlvt.db")

def norm(s):
    return "" if s is None else str(s).strip().lower()

def to_float(v, d=0):
    try: return float(v)
    except: return d

def xdate(v):
    if v is None: return None
    if isinstance(v, datetime): return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    for f in ("%Y-%m-%d","%d/%m/%Y","%m/%d/%Y"):
        try: return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except: pass
    return None

print(f"Đọc: {EXCEL}")
wb = load_workbook(EXCEL, data_only=True, read_only=True)
print(f"Sheets: {wb.sheetnames}")

conn = sqlite3.connect(DB)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=OFF")  # Tắt FK trong lúc import để xóa thoải mái

# Xóa dữ liệu cũ (giữ users)
conn.execute("DELETE FROM phieu_giaodich")
conn.execute("DELETE FROM hop_dong")
conn.execute("DELETE FROM dm_khachhang")
conn.execute("DELETE FROM dm_vattu")
conn.commit()

# --- Product: header R2, data R3+ ---
ws = wb["Product"]
n = 0
for row in list(ws.iter_rows(values_only=True))[2:]:
    if not row or not row[0]: continue
    ma = str(row[0]).strip()
    conn.execute("INSERT OR REPLACE INTO dm_vattu VALUES (?,?,?,?,?,?,?,?,?)",
        (ma, str(row[1] or "").strip(), str(row[6] or "").strip() if len(row)>6 else "",
         str(row[2] or "").strip(), str(row[3] or "").strip(), "", "",
         to_float(row[10] if len(row)>10 else 0), 0))
    n += 1
print(f"Product: {n}")

# --- Customer: header R2, data R3+ ---
ws = wb["Customer"]
n = 0
for row in list(ws.iter_rows(values_only=True))[2:]:
    if not row or not row[1]: continue
    conn.execute("INSERT OR REPLACE INTO dm_khachhang VALUES (?,?,?,?,?)",
        (str(row[1]).strip(), str(row[0] or "").strip(),
         str(row[2] or "").strip() if len(row)>2 else "",
         str(row[3] or "").strip() if len(row)>3 else "",
         str(row[4] or "").strip() if len(row)>4 else ""))
    n += 1
print(f"Customer: {n}")

ten_to_ma = {norm(r[1]): r[0] for r in conn.execute("SELECT ma_kh,ten_kh FROM dm_khachhang")}

# --- Stock → NHAP (tồn kho hiện tại) ---
ws = wb["Stock"]
n = 0
for row in list(ws.iter_rows(values_only=True))[2:]:
    if not row or not row[0]: continue
    ma = str(row[0]).strip()
    sl = to_float(row[3] if len(row)>3 else 0)
    if sl == 0: continue
    conn.execute("INSERT INTO phieu_giaodich (so_phieu,loai_phieu,ngay_phieu,ma_vt,so_luong,don_gia,ngay_lap) VALUES (?,?,?,?,?,?,?)",
        (f"IMP-{n+1:04d}", "NHAP", "2026-01-01", ma, sl,
         to_float(row[10] if len(row)>10 else 0), datetime.now().strftime("%Y-%m-%d")))
    conn.execute("UPDATE dm_vattu SET ton_toi_thieu=? WHERE ma_vt=?",
        (to_float(row[9] if len(row)>9 else 0), ma))
    n += 1
print(f"Stock (NHAP): {n}")

# --- Sale → XUAT ---
ws = wb["Sale"]
n = 0
for row in list(ws.iter_rows(values_only=True))[5:]:
    if not row or not row[1]: continue
    ma = str(row[1]).strip()
    sl = to_float(row[4] if len(row)>4 else 0)
    if sl == 0: continue
    kh = str(row[7]).strip() if len(row)>7 and row[7] else None
    ma_kh = ten_to_ma.get(norm(kh)) if kh else None
    gia = to_float(row[6] if len(row)>6 else 0) / sl if sl > 0 else 0
    ngay = xdate(row[0] if len(row)>0 else None) or "2026-01-01"
    try:
        conn.execute("INSERT INTO phieu_giaodich (so_phieu,loai_phieu,ngay_phieu,ma_vt,so_luong,don_gia,ma_kh,khoa_nhan,nguoi_goi,ngay_lap) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"SAL-{n+1:04d}", "XUAT", ngay, ma, sl, gia, ma_kh,
             str(row[8] or "").strip() if len(row)>8 else None,
             str(row[9] or "").strip() if len(row)>9 else None,
             datetime.now().strftime("%Y-%m-%d")))
        n += 1
    except sqlite3.IntegrityError:
        pass
print(f"Sale (XUAT): {n}")

# --- Consignment → KYGUI ---
ws = wb["Consignment"]
n = 0
for row in list(ws.iter_rows(values_only=True))[3:]:
    if not row or not row[1]: continue
    ma = str(row[1]).strip()
    sl = to_float(row[5] if len(row)>5 else 0)
    if sl == 0: continue
    kh = str(row[6]).strip() if len(row)>6 and row[6] else None
    ma_kh = ten_to_ma.get(norm(kh)) if kh else None
    ngay = xdate(row[0] if len(row)>0 else None) or "2026-01-01"
    try:
        conn.execute("INSERT INTO phieu_giaodich (so_phieu,loai_phieu,ngay_phieu,ma_vt,so_luong,don_gia,ma_kh,ngay_lap) VALUES (?,?,?,?,?,?,?,?)",
            (f"CS-{n+1:04d}", "KYGUI", ngay, ma, sl, 0, ma_kh, datetime.now().strftime("%Y-%m-%d")))
        n += 1
    except sqlite3.IntegrityError:
        pass
print(f"Consignment: {n}")

# --- Contracts ---
ws = wb["Contracts"]
n = 0
for row in list(ws.iter_rows(values_only=True))[3:]:
    if not row or not row[1]: continue
    kh = str(row[0]).strip() if row[0] else None
    hd = str(row[1]).strip()
    ma = str(row[9]).strip() if len(row)>9 and row[9] else None
    if not kh or not hd or not ma: continue
    ma_kh = ten_to_ma.get(norm(kh))
    if not ma_kh: continue
    conn.execute("INSERT OR REPLACE INTO hop_dong (so_hd,ma_kh,ma_vt,so_luong,don_gia,ngay_ky) VALUES (?,?,?,?,?,?)",
        (hd, ma_kh, ma, 0, 0, xdate(row[4] if len(row)>4 else None)))
    n += 1
print(f"Contracts: {n}")

conn.commit()
print("\n=== THỐNG KÊ ===")
for t in ("dm_vattu","dm_khachhang","phieu_giaodich","hop_dong"):
    print(f"  {t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
ton = conn.execute("SELECT SUM(so_luong) FROM phieu_giaodich WHERE loai_phieu='NHAP'").fetchone()[0] or 0
xuat = conn.execute("SELECT SUM(so_luong) FROM phieu_giaodich WHERE loai_phieu='XUAT'").fetchone()[0] or 0
print(f"  Tổng nhập: {ton} | Tổng xuất: {xuat} | Tồn: {ton-xuat}")
conn.close()
wb.close()
print("Hoàn thành!")
