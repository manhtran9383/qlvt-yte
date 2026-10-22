"""
qlvt_core.py — Lõi nghiệp vụ của phần mềm QLVT Y tế (bản Desktop)

Đây là file DUY NHẤT chứa logic nghiệp vụ. app_desktop.py import file này
→ giao diện và nghiệp vụ không bao giờ lệch nhau.

Chứa:
  - Kết nối SQLite (WAL, timeout, lock) cho phép nhiều tiến trình cùng truy cập
  - Các thao tác nhập/xuất/ký gửi (ghi sổ giao dịch)
  - Tra cứu giá theo bệnh viện (bảng giá)
  - Sinh số biên bản giao hàng
  - Tồn kho + cảnh báo (query, không lưu trữ)
  - Báo cáo tháng/quý/thị phần
  - Đọc số tiền bằng chữ tiếng Việt (cho biên bản)
  - Đăng nhập, phiên, phân quyền tài khoản (users/sessions)
"""
import sqlite3
import os
import re
import sys
import time
import random
from datetime import datetime, date
from i18n import t, tf


def _resource_dir():
    """Thư mục chứa tài nguyên (schema.sql).

    Khi đóng gói bằng PyInstaller, schema.sql nằm trong sys._MEIPASS;
    khi chạy từ source thì nằm cạnh file này.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _db_dir():
    """Thư mục lưu CSDL — phải BỀN VỮNG.

    Trong bản .exe, thư mục này KHÔNG được nằm trong _MEIPASS (bị xoá khi
    thoát app → mất toàn bộ dữ liệu). Ưu tiên cạnh file .exe; nếu không ghi
    được (Program Files) thì rơi về %LOCALAPPDATA%/QLVT-YTe.
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        probe = os.path.join(base, ".qlvt_write_test")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return base
    except OSError:
        fallback = os.path.join(os.environ.get("LOCALAPPDATA", base), "QLVT-YTe")
        os.makedirs(fallback, exist_ok=True)
        return fallback


SCHEMA_FILE = os.path.join(_resource_dir(), "schema.sql")
# DB path override — test / nhiều instance khác nhau không dùng chung 1 file
DB_PATH = os.environ.get("QLVT_DB", os.path.join(_db_dir(), "qlvt.db"))

# ============================================================
# 1. KẾT NỐI
# ============================================================
import threading

# SQLite chỉ cho 1 tiến trình dùng 1 connection tại một thời điểm, và mặc định
# cấm dùng connection giữa các thread ("objects created in a thread can only be
# used in that same thread"). Desktop có nhiều thread (UI + tác vụ nền) →
# BẮT BUỘC tắt check_same_thread và bọc mọi thao tác bằng lock chung,
# nếu không thao tác đồng thời sẽ báo "database is locked".
_DB_LOCK = threading.RLock()


def connect(db_path=None, check_same_thread=False):
    """Mở kết nối SQLite. WAL cho phép đọc song song khi đang ghi.
    check_same_thread=False chỉ dùng khi có lock bảo vệ (xem with_lock).
    Mặc định đọc đường dẫn từ biến môi trường QLVT_DB (nếu set)."""
    if db_path is None:
        db_path = DB_PATH
    con = sqlite3.connect(db_path, timeout=10.0,
                           check_same_thread=check_same_thread)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")      # đọc/ghi song song
    con.execute("PRAGMA foreign_keys = ON")        # bắt lỗi khóa ngoại ngay
    con.execute("PRAGMA busy_timeout = 8000")      # chờ thay vì báo lỗi "locked"
    return con


def with_lock(con, fn, *a, **kw):
    """Chạy 1 hàm trên connection dưới lock toàn cục.
    Dùng cho mọi thao tác DB từ nhiều thread (UI + tác vụ nền)."""
    with _DB_LOCK:
        return fn(con, *a, **kw)


def init_db(con):
    """Tạo schema + seed dữ liệu mẫu (chỉ chạy lần đầu)."""
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()


def ensure_db(db_path=None):
    """Mở DB, tự tạo nếu chưa có. Trả về (connection, đã_tạo_mới)."""
    con = connect(db_path)
    # Kiểm tra cả dm_vattu lẫn users — schema có thể đã được cập nhật
    # thêm bảng mới sau khi DB đã tạo.
    is_new = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dm_vattu'"
    ).fetchone()[0] == 0
    need_migrate = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()[0] == 0
    if is_new or need_migrate:
        init_db(con)
    return con, is_new

# ============================================================
# 2. SINH SỐ CHỨNG TỪ
# ============================================================

def next_so_phieu(con, loai="PX", prefix=None):
    """Sinh số phiếu liên tục: PX-2026-0001.
    Dùng CAST(substr) để lấy phần số → hoạt động đúng khi vượt 9999.
    Gọi từ trong transaction của ghi_phieu để tránh race condition.
    """
    d = date.today()
    p = prefix or {"NHAP": "PN", "XUAT": "PX", "KYGUI": "KG",
                   "XUAT_KYGUI": "XK"}.get(loai, "PX")
    prefix_str = f"{p}-{d.year}-"
    # Trích xuất phần số sau prefix (4+ chữ số) → cast integer → MAX + 1
    row = con.execute(
        "SELECT MAX(CAST(substr(so_phieu, ?) AS INTEGER)) "
        "FROM phieu_giaodich WHERE so_phieu LIKE ?",
        (len(prefix_str) + 1, prefix_str + "%"),
    ).fetchone()
    n = (row[0] or 0) + 1
    return f"{prefix_str}{n:04d}"

# ============================================================
# 3. GHI SỔ GIAO DỊCH — nguồn duy nhất của mọi con số
# ============================================================

def ghi_phieu(con, loai_phieu, ngay_phieu, ma_vt, so_luong, don_gia,
              ma_kh=None, so_lo=None, han_su_dung=None, khoa_nhan=None,
              nguoi_goi=None, so_hop_dong=None, so_hoa_don=None,
              nguoi_lap="", ghi_chu=""):
    """Ghi 1 dòng phiếu. Trả về số phiếu đã ghi.

    loai_phieu: NHAP | XUAT | KYGUI | XUAT_KYGUI | XUAT_HOADON_TRUOC
    so_luong: dương cho NHAP/KYGUI, dương cho XUAT (view tự trừ dấu)
    """
    if so_luong is None or float(so_luong) == 0:
        raise ValueError(t("Số lượng phải khác 0"))
    if not ma_vt:
        raise ValueError(t("Thiếu mã vật tư"))
    if not con.execute("SELECT 1 FROM dm_vattu WHERE ma_vt=?", (ma_vt,)).fetchone():
        raise ValueError(tf("Mã vật tư '{}' không tồn tại trong danh mục", ma_vt))

    # Khi GIAO HÀNG (XUAT) kèm số hóa đơn: không được giao nhiều hơn đã xuất hóa đơn.
    # Check ở đây (không chỉ ở xuat_hoadon_truoc) vì người dùng có thể giao trước mà xuất HĐ sau.
    if loai_phieu == "XUAT" and so_hoa_don:
        da_xuat_hd = con.execute(
            "SELECT COALESCE(SUM(so_luong),0) FROM phieu_giaodich "
            "WHERE loai_phieu='XUAT_HOADON_TRUOC' AND so_hoa_don=?",
            (so_hoa_don,)).fetchone()[0] or 0
        da_giao = con.execute(
            "SELECT COALESCE(SUM(so_luong),0) FROM phieu_giaodich "
            "WHERE loai_phieu='XUAT' AND so_hoa_don=?",
            (so_hoa_don,)).fetchone()[0] or 0
        if da_giao + float(so_luong) > da_xuat_hd:
            raise ValueError(
                tf("Giao {} sẽ vượt số đã xuất hóa đơn {}", so_luong, so_hoa_don) + 
                f"(đã xuất HĐ {da_xuat_hd}, đã giao {da_giao})")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = """INSERT INTO phieu_giaodich
             (so_phieu, loai_phieu, ngay_phieu, ma_vt, so_lo, han_su_dung,
              so_luong, don_gia, ma_kh, khoa_nhan, nguoi_goi, so_hop_dong,
              so_hoa_don, nguoi_lap, ngay_lap, ghi_chu)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    # SQLite chỉ cho 1 writer tại một thời điểm. Khi nhiều tiến trình (hoặc
    # nhiều server dev) ghi cùng lúc → "database is locked". Retry với
    # backoff ngẫu nhiên thay vì để request 500 ngay lập tức.
    # QUAN TRỌNG: ghi_log() phải nằm NGOÀI vòng retry. Nếu gọi trong vòng,
    # mỗi lần lock sẽ cố ghi 1 dòng log → log cũng bị lock → retry tiếp vô tận.
    # Mỗi lần retry chờ busy_timeout ngắn (300ms) thay vì mặc định 8s — nếu
    # không, 6 lần retry sẽ tốn ~48s và request sẵn bị timeout.
    # Lưu busy_timeout gốc để khôi phục sau.
    orig_busy = 8000
    try:
        row_orig = con.execute("PRAGMA busy_timeout").fetchone()
        orig_busy = row_orig[0] if row_orig else 8000
    except Exception:
        pass
    last_err = None
    try:
        for attempt in range(6):
            # Sinh số phiếu MỖI lần retry (nếu trùng PK → sinh lại)
            so_phieu = next_so_phieu(con, loai_phieu)
            values = (so_phieu, loai_phieu, ngay_phieu, ma_vt, so_lo, han_su_dung,
                      float(so_luong), float(don_gia or 0), ma_kh, khoa_nhan, nguoi_goi,
                      so_hop_dong, so_hoa_don, nguoi_lap, now, ghi_chu)
            try:
                con.execute("PRAGMA busy_timeout = 300")
                con.execute(sql, values)
                con.commit()
                break
            except sqlite3.OperationalError as e:
                if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                    raise
                last_err = e
                time.sleep(0.05 * (attempt + 1) + random.random() * 0.05)
            except sqlite3.IntegrityError as e:
                # Trùng khóa chính (số phiếu trùng) → retry để sinh số mới
                last_err = e
                time.sleep(0.05 * (attempt + 1) + random.random() * 0.05)
        else:
            raise last_err
    finally:
        # Khôi phục busy_timeout gốc
        try:
            con.execute(f"PRAGMA busy_timeout = {orig_busy}")
        except Exception:
            pass
    ghi_log(con, nguoi_lap, loai_phieu, "phieu_giaodich",
            f"{so_phieu} | {ma_vt} x{so_luong} | KH={ma_kh or '-'}")
    return so_phieu


def ghi_log(con, nguoi, hanh_dong, doi_tuong, chi_tiet):
    """Ghi nhật ký thao tác. Không commit ở đây (để nằm trong transaction
    của thao tác gọi). Nếu bảng audit_log chưa tồn tại (DB cũ) thì bỏ qua —
    nhật ký không được làm hỏng giao dịch chính."""
    try:
        con.execute(
            "INSERT INTO audit_log (nguoi, hanh_dong, doi_tuong, chi_tiet) VALUES (?,?,?,?)",
            (nguoi, hanh_dong, doi_tuong, chi_tiet),
        )
    except sqlite3.OperationalError:
        pass

# ============================================================
# 4. GIÁ BÁN — ưu tiên giá theo bệnh viện, không có thì lấy giá kế hoạch
# ============================================================

def gia_ban(con, ma_vt, ma_kh):
    """Giá bán cho 1 mã VT tại 1 bệnh viện.
    Đúng logic sheet PrDetail: tra bảng giá riêng, fallback về giá kế hoạch."""
    if ma_kh:
        r = con.execute(
            "SELECT don_gia FROM bang_gia WHERE ma_vt=? AND ma_kh=?",
            (ma_vt, ma_kh),
        ).fetchone()
        if r and r["don_gia"]:
            return float(r["don_gia"]), "theo hợp đồng"
    r = con.execute("SELECT don_gia FROM dm_vattu WHERE ma_vt=?", (ma_vt,)).fetchone()
    return (float(r["don_gia"]) if r and r["don_gia"] else 0.0), "giá kế hoạch"

# ============================================================
# 5. TỒN KHO & CẢNH BÁO — thay hoàn toàn VBA TonKhoCty / TonKhoKyGui
# ============================================================

def ton_kho(con):
    """Toàn bộ tồn kho công ty (view)."""
    return con.execute(
        """SELECT v.ma_vt, v.ten_vt, v.dvt, v.ton_toi_thieu, v.don_gia,
                  COALESCE(t.ton_kho,0)      AS ton_kho,
                  COALESCE(t.gia_tri_ton,0)  AS gia_tri_ton
           FROM dm_vattu v
           LEFT JOIN (
               SELECT ma_vt,
                      SUM(CASE WHEN loai_phieu='NHAP' THEN so_luong ELSE -so_luong END) AS ton_kho,
                      SUM(CASE WHEN loai_phieu='NHAP' THEN so_luong ELSE -so_luong END) * MAX(don_gia) AS gia_tri_ton
               FROM phieu_giaodich WHERE loai_phieu IN ('NHAP','XUAT')
               GROUP BY ma_vt
           ) t ON t.ma_vt = v.ma_vt
           ORDER BY v.ten_vt"""
    ).fetchall()


def ton_kho_theo_han(con):
    """Tồn kho phân nhóm hạn sử dụng (thay sheet Stock với các cột >10th, 8-10th...)."""
    return con.execute("SELECT * FROM v_tonkho_hansudung").fetchall()


def canh_bao(con):
    """Danh sách cảnh báo cho dashboard: cần nhập thêm, sắp hết hạn, đã hết hạn."""
    return canh_bao_v2(con, ton_kho(con))


def canh_bao_v2(con, tk_data):
    """Danh sách cảnh báo — nhận ton_kho đã query để tránh scan 2 lần."""
    can_nhap, sap_het, het_han = [], [], []
    han = {r["ma_vt"]: r for r in ton_kho_theo_han(con)}
    for v in tk_data:
        tk_ = v["ton_kho"] or 0
        mn = v["ton_toi_thieu"] or 0
        if mn > 0 and tk_ < mn:
            can_nhap.append({"ma_vt": v["ma_vt"], "ten_vt": v["ten_vt"],
                             "ton": tk_, "toi_thieu": mn, "thieu": mn - tk_})
        h = han.get(v["ma_vt"])
        if h:
            if (h["het_han"] or 0) > 0:
                het_han.append({"ma_vt": v["ma_vt"], "ten_vt": v["ten_vt"],
                                "so_luong": h["het_han"]})
            if (h["nhom_duoi_3th"] or 0) > 0:
                sap_het.append({"ma_vt": v["ma_vt"], "ten_vt": v["ten_vt"],
                                "so_luong": h["nhom_duoi_3th"]})
    return {"can_nhap": can_nhap, "sap_het": sap_het, "het_han": het_han}

# ============================================================
# 6. BÁO CÁO — thay pivot + VBA BaoCaoThang/Quy/LocMshare
# ============================================================

def doanh_so_thang(con, nam=None):
    nam = nam or date.today().year
    return con.execute(
        """SELECT substr(ngay_phieu,6,2) AS thang,
                  SUM(so_luong)  AS so_luong,
                  SUM(thanh_tien) AS doanh_so
           FROM phieu_giaodich
           WHERE loai_phieu IN ('XUAT','XUAT_KYGUI')
             AND substr(ngay_phieu,1,4) = ?
           GROUP BY thang ORDER BY thang""",
        (str(nam),),
    ).fetchall()


def _thang_con(nam, thang):
    """(2026, 10) -> 2026*12 + 9 — đơn vị tháng tuyệt đối để cộng/trừ tháng."""
    return int(nam) * 12 + (int(thang) - 1)


def _nam_thang_con(tong):
    return tong // 12, tong % 12 + 1


def doanh_so_thang_gan_nhat(con, so_thang=24):
    """Doanh số theo tháng — N tháng gần nhất, chạy qua ranh giới năm.

    Trả về list dict {nam, thang, so_luong, doanh_so} sắp xếp cũ -> mới.
    Tháng không có phiếu xuất vẫn được liệt kê với doanh_số = 0 để đồ thị
    24 tháng liền mạch, không bị nhảy cột.
    """
    rows = con.execute(
        """SELECT substr(ngay_phieu,1,4) AS nam, substr(ngay_phieu,6,2) AS thang,
                  SUM(so_luong)  AS so_luong,
                  SUM(thanh_tien) AS doanh_so
           FROM phieu_giaodich
           WHERE loai_phieu IN ('XUAT','XUAT_KYGUI')
             AND ngay_phieu IS NOT NULL AND ngay_phieu != ''
           GROUP BY nam, thang ORDER BY nam, thang"""
    ).fetchall()
    if not rows:
        return []
    co = {(str(r["nam"]), int(r["thang"])): r for r in rows}
    ket_thuc = _thang_con(str(rows[-1]["nam"]), rows[-1]["thang"])
    out = []
    for lech in range(-(int(so_thang) - 1), 1):
        nam, thang = _nam_thang_con(ket_thuc + lech)
        r = co.get((str(nam), thang))
        out.append({"nam": nam, "thang": thang,
                    "so_luong": r["so_luong"] if r else 0,
                    "doanh_so": r["doanh_so"] if r else 0})
    return out


def doanh_so_theo_khach(con, nam=None):
    nam = nam or date.today().year
    return con.execute(
        """SELECT k.ten_kh, SUM(p.thanh_tien) AS doanh_so
           FROM phieu_giaodich p JOIN dm_khachhang k ON k.ma_kh = p.ma_kh
           WHERE p.loai_phieu IN ('XUAT','XUAT_KYGUI')
             AND substr(p.ngay_phieu,1,4) = ?
           GROUP BY k.ten_kh
           HAVING SUM(p.thanh_tien) > 0
           ORDER BY doanh_so DESC""",
        (str(nam),),
    ).fetchall()


def doanh_so_theo_sp(con, nam=None):
    nam = nam or date.today().year
    return con.execute(
        """SELECT v.ma_vt, v.ten_vt, SUM(p.thanh_tien) AS doanh_so
           FROM phieu_giaodich p JOIN dm_vattu v ON v.ma_vt = p.ma_vt
           WHERE p.loai_phieu IN ('XUAT','XUAT_KYGUI')
             AND substr(p.ngay_phieu,1,4) = ?
           GROUP BY v.ma_vt
           HAVING SUM(p.thanh_tien) > 0
           ORDER BY doanh_so DESC""",
        (str(nam),),
    ).fetchall()


def thi_phan(con, nam=None):
    """Thị phần nội bộ = tỷ trọng doanh số từng khách hàng."""
    rows = doanh_so_theo_khach(con, nam)
    tong = sum(r["doanh_so"] for r in rows) or 1
    return [{"ten_kh": r["ten_kh"], "doanh_so": r["doanh_so"],
             "ti_le": r["doanh_so"] / tong * 100} for r in rows]


def tien_do_hop_dong(con):
    return con.execute("SELECT * FROM v_tiendo_hopdong").fetchall()

# ============================================================
# 7. SỐ TIỀN BẰNG CHỮ — cho biên bản giao hàng
# ============================================================

_CHU = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_NHOM = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ"]


def _doc_3_so(n):
    """Đọc 3 chữ số tiếng Việt."""
    tram, chuc, dv = n // 100, (n % 100) // 10, n % 10
    s = ""
    if tram:
        s += _CHU[tram] + " trăm "
    if chuc == 0 and dv and tram:
        s += "linh "
    elif chuc == 1:
        s += "mười "
    elif chuc:
        s += _CHU[chuc] + " mươi "
    if dv == 1 and chuc > 1:
        s += "mốt"
    elif dv == 5 and chuc:
        s += "lăm"
    elif dv:
        s += _CHU[dv]
    return s.strip()


def so_tien_bang_chu(so_tien):
    """1234567 -> 'một triệu hai trăm ba mươi tư nghìn năm trăm sáu mươi bảy đồng'"""
    n = int(round(abs(float(so_tien or 0))))
    if n == 0:
        return "không đồng"
    # tách thành từng nhóm 3 chữ số
    nhom, t = [], n
    while t > 0:
        nhom.append(t % 1000)
        t //= 1000
    parts = []
    for i in range(len(nhom) - 1, -1, -1):
        if nhom[i] == 0:
            continue
        parts.append(_doc_3_so(nhom[i]) + (" " + _NHOM[i] if i < len(_NHOM) else ""))
    return " ".join(p for p in parts if p).strip() + " đồng"

# ============================================================
# 8. BIÊN BẢN GIAO HÀNG — dữ liệu cho mẫu in
# ============================================================

def bien_ban(con, so_phieu_gia_tri=None):
    """Lấy thông tin để in biên bản giao hàng cho 1 phiếu xuất.
    Trả về dict; template in do app_desktop tự render (print dialog / PDF).
    Lưu ý: KHÔNG hiển thị hạn sử dụng. Gom các dòng cùng ma_vt (cộng dồn so_luong)."""
    if not so_phieu_gia_tri:
        r = con.execute(
            "SELECT so_phieu FROM phieu_giaodich WHERE loai_phieu='XUAT' ORDER BY ngay_lap DESC LIMIT 1"
        ).fetchone()
        if not r:
            return None
        so_phieu_gia_tri = r["so_phieu"]

    rows = con.execute(
        """SELECT p.*, k.ten_kh, k.dia_chi, k.ma_so_thue, v.ten_vt, v.dvt
           FROM phieu_giaodich p
           LEFT JOIN dm_khachhang k ON k.ma_kh = p.ma_kh
           LEFT JOIN dm_vattu v ON v.ma_vt = p.ma_vt
           WHERE p.so_phieu = ? ORDER BY p.rowid""",
        (so_phieu_gia_tri,),
    ).fetchall()
    if not rows:
        return None

    # Gom các dòng cùng ma_vt (cộng dồn so_luong)
    grouped = {}
    for r in rows:
        ma_vt = r["ma_vt"]
        if ma_vt not in grouped:
            grouped[ma_vt] = {
                "ten_vt": r["ten_vt"], "ma_vt": ma_vt, "dvt": r["dvt"],
                "so_luong": 0.0, "don_gia": r["don_gia"] or 0,
            }
        grouped[ma_vt]["so_luong"] += (r["so_luong"] or 0)

    items, tong = [], 0.0
    for g in grouped.values():
        tt = g["so_luong"] * g["don_gia"]
        tong += tt
        items.append({
            "ten_vt": g["ten_vt"], "ma_vt": g["ma_vt"], "dvt": g["dvt"],
            "so_luong": g["so_luong"], "don_gia": g["don_gia"], "thanh_tien": tt,
        })
    vat = tong * 0.08
    d = None
    try:
        d = datetime.strptime(rows[0]["ngay_phieu"], "%Y-%m-%d").date()
    except Exception:
        d = date.today()
    return {
        "so_phieu": so_phieu_gia_tri,
        "ngay": d.day, "thang": d.month, "nam": d.year,
        "ten_kh": rows[0]["ten_kh"] or "", "dia_chi": rows[0]["dia_chi"] or "",
        "ma_so_thue": rows[0]["ma_so_thue"] or "",
        "khoa_nhan": rows[0]["khoa_nhan"] or "", "nguoi_goi": rows[0]["nguoi_goi"] or "",
        "so_hop_dong": rows[0]["so_hop_dong"] or "",
        "items": items, "tong": tong, "vat": vat, "tong_cong": tong + vat,
        "bang_chu": so_tien_bang_chu(tong + vat),
        "nguoi_lap": rows[0]["nguoi_lap"] or "",
    }

# ============================================================
# 9. DANH MỤC
# ============================================================

def ds_vattu(con, q=""):
    """Danh sách vật tư. Nếu có q → tìm kiếm, trả về tối đa 5 kết quả."""
    sql = "SELECT ma_vt, ten_vt, dvt, don_gia, ton_toi_thieu, hang_sx, nhom_vt FROM dm_vattu"
    args = ()
    if q:
        sql += " WHERE ma_vt LIKE ? OR ten_vt LIKE ?"
        args = (f"%{q}%", f"%{q}%")
        sql += " ORDER BY ten_vt LIMIT 5"
    else:
        sql += " ORDER BY ten_vt"
    return con.execute(sql, args).fetchall()


def ds_khachhang(con):
    return con.execute(
        "SELECT ma_kh, ten_kh, dia_chi, ma_so_thue, khu_vuc FROM dm_khachhang ORDER BY ten_kh"
    ).fetchall()


# ============================================================
# 10. KÝ GỬI — hàng gửi bệnh viện giữ, vẫn là tài sản công ty
# ============================================================

def ton_kho_kygui(con):
    """Tồn kho ký gửi theo bệnh viện (thay sheet CsStock)."""
    return con.execute("SELECT * FROM v_ton_kho_kygui ORDER BY ten_kh, ten_vt").fetchall()


def ghi_phieu_kygui(con, loai, ngay, ma_vt, so_luong, ma_kh,
                    khoa_nhan=None, nguoi_goi=None, nguoi_lap="", ghi_chu=""):
    """Ghi phiếu ký gửi (KYGUI) hoặc xuất ký gửi (XUAT_KYGUI).
    KYGUI = chuyển từ kho công ty sang kho KH (tài sản vẫn của cty).
    XUAT_KYGUI = bán hàng trong số ký gửi (doanh số được ghi nhận)."""
    if loai not in ("KYGUI", "XUAT_KYGUI"):
        raise ValueError(tf("Loại phiếu ký gửi không hợp lệ: {}", loai))
    if not ma_kh:
        raise ValueError(t("Phiếu ký gửi phải có khách hàng"))
    # Kiểm tra đủ hàng trong ký gửi cho XUAT_KYGUI
    if loai == "XUAT_KYGUI":
        ton = con.execute(
            "SELECT COALESCE(SUM(CASE WHEN loai_phieu='KYGUI' THEN so_luong "
            "                        WHEN loai_phieu='XUAT_KYGUI' THEN -so_luong END),0) "
            "FROM phieu_giaodich WHERE ma_vt=? AND ma_kh=?",
            (ma_vt, ma_kh)).fetchone()[0] or 0
        if ton < float(so_luong):
            raise ValueError(tf("Ký gửi chỉ còn {} {} tại KH này, không đủ xuất {}", ton, ma_vt, so_luong))
    gia, _ = gia_ban(con, ma_vt, ma_kh)
    return ghi_phieu(con, loai, ngay, ma_vt, so_luong, gia,
                     ma_kh=ma_kh, khoa_nhan=khoa_nhan, nguoi_goi=nguoi_goi,
                     nguoi_lap=nguoi_lap, ghi_chu=ghi_chu)


# ============================================================
# 11. XUẤT HÓA ĐƠN TRƯỚC — xuất hóa đơn trước, giao hàng sau
# ============================================================

def xuat_hoadon_truoc(con, ngay, ma_vt, so_luong, ma_kh, so_hoa_don,
                      so_hop_dong=None, nguoi_lap="", ghi_chu=""):
    """Phiếu xuất hóa đơn trước: xuất hóa đơn nhưng chưa giao hàng đủ.
    Số lượng đã giao = tổng phiếu XUAT có cùng so_hoa_don."""
    if not so_hoa_don:
        raise ValueError(t("Thiếu số hóa đơn"))
    # Kiểm tra không vượt quá số đã xuất hóa đơn
    da_xuat_hd = con.execute(
        "SELECT COALESCE(SUM(so_luong),0) FROM phieu_giaodich "
        "WHERE loai_phieu='XUAT_HOADON_TRUOC' AND so_hoa_don=?",
        (so_hoa_don,)).fetchone()[0] or 0
    da_giao = con.execute(
        "SELECT COALESCE(SUM(so_luong),0) FROM phieu_giaodich "
        "WHERE loai_phieu='XUAT' AND so_hoa_don=?",
        (so_hoa_don,)).fetchone()[0] or 0
    # Logic: tổng đã xuất hóa độn (kể cả phiếu đang tạo) phải >= tổng đã giao.
    # Nếu không, sẽ xuất hóa độn nhiều hơn hàng thực tế giao.
    if da_giao > da_xuat_hd + float(so_luong):
        raise ValueError(tf("Đã giao {} nhưng chỉ xuất hóa độn {}", da_giao, da_xuat_hd) + 
                         f"(thêm phiếu này = {da_xuat_hd + float(so_luong)}). "
                         f"Không thể giao nhiều hơn đã xuất hóa độn.")
    gia, _ = gia_ban(con, ma_vt, ma_kh)
    return ghi_phieu(con, "XUAT_HOADON_TRUOC", ngay, ma_vt, so_luong, gia,
                     ma_kh=ma_kh, so_hop_dong=so_hop_dong, so_hoa_don=so_hoa_don,
                     nguoi_lap=nguoi_lap, ghi_chu=ghi_chu)


def tien_do_hoadon_truoc(con):
    """Tiến độ xuất hóa đơn trước (thay sheet Invoice in advance)."""
    return con.execute("SELECT * FROM v_xuat_hoadon_truoc").fetchall()


# ============================================================
# 12. TRA CỨU LỊCH SỬ KHÁCH HÀNG
# ============================================================

def lich_su_khachhang(con, ma_kh=None, tu_ngay=None, den_ngay=None):
    """Lịch sử giao dịch của 1 hoặc tất cả khách hàng, lọc theo thời gian."""
    sql = "SELECT * FROM v_lich_su_khachhang WHERE 1=1"
    args = ()
    if ma_kh:
        sql += " AND ma_kh = ?"
        args += (ma_kh,)
    if tu_ngay:
        sql += " AND ngay_phieu >= ?"
        args += (tu_ngay,)
    if den_ngay:
        sql += " AND ngay_phieu <= ?"
        args += (den_ngay,)
    return con.execute(sql + " ORDER BY ngay_phieu DESC, ngay_lap DESC", args).fetchall()


# ============================================================
# 13. AUTH — đăng nhập, phiên, phân quyền tài khoản
# ============================================================
try:
    import bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False

import hashlib
import hmac
import secrets

VAI_TRO = ("admin", "kinhdoanh", "ketoan", "kho", "nhanvien")

# Mật khẩu mặc định khi tạo tài khoản — bắt buộc đổi ở lần đăng nhập đầu.
MAT_KHAU_MAC_DINH = "123456"


def hash_password(password: str) -> str:
    """Băm mật khẩu. bcrypt nếu có, fallback PBKDF2-HMAC-SHA256 (stdlib).
    PBKDF2 là lựa chọn an toàn — không dùng sha256 trần như bản cũ vì nó dễ
    bị dò mật khẩu bằng GPU/rainbow table."""
    if _HAS_BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2${salt}${dk.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Kiểm tra mật khẩu đã băm. Dùng compare dạng hằng thời gian để tránh
    lộ thông tin qua timing attack."""
    if not hashed:
        return False
    if _HAS_BCRYPT and not hashed.startswith(("pbkdf2$", "sha256$")):
        try:
            return bcrypt.checkpw(password.encode(), hashed.encode())
        except ValueError:
            return False
    if hashed.startswith("pbkdf2$"):
        try:
            _, salt, dk = hashed.split("$")
            calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
            return hmac.compare_digest(calc, dk)
        except ValueError:
            return False
    # định dạng cũ (sha256 cố định) — chỉ để verify DB cũ, sẽ tự nâng cấp
    legacy = "sha256$" + hashlib.sha256(("qlvt_salt_2026" + password).encode()).hexdigest()
    return hmac.compare_digest(legacy, hashed)


def doi_mat_khau(con, user_id, mat_khau_cu, mat_khau_moi, kiem_tra_cu=True):
    """Đổi mật khẩu. Trả về None nếu OK, hoặc thông báo lỗi."""
    row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return "Không tìm thấy tài khoản"
    if kiem_tra_cu and not verify_password(mat_khau_cu, row["password"]):
        return t("Mật khẩu hiện tại không đúng")
    loi = kiem_tra_mat_khau(mat_khau_moi)
    if loi:
        return loi
    con.execute("UPDATE users SET password=?, lan_doi_mk=NULL WHERE id=?",
                (hash_password(mat_khau_moi), user_id))
    con.commit()
    ghi_log(con, row["username"], "DOI_MAT_KHAU", "users", str(user_id))
    return None


def kiem_tra_mat_khau(mk: str):
    """Yêu cầu mật khẩu tối thiểu 6 ký tự. Trả về lỗi hoặc None."""
    if not mk or len(mk) < 6:
        return "Mật khẩu phải có ít nhất 6 ký tự"
    return None


def tao_token(secret: bytes) -> tuple[str, str]:
    """Sinh token ngẫu nhiên + HMAC signature.
    Token gửi cho client = f"{nonce}.{sig}". DB lưu HMAC(token) làm khoá.
    Trả về (token_plaintext, token_hash)."""
    nonce = secrets.token_urlsafe(24)
    sig = hmac.new(secret, nonce.encode(), hashlib.sha256).hexdigest()
    token = f"{nonce}.{sig}"
    return token, hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def kiem_tra_token(secret: bytes, token: str) -> bool:
    """Xác minh chữ ký HMAC của token. Chống giả mạo cookie/phiên."""
    try:
        nonce, sig = token.split(".")
    except ValueError:
        return False
    calc = hmac.new(secret, nonce.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, sig)


def secret_key(db_path=None) -> bytes:
    """Khoá bí mật dùng ký phiên. Sinh 1 lần rồi lưu trong file .secret cạnh DB
    → server khởi động lại vẫn nhận các phiên đang mở (không đá đăng xuất
    toàn bộ người dùng mỗi lần restart)."""
    # BẮT BUỘC dùng biến module DB_PATH, không dùng tham số db_path: nếu để
    # tham số mặc định là None rồi lại tự gán db_path = DB_PATH ở đầu hàm thì
    # tên biến cục bộ che mất module → RecursionError.
    path = db_path if db_path else DB_PATH
    p = os.path.join(os.path.dirname(os.path.abspath(path)), ".secret")
    if os.path.exists(p):
        return open(p, "rb").read().strip()
    key = secrets.token_bytes(32)
    try:
        open(p, "wb").write(key)
        os.chmod(p, 0o600)
    except OSError:
        # không ghi được (hạn chế quyền) → dùng khoá tạm trong bộ nhớ
        return key
    return key


def tao_session(con, user_id, het_han, ip=None, user_agent=None):
    """Mở phiên mới cho user. Trả về token plaintext (gửi về client)."""
    token, token_hash = tao_token(secret_key())
    con.execute(
        "INSERT INTO sessions (token_hash,user_id,het_han,ip,user_agent) VALUES (?,?,?,?,?)",
        (token_hash, user_id, het_han, ip, user_agent))
    con.execute(
        "UPDATE users SET lan_cuoi_dang_nhap=datetime('now','localtime') WHERE id=?",
        (user_id,))
    con.commit()
    ghi_log(con, str(user_id), "DANG_NHAP", "sessions", f"user={user_id}")
    return token


def xoa_session(con, token: str):
    """Đăng xuất: xoá phiên khỏi DB."""
    if not token:
        return
    token_hash = hmac.new(secret_key(), token.encode(), hashlib.sha256).hexdigest()
    con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
    con.commit()


def don_session(con, user_id):
    """Đăng xuất toàn bộ thiết bị của 1 user (dùng khi đổi mật khẩu / khoá tài khoản)."""
    con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    con.commit()


def nang_cap_mat_khau_cu(con, username, password_hash_cu, mat_khau_moi):
    """Nâng cấp hash cũ (sha256 trần) lên bcrypt/pbkdf2 khi đăng nhập đúng.
    Trả về True nếu đã nâng cấp."""
    if password_hash_cu.startswith(("pbkdf2$",)) or (_HAS_BCRYPT and password_hash_cu.startswith("$2")):
        return False
    if not _HAS_BCRYPT and password_hash_cu.startswith("pbkdf2$"):
        return False
    con.execute("UPDATE users SET password=? WHERE username=?",
                (hash_password(mat_khau_moi), username))
    con.commit()
    return True


def phan_quyyen(vai_tro, chuc_nang):
    """Kiểm tra quyền. admin có tất cả; các vai trò khác theo bảng quyền."""
    if vai_tro == "admin":
        return True
    # Bảng quyền: vai_tro -> set chuc_nang được phép
    QUYEN = {
        "kinhdoanh": {"xem", "nhap", "xuat", "kygui", "xuat_kygui",
                      "hoadon_truoc", "baocao", "lichsu", "khachhang", "hopdong"},
        "ketoan":    {"xem", "baocao", "lichsu", "hoadon_truoc", "khachhang"},
        "kho":       {"xem", "nhap", "kygui", "xuat_kygui"},
        "nhanvien":  {"xem", "khachhang"},
    }
    return chuc_nang in QUYEN.get(vai_tro, set())


def quyen_chuc_nang() -> dict:
    """Bảng quyền hiển thị cho UI (checkbox)."""
    return {
        "xem": t("Xem dữ liệu (tồn kho, khách hàng)"),
        "nhap": t("Nhập kho"),
        "xuat": t("Bán hàng / xuất hàng"),
        "kygui": t("Ký gửi hàng"),
        "xuat_kygui": t("Xuất ký gửi (bán hàng ký gửi)"),
        "hoadon_truoc": t("Xuất hóa đơn trước"),
        "baocao": t("Xem & xuất báo cáo"),
        "lichsu": t("Tra cứu lịch sử khách hàng"),
        "khachhang": t("Quản lý danh mục khách hàng"),
        "hopdong": t("Quản lý hợp đồng thầu"),
    }


# ------------------------------------------------------------
# Quản lý tài khoản — chạy trong lõi để Desktop và Web dùng chung 1 luật
# ------------------------------------------------------------
def create_user(con, username, password, ten_hien_thi, vai_tro="nhanvien",
                email="", khoa="", doi_mk_lan_dau=False):
    """Tạo tài khoản mới. Trả về id.
    - Từ chối username trùng.
    - vai_tro không hợp lệ → ValueError.
    - doi_mk_lan_dau=True → đánh dấu phải đổi mật khẩu ở lần đăng nhập kế.
    - Mật khẩu rỗng → dùng MAT_KHAU_MAC_DINH và ĐÁNH DẤU bắt buộc đổi, để
      admin hệ thống luôn phải đổi mật khẩu chung ở lần đăng nhập đầu."""
    username = (username or "").strip()
    if not username:
        raise ValueError(t("Thiếu tên đăng nhập"))
    if len(username) < 3:
        raise ValueError(t("Tên đăng nhập phải có ít nhất 3 ký tự"))
    if not re.match(r"^[A-Za-z0-9_.@-]+$", username):
        raise ValueError(t("Tên đăng nhập chỉ dùng chữ, số và . _ - @"))
    if not ten_hien_thi or not str(ten_hien_thi).strip():
        raise ValueError(t("Thiếu tên hiển thị"))
    if vai_tro not in VAI_TRO:
        raise ValueError(tf("Vai trò không hợp lệ: {}", vai_tro))
    if not password:
        # Mật khẩu chung, bắt buộc đổi ở lần đăng nhập kế.
        password = MAT_KHAU_MAC_DINH
        doi_mk_lan_dau = True
    loi_mk = kiem_tra_mat_khau(password)
    if loi_mk:
        raise ValueError(loi_mk)
    try:
        cur = con.execute(
            "INSERT INTO users (username,password,ten_hien_thi,email,vai_tro,khoa,lan_doi_mk)"
            " VALUES (?,?,?,?,?,?,?)",
            (username, hash_password(password), str(ten_hien_thi).strip(), email or "",
             vai_tro, khoa or "", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
             if doi_mk_lan_dau else None))
        con.commit()
    except sqlite3.IntegrityError:
        raise ValueError(tf("Tên đăng nhập '{}' đã tồn tại", username))
    ghi_log(con, username, "TAO_USER", "users", f"{username} | {vai_tro}")
    return cur.lastrowid


def sua_user(con, user_id, ten_hien_thi=None, vai_tro=None, email=None,
             khoa=None, hoat_dong=None, nguoi_thao_tac=""):
    """Cập nhật thông tin tài khoản (không đổi mật khẩu ở đây)."""
    row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise ValueError(t("Không tìm thấy tài khoản"))
    if vai_tro is not None and vai_tro not in VAI_TRO:
        raise ValueError(tf("Vai trò không hợp lệ: {}", vai_tro))
    if vai_tro is not None and row["username"] == "admin" and vai_tro != "admin":
        raise ValueError(t("Không thể hạ quyền tài khoản admin hệ thống"))
    con.execute(
        "UPDATE users SET ten_hien_thi=COALESCE(?,ten_hien_thi),"
        " vai_tro=COALESCE(?,vai_tro), email=COALESCE(?,email),"
        " khoa=COALESCE(?,khoa), hoat_dong=COALESCE(?,hoat_dong) WHERE id=?",
        (ten_hien_thi, vai_tro, email, khoa, hoat_dong, user_id))
    con.commit()
    ghi_log(con, nguoi_thao_tac, "SUA_USER", "users", f"id={user_id} | {row['username']}")


def xoa_user(con, user_id, nguoi_thao_tac=""):
    """Xoá tài khoản. Không cho xoá admin hệ thống (username='admin')."""
    row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise ValueError(t("Không tìm thấy tài khoản"))
    if row["username"] == "admin":
        raise ValueError(t("Không thể xoá tài khoản admin hệ thống"))
    if row["hoat_dong"] != 0:
        con.execute("UPDATE users SET hoat_dong=0 WHERE id=?", (user_id,))
        con.commit()
    con.execute("DELETE FROM users WHERE id=?", (user_id,))
    con.commit()
    ghi_log(con, nguoi_thao_tac, "XOA_USER", "users", f"id={user_id} | {row['username']}")


def dat_lai_mat_khau(con, user_id, mat_khau_moi, nguoi_thao_tac="", doi_lai_phan_hoi=False):
    """Admin đặt lại mật khẩu cho người khác. Không cần mật khẩu cũ.
    đoi_lai_phan_hoi=True → bắt người đó đổi mật khẩu ở lần đăng nhập kế,
    đồng thời đá toàn bộ phiên đang mở."""
    row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise ValueError(t("Không tìm thấy tài khoản"))
    loi = kiem_tra_mat_khau(mat_khau_moi)
    if loi:
        raise ValueError(loi)
    con.execute("UPDATE users SET password=?, lan_doi_mk=? WHERE id=?",
                (hash_password(mat_khau_moi),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S") if doi_lai_phan_hoi else None,
                 user_id))
    if doi_lai_phan_hoi:
        don_session(con, user_id)
    con.commit()
    ghi_log(con, nguoi_thao_tac, "DAT_LAI_MAT_KHAU", "users",
            f"id={user_id} | {row['username']}")
    return True


def authenticate(con, username, password):
    """Đăng nhập. Trả về dict user kèm cờ `phai_doi_mk` nếu đúng, None nếu sai.
    Không lộ tài khoản tồn tại hay không — chỉ trả về None."""
    row = con.execute(
        "SELECT * FROM users WHERE username=? AND hoat_dong=1", (username or "",)).fetchone()
    if not row or not verify_password(password, row["password"]):
        return None
    # Nâng cấp hash yếu → mạnh ngay sau khi đăng nhập thành công
    try:
        if not row["password"].startswith("pbkdf2$"):
            if _HAS_BCRYPT and not row["password"].startswith("$2"):
                con.execute("UPDATE users SET password=? WHERE id=?",
                            (hash_password(password), row["id"]))
                con.commit()
    except sqlite3.Error:
        pass
    return {"id": row["id"], "username": row["username"],
            "ten_hien_thi": row["ten_hien_thi"], "vai_tro": row["vai_tro"],
            "email": row["email"] or "", "khoa": row["khoa"] or "",
            "hoat_dong": row["hoat_dong"],
            "phai_doi_mk": bool(row["lan_doi_mk"])}


def user_theo_token(con, token):
    """Tra user từ token phiên. Kiểm tra chữ ký HMAC + đúng hạn + hoạt động.
    Trả về dict user hoặc None."""
    if not token or not kiem_tra_token(secret_key(), token):
        return None
    token_hash = hmac.new(secret_key(), token.encode(), hashlib.sha256).hexdigest()
    row = con.execute(
        "SELECT s.het_han, u.* FROM sessions s JOIN users u ON u.id=s.user_id"
        " WHERE s.token_hash=?", (token_hash,)).fetchone()
    if not row:
        return None
    if row["hoat_dong"] != 1:
        return None
    try:
        het_han = datetime.strptime(row["het_han"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    if het_han < datetime.now():
        con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        con.commit()
        return None
    return {"id": row["id"], "username": row["username"],
            "ten_hien_thi": row["ten_hien_thi"], "vai_tro": row["vai_tro"],
            "email": row["email"] or "", "khoa": row["khoa"] or "",
            "hoat_dong": row["hoat_dong"], "phai_doi_mk": bool(row["lan_doi_mk"])}


def ds_users(con):
    """Danh sách tài khoản (không trả password hash, không trả token)."""
    return con.execute(
        "SELECT id,username,ten_hien_thi,email,vai_tro,khoa,hoat_dong,"
        " lan_cuoi_dang_nhap,tao_luc FROM users ORDER BY id"
    ).fetchall()


def dem_user(con):
    return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def migrate_users(con):
    """Nâng cấp bảng users cho DB cũ (thiếu cột email/khoa/lan_cuoi_dang_nhap/
    lan_doi_mk) và tạo bảng sessions nếu chưa có. Trả về list cột đã thêm.
    Chạy mỗi lần khởi động — rẻ (1 query PRAGMA) và an toàn (idempotent)."""
    them = []
    cols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    for ten, kieu, mac_dinh in (
        ("email", "TEXT", "''"),
        ("khoa", "TEXT", "''"),
        ("lan_cuoi_dang_nhap", "TEXT", "NULL"),
        ("lan_doi_mk", "TEXT", "NULL"),
    ):
        if ten not in cols:
            # KHÔNG dùng DEFAULT cho cột mới ở đây: SQLite sẽ tự điền giá trị
            # mặc định cho toàn bộ dòng cũ, làm mất ý nghĩa "chưa từng đăng nhập".
            con.execute(f"ALTER TABLE users ADD COLUMN {ten} {kieu}")
            them.append(ten)
    # Bỏ ràng buộc CHECK cũ (vai_tro IN ('admin','kinhdoanh','ketoan','kho'))
    # nếu nó tồn tại — SQLite không có DROP CHECK, phải dựng lại bảng.
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
    if "nhanvien" not in sql and "vai_tro" in sql:
        con.executescript(_REBUILD_USERS_SQL)
        them.append("vai_tro(bo-sung nhanvien)")
    con.commit()
    return them


# Dựng lại bảng users khi cần nới ràng buộc CHECK. Giữ nguyên mọi dòng dữ liệu.
_REBUILD_USERS_SQL = """
PRAGMA foreign_keys=OFF;
BEGIN;
CREATE TABLE users_new (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  username   TEXT UNIQUE NOT NULL,
  password   TEXT NOT NULL,
  ten_hien_thi TEXT NOT NULL,
  email      TEXT DEFAULT '',
  vai_tro    TEXT NOT NULL DEFAULT 'nhanvien'
             CHECK (vai_tro IN ('admin','kinhdoanh','ketoan','kho','nhanvien')),
  hoat_dong  INTEGER NOT NULL DEFAULT 1,
  khoa       TEXT DEFAULT '',
  lan_cuoi_dang_nhap TEXT,
  lan_doi_mk TEXT,
  tao_luc    TEXT DEFAULT (datetime('now','localtime'))
);
INSERT INTO users_new (id,username,password,ten_hien_thi,email,vai_tro,hoat_dong,
                       khoa,lan_cuoi_dang_nhap,lan_doi_mk,tao_luc)
  SELECT id,username,password,ten_hien_thi,
         COALESCE(email,''), vai_tro, hoat_dong,
         COALESCE(khoa,''), COALESCE(lan_cuoi_dang_nhap,NULL),
         COALESCE(lan_doi_mk,NULL), COALESCE(tao_luc,datetime('now','localtime'))
  FROM users;
DROP TABLE users;
ALTER TABLE users_new RENAME TO users;
COMMIT;
PRAGMA foreign_keys=ON;
"""


def ensure_auth_schema(con):
    """Gọi 1 lần lúc khởi động: đảm bảo users/sessions đúng chuẩn + có admin.
    Trả về dict mô tả việc đã làm (để hiển thị trong log)."""
    ket_qua = {"them_cot": [], "admin": None}
    co_users = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()[0] > 0
    if co_users:
        ket_qua["them_cot"] = migrate_users(con)
    else:
        # DB cũ (schema trước 2026-10) chưa có bảng users → tạo nguyên bảng
        # theo schema.sql mới. Không có dòng nào nên không mất dữ liệu.
        con.executescript(SCHEMA_USERS_SQL)
        con.commit()
        ket_qua["them_cot"].append("users")
    # sessions có thể thiếu ở DB cũ
    co_sessions = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sessions'"
    ).fetchone()[0] > 0
    if not co_sessions:
        con.executescript(SCHEMA_SESSIONS_SQL)
        con.commit()
        ket_qua["them_cot"].append("sessions")
    so_admin, da_tao = dam_bao_admin_mac_dinh(con)
    ket_qua["admin"] = {"so_admin": so_admin, "da_tao_moi": da_tao}
    return ket_qua


# Tách riêng để tạo bảng users khi DB cũ hoàn toàn chưa có bảng này.
SCHEMA_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  username   TEXT UNIQUE NOT NULL,
  password   TEXT NOT NULL,
  ten_hien_thi TEXT NOT NULL,
  email      TEXT DEFAULT '',
  vai_tro    TEXT NOT NULL DEFAULT 'nhanvien'
             CHECK (vai_tro IN ('admin','kinhdoanh','ketoan','kho','nhanvien')),
  hoat_dong  INTEGER NOT NULL DEFAULT 1,
  khoa       TEXT DEFAULT '',
  lan_cuoi_dang_nhap TEXT,
  lan_doi_mk TEXT,
  tao_luc    TEXT DEFAULT (datetime('now','localtime'))
);
"""


# Tách riêng để chạy được mà không cần đọc cả file schema.sql
SCHEMA_SESSIONS_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tao_luc    TEXT DEFAULT (datetime('now','localtime')),
  het_han    TEXT NOT NULL,
  ip         TEXT,
  user_agent TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
"""


def dam_bao_admin_mac_dinh(con):
    """Đảm bảo luôn có ít nhất 1 admin hoạt động. Trả về (so_admin, da_tao_moi).
    Nếu bảng users trống hoặc không còn admin nào hoạt động → tạo lại admin."""
    rows = con.execute("SELECT id,username,vai_tro,hoat_dong FROM users ORDER BY id").fetchall()
    admins = [r for r in rows if r["vai_tro"] == "admin"]
    active = [r for r in admins if r["hoat_dong"] == 1]
    if not rows:
        # doi_mk_lan_dau=True: admin phải đổi mật khẩu ở lần đăng nhập đầu.
        # Admin mặc định không bao giờ được để nguyên mật khẩu chung.
        create_user(con, "admin", "admin123", "Quản trị hệ thống", "admin",
                    khoa="IT", doi_mk_lan_dau=True)
        return 1, True
    if not active:
        if admins:
            # admin bị khoá → mở khoá lại admin đầu tiên để không bị khoá cứng
            con.execute("UPDATE users SET hoat_dong=1 WHERE id=?", (admins[0]["id"],))
            con.commit()
            ghi_log(con, "he_thong", "MO_KHOA_ADMIN", "users",
                    f"id={admins[0]['id']} | {admins[0]['username']}")
            return 1, True
        create_user(con, "admin", "admin123", "Quản trị hệ thống", "admin",
                    khoa="IT", doi_mk_lan_dau=True)
        return 1, True
    return len(active), False


# ============================================================
# 14. BACKUP & QUẢN LÝ KHÁCH HÀNG
# ============================================================
def backup_db(con=None, backup_dir=None):
    """Sao lưu DB thành bản backup có timestamp.
    Trả về (path_backup, dung_luong_mb) hoặc (None, lỗi)."""
    import shutil
    src = getattr(con, "execute", None) and None
    # Lấy path từ connection SQLite
    if con is not None:
        try:
            src = con.execute("PRAGMA database_list").fetchone()[2]
        except Exception:
            src = None
    if src is None or not src or src == ":memory:":
        raise ValueError("Không xác định được đường dẫn DB")
    if not os.path.exists(src):
        return None, tf("Không tìm thấy DB: {}", src)
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(src), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"qlvt_backup_{ts}.db"
    dst = os.path.join(backup_dir, name)
    # Đóng transaction trước khi copy (WAL mode: copy cả -wal)
    try:
        con = sqlite3.connect(src)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
    except Exception:
        pass
    shutil.copy2(src, dst)
    size_mb = os.path.getsize(dst) / 1024 / 1024
    return dst, size_mb


def khoi_phuc_db(con, nguon_path):
    """Khôi phục DB từ file người dùng chọn.
    - Validate file nguồn là SQLite hợp lệ (có bảng dm_vattu)
    - Tự động backup DB hiện tại trước khi ghi đè (an toàn)
    - Trả về (path_backup_cu, loi). loi=None nếu thành công."""
    if not nguon_path or not os.path.exists(nguon_path):
        return None, t("File khôi phục không tồn tại")
    # Validate file nguồn
    try:
        test = sqlite3.connect(nguon_path)
        ok = test.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='dm_vattu'"
        ).fetchone()[0] > 0
        test.close()
    except Exception as e:
        return None, tf("File không phải SQLite hợp lệ: {}", e)
    if not ok:
        return None, t("File không phải DB QLVT (thiếu bảng dm_vattu)")

    # Backup DB hiện tại trước khi khôi phục (nếu có dữ liệu)
    src = con.execute("PRAGMA database_list").fetchone()[2]
    bak = None
    if src and os.path.exists(src) and src != ":memory:":
        try:
            bak, _ = backup_db(con)
        except Exception:
            bak = None

    import shutil
    # Đóng WAL checkpoint + ĐÓNG connection trước khi thay file (Windows lock file)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    try:
        con.close()
    except Exception:
        pass
    # Ghi đè file DB + xóa WAL/SHM cũ
    shutil.copy2(nguon_path, src)
    for e in ("-wal", "-shm"):
        if os.path.exists(src + e):
            os.remove(src + e)
    return bak, None

def luu_khachhang(con, ma_kh=None, ten_kh="", dia_chi="", ma_so_thue="", khu_vuc=""):
    """Tạo KH mới hoặc cập nhật KH. Trả về ma_kh.
    Nếu ma_kh=None → tạo mới (sinh mã tự động).
    Sinh mã KH an toàn: dùng MAX(CAST(substr)).
    """
    if not ten_kh or not str(ten_kh).strip():
        raise ValueError(t("Thiếu tên khách hàng"))
    ten_kh = str(ten_kh).strip()
    if ma_kh:
        # Cập nhật
        con.execute(
            "UPDATE dm_khachhang SET ten_kh=?, dia_chi=?, ma_so_thue=?, khu_vuc=? WHERE ma_kh=?",
            (ten_kh, dia_chi, ma_so_thue, khu_vuc, ma_kh))
        con.commit()
        ghi_log(con, "", "SUA_KH", "dm_khachhang", f"{ma_kh} | {ten_kh}")
        return ma_kh
    # Tạo mới — sinh mã tự động an toàn
    row = con.execute(
        "SELECT MAX(CAST(substr(ma_kh, 3) AS INTEGER)) FROM dm_khachhang"
    ).fetchone()
    num = (row[0] or 0) + 1
    ma_kh = f"KH{num:03d}"
    con.execute(
        "INSERT INTO dm_khachhang (ma_kh,ten_kh,dia_chi,ma_so_thue,khu_vuc) VALUES (?,?,?,?,?)",
        (ma_kh, ten_kh, dia_chi, ma_so_thue, khu_vuc))
    con.commit()
    ghi_log(con, "", "TAO_KH", "dm_khachhang", f"{ma_kh} | {ten_kh}")
    return ma_kh

def xoa_khachhang(con, ma_kh):
    """Xóa KH nếu chưa có phiếu giao dịch / hợp đồng."""
    n = con.execute("SELECT COUNT(*) FROM phieu_giaodich WHERE ma_kh=?", (ma_kh,)).fetchone()[0]
    n += con.execute("SELECT COUNT(*) FROM hop_dong WHERE ma_kh=?", (ma_kh,)).fetchone()[0]
    if n > 0:
        raise ValueError(tf("Không thể xóa KH {}: đã có {} phiếu/hợp đồng liên quan", ma_kh, n))
    con.execute("DELETE FROM dm_khachhang WHERE ma_kh=?", (ma_kh,))
    ghi_log(con, "", "XOA_KH", "dm_khachhang", ma_kh)

def ds_phieu(con, loai=None, limit=200):
    sql = """SELECT p.so_phieu, p.loai_phieu, p.ngay_phieu, p.ma_vt, v.ten_vt, v.dvt,
                    p.so_luong, p.don_gia, p.thanh_tien,
                    k.ten_kh, p.khoa_nhan, p.nguoi_lap
             FROM phieu_giaodich p
             LEFT JOIN dm_vattu v ON v.ma_vt = p.ma_vt
             LEFT JOIN dm_khachhang k ON k.ma_kh = p.ma_kh"""
    args = ()
    if loai:
        sql += " WHERE p.loai_phieu = ?"
        args = (loai,)
    return con.execute(sql + " ORDER BY p.ngay_lap DESC LIMIT ?", args + (limit,)).fetchall()


# ============================================================
# 15. HỢP ĐỒNG THẦU
# ============================================================

def ds_hop_dong_con_han(con, ma_kh=None):
    """Danh sách hợp đồng CÒN HẠN của khách hàng.
    Trả về các hợp đồng có ngay_het_han >= hôm nay (hoặc NULL).
    Nếu ma_kh=None → tất cả hợp đồng còn hạn."""
    if ma_kh:
        return con.execute(
            """SELECT DISTINCT so_hd FROM hop_dong
               WHERE (ngay_het_han IS NULL OR ngay_het_han >= date('now'))
                 AND ma_kh=?
               ORDER BY so_hd""",
            (ma_kh,),
        ).fetchall()
    return con.execute(
        """SELECT DISTINCT so_hd FROM hop_dong
           WHERE ngay_het_han IS NULL OR ngay_het_han >= date('now')
           ORDER BY so_hd"""
    ).fetchall()


def luu_hop_dong(con, so_hd, ma_kh, ma_vt, so_luong, don_gia, ngay_ky=None,
                 ngay_hieu_luc=None, ngay_het_han=None):
    """Thêm/cập nhật hợp đồng. INSERT OR REPLACE INTO hop_dong."""
    con.execute(
        """INSERT OR REPLACE INTO hop_dong
           (so_hd, ma_kh, ma_vt, so_luong, don_gia, ngay_ky, ngay_hieu_luc, ngay_het_han)
           VALUES (?,?,?,?,?,?,?,?)""",
        (so_hd, ma_kh, ma_vt, so_luong, don_gia, ngay_ky, ngay_hieu_luc, ngay_het_han),
    )
    con.commit()


# ============================================================
# 16. XUẤT PDF
# ============================================================

def xuat_pdf(con, duong_dan_pdf):
    """Xuất biên bản giao hàng ra file PDF.
    Dùng reportlab. Trả về đường dẫn file PDF đã tạo.
    PDF format: A4, font Helvetica, bảng biên bản giao hàng với:
    - Tiêu đề: BIÊN BẢN GIAO HÀNG
    - Thông tin: số phiếu, ngày, số hợp đồng, khách hàng, địa chỉ, MST, khoa nhận
    - Bảng: STT | Tên vật tư | Mã VT | ĐVT | Tổng SL | Đơn giá | Thành tiền
    - Tổng cộng, thuế 8%, tổng thanh toán
    - Dòng chữ ký
    Lưu vào dist/bienban/ (tạo thư mục nếu chưa có). Trả về (duong_dan_pdf, loi)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        return None, t("Thiếu thư viện reportlab. Cài: pip install reportlab")

    # Lấy dữ liệu biên bản
    bb = bien_ban(con)
    if not bb:
        return None, t("Không tìm thấy phiếu xuất nào")

    # Tạo thư mục dist/bienban/
    dist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "bienban")
    os.makedirs(dist_dir, exist_ok=True)

    # Nếu duong_dan_pdf chỉ là tên file, thêm đường dẫn dist/bienban/
    if not duong_dan_pdf:
        import tempfile
        duong_dan_pdf = os.path.join(tempfile.gettempdir(), "baocao.pdf")
    if not os.path.isabs(duong_dan_pdf):
        duong_dan_pdf = os.path.join(dist_dir, duong_dan_pdf)

    # Tạo PDF
    doc = SimpleDocTemplate(duong_dan_pdf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []

    # Tiêu đề
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, alignment=1, spaceAfter=10)
    elements.append(Paragraph("BIÊN BẢN GIAO HÀNG", title_style))
    elements.append(Spacer(1, 5*mm))

    # Thông tin
    info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10, spaceAfter=2)
    elements.append(Paragraph(f"<b>Số phiếu:</b> {bb['so_phieu']}", info_style))
    elements.append(Paragraph(f"<b>Ngày:</b> {bb['ngay']}/{bb['thang']}/{bb['nam']}", info_style))
    elements.append(Paragraph(f"<b>Số hợp đồng:</b> {bb['so_hop_dong']}", info_style))
    elements.append(Paragraph(f"<b>Khách hàng:</b> {bb['ten_kh']}", info_style))
    elements.append(Paragraph(f"<b>Địa chỉ:</b> {bb['dia_chi']}", info_style))
    elements.append(Paragraph(f"<b>MST:</b> {bb['ma_so_thue']}", info_style))
    elements.append(Paragraph(f"<b>Khoa nhận:</b> {bb['khoa_nhan']}", info_style))
    elements.append(Spacer(1, 5*mm))

    # Bảng
    data = [["STT", "Tên vật tư", "Mã VT", "ĐVT", "Tổng SL", "Đơn giá", "Thành tiền"]]
    for i, item in enumerate(bb["items"], 1):
        data.append([
            str(i),
            f"{item['ten_vt']} ({item['ma_vt']})",
            item["ma_vt"],
            item["dvt"],
            f"{item['so_luong']:.0f}",
            f"{item['don_gia']:,.0f}",
            f"{item['thanh_tien']:,.0f}",
        ])
    # Tổng cộng
    data.append(["", "", "", "", "", "Tổng cộng:", f"{bb['tong']:,.0f}"])
    data.append(["", "", "", "", "", "Thuế 8%:", f"{bb['vat']:,.0f}"])
    data.append(["", "", "", "", "", "Tổng thanh toán:", f"{bb['tong_cong']:,.0f}"])

    table = Table(data, colWidths=[10*mm, 50*mm, 20*mm, 15*mm, 20*mm, 25*mm, 30*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 5*mm))

    # Bằng chữ
    elements.append(Paragraph(f"<b>Bằng chữ:</b> {bb['bang_chu']}", info_style))
    elements.append(Spacer(1, 10*mm))

    # Chữ ký
    sig_style = ParagraphStyle('Sig', parent=styles['Normal'], fontSize=10, alignment=1)
    elements.append(Paragraph("Người lập", sig_style))
    elements.append(Spacer(1, 15*mm))
    elements.append(Paragraph(f"<i>{bb['nguoi_lap']}</i>", sig_style))

    doc.build(elements)
    return duong_dan_pdf, None


def xuat_baocao_pdf(con, loai, nam, duong_dan_pdf):
    """Xuất báo cáo ra PDF.
    loai: 'm' (tháng), 'q' (quý), 's' (thị phần)
    Dùng reportlab tạo PDF với bảng báo cáo tương ứng.
    Trả về (duong_dan_pdf, loi)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        return None, t("Thiếu thư viện reportlab. Cài: pip install reportlab")

    # Tạo thư mục dist/baocao/
    dist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "baocao")
    os.makedirs(dist_dir, exist_ok=True)

    if not duong_dan_pdf:
        import tempfile
        duong_dan_pdf = os.path.join(tempfile.gettempdir(), "baocao.pdf")
    if not os.path.isabs(duong_dan_pdf):
        duong_dan_pdf = os.path.join(dist_dir, duong_dan_pdf)

    doc = SimpleDocTemplate(duong_dan_pdf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, alignment=1, spaceAfter=10)

    if loai == 'm':
        # Báo cáo tháng
        elements.append(Paragraph(f"BÁO CÁO DOANH SỐ THÁNG NĂM {nam}", title_style))
        elements.append(Spacer(1, 5*mm))
        rows = doanh_so_thang(con, nam)
        data = [["Tháng", "Số lượng", "Doanh số"]]
        for r in rows:
            data.append([r["thang"], f"{r['so_luong']:.0f}", f"{r['doanh_so']:,.0f}"])
    elif loai == 'q':
        # Báo cáo quý
        elements.append(Paragraph(f"BÁO CÁO DOANH SỐ QUÝ NĂM {nam}", title_style))
        elements.append(Spacer(1, 5*mm))
        rows = doanh_so_thang(con, nam)
        # Gom theo quý
        quy = {}
        for r in rows:
            thang = int(r["thang"])
            q = (thang - 1) // 3 + 1
            if q not in quy:
                quy[q] = {"so_luong": 0, "doanh_so": 0}
            quy[q]["so_luong"] += r["so_luong"]
            quy[q]["doanh_so"] += r["doanh_so"]
        data = [["Quý", "Số lượng", "Doanh số"]]
        for q in sorted(quy.keys()):
            data.append([f"Quý {q}", f"{quy[q]['so_luong']:.0f}", f"{quy[q]['doanh_so']:,.0f}"])
    elif loai == 's':
        # Báo cáo thị phần
        elements.append(Paragraph(f"BÁO CÁO THỊ PHẦN NĂM {nam}", title_style))
        elements.append(Spacer(1, 5*mm))
        rows = thi_phan(con, nam)
        data = [["Khách hàng", "Doanh số", "Tỷ lệ (%)"]]
        for r in rows:
            data.append([r["ten_kh"], f"{r['doanh_so']:,.0f}", f"{r['ti_le']:.1f}%"])
    else:
        return None, f"Loại báo cáo không hợp lệ: {loai}"

    table = Table(data, colWidths=[40*mm, 40*mm, 40*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)

    doc.build(elements)
    return duong_dan_pdf, None
