# -*- coding: utf-8 -*-
"""test_v3_fixes.py — Regression tests cho BẢN VIẾT LẠI app_desktop.py.

Chứng minh từng bug đã nêu trong review được sửa ở tầng GUI:
  lichsu IndexError, biên bản thiếu hàng, to_float ×100/÷1000, PDF TypeError,
  font Unicode, validate ngày/SL, đổi ngôn ngữ rebuild toàn bộ, DB path.
Chạy: xvfb-run -a python3 -m pytest test_v3_fixes.py -v
"""
import os
import sys
import uuid

import pytest

SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
DB = os.path.join(SRC, f"_v3fix_{uuid.uuid4().hex[:6]}.db")
os.environ["QLVT_DB"] = DB

import customtkinter as ctk          # noqa: E402
import qlvt_core as core             # noqa: E402
import app_desktop as mod            # noqa: E402
from i18n import set_lang            # noqa: E402


def _dump(widget):
    out = []

    def walk(w):
        for attr in ("text",):
            try:
                v = w.cget(attr)
                if isinstance(v, str) and v.strip():
                    out.append(v)
            except Exception:
                pass
        try:
            for c in w.winfo_children():
                walk(c)
        except Exception:
            pass
    walk(widget)
    return " | ".join(out)


@pytest.fixture(scope="module")
def app():
    a = mod.App.__new__(mod.App)
    ctk.CTk.__init__(a)
    a.title("test-v3")
    a.geometry("1280x760")
    a.con, a.is_new = core.ensure_db(DB)
    core.ensure_auth_schema(a.con)
    # seed danh mục + tồn kho dương (tránh dialog cảnh báo vượt tồn)
    for ma, ten, gia in [("A", "KIM TIÊM 21G", 100000),
                         ("B", "BĂNG DÍNH 3M", 50000)]:
        a.con.execute(
            "INSERT INTO dm_vattu (ma_vt,ten_vt,dvt,hang_sx,nuoc_sx,nhom_vt,"
            "so_dk,don_gia,ton_toi_thieu) VALUES (?,?,?,?,?,?,?,?,?)",
            (ma, ten, "Cái", "X", "VN", "VTTH", "DK", gia, 0))
    a.con.execute(
        "INSERT INTO dm_khachhang (ma_kh,ten_kh,dia_chi,ma_so_thue,khu_vuc) "
        "VALUES (?,?,?,?,?)", ("VDH", "Bệnh viện Việt Đức", "HN", "010", "MB"))
    a.con.commit()
    core.ghi_phieu(a.con, "NHAP", "2026-10-01", "A", 500, 90000,
                   nguoi_lap="seed")
    core.ghi_phieu(a.con, "NHAP", "2026-10-01", "B", 500, 45000,
                   nguoi_lap="seed")
    a.cart, a.cart_nhap = [], []
    a.user = {"id": 1, "username": "admin", "ten_hien_thi": "Test Admin",
              "vai_tro": "admin", "hoat_dong": 1}
    a._nav_items, a.nav, a._login_dlg = [], {}, None
    a._cur_screen, a._bb_last, a._kh_cache = "home", None, []
    a._build()
    yield a
    try:
        a.con.close()
    except Exception:
        pass
    try:
        a.destroy()
    except Exception:
        pass
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(DB + ext):
            os.remove(DB + ext)


# ---------------------------------------------------------------- 1. to_float
@pytest.mark.parametrize("s,expected", [
    ("15.000", 15000.0), ("100.000", 100000.0),
    ("1.000.000.000", 1000000000.0),
    ("147000.00", 147000.0), ("1.5", 1.5), ("0.5", 0.5),
    ("15,5", 15.5), ("147000,5", 147000.5),
    ("15.099.000", 15099000.0), ("15,099,000", 15099000.0),
    ("1.500,50", 1500.5), ("1,234,567.89", 1234567.89),
    ("", 0.0), (None, 0.0),
])
def test_to_float_dung(s, expected):
    assert mod.to_float(s) == expected


@pytest.mark.parametrize("s", [
    "15,099.000", "15.09.000", "abc", "nan", "inf", "1e5",
    "1.2.3.4", "5.", "-",
])
def test_to_float_chan_loi(s):
    with pytest.raises(ValueError):
        mod.to_float(s)


# ------------------------------------------------- 2. Lịch sử KH không còn lỗi
def test_lichsu_hien_ket_qua(app):
    core.ghi_phieu(app.con, "XUAT", "2026-10-05", "A", 3, 100000,
                   ma_kh="VDH", nguoi_lap="tester")
    app.show("lichsu")
    app.ls_kh.set("Bệnh viện Việt Đức")
    app._tim_lichsu()
    app.update()
    msg = app.ls_msg.cget("text")
    assert "Lỗi" not in msg, msg
    assert "giao dịch" in msg, msg
    txt = _dump(app.ls_box)
    assert "PX-" in txt and "Xuất bán" in txt and "KIM TIÊM 21G" in txt


# ------------------------------------- 3. Biên bản ĐỦ mặt hàng cho giỏ nhiều món
def test_bien_ban_nhieu_mat(app):
    app.show("sale")
    app.update()
    app.v_kh.set("Bệnh viện Việt Đức")
    app.v_ma.set("A")
    app._on_ma_typed(None)
    app.v_sl.set("2")
    app._add_cart()
    app.v_ma.set("B")
    app._on_ma_typed(None)
    app.v_sl.set("3")
    app._add_cart()
    assert len(app.cart) == 2
    app._lap_bien_ban()
    app.update()
    bb = app._bb_last
    assert bb is not None
    mas = {i["ma_vt"] for i in bb["items"]}
    assert mas == {"A", "B"}, f"biên bản thiếu mặt: {mas}"
    assert len(bb["so_phieus"]) == 2
    assert bb["tong"] == 2 * 100000 + 3 * 50000
    # cửa sổ preview hiển thị đủ 2 mặt
    import tkinter as tk
    tops = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
    assert tops, "preview không mở"
    txt = _dump(tops[-1])
    assert "KIM TIÊM 21G" in txt and "BĂNG DÍNH 3M" in txt
    for w in tops:
        w.destroy()


# --------------------------------------- 4. PDF: không TypeError, font Unicode
def test_pdf_bien_ban_unicode(tmp_path):
    set_lang("vi")
    bb = {"so_phieu": "PX-TEST-1", "so_phieus": ["PX-TEST-1"],
          "ngay": 5, "thang": 10, "nam": 2026,
          "ten_kh": "Bệnh viện Việt Đức", "dia_chi": "Hà Nội",
          "ma_so_thue": "010123", "khoa_nhan": "Hồi sức",
          "nguoi_goi": "BS. An", "so_hop_dong": "HD-1",
          "items": [{"ten_vt": "KIM TIÊM 21G", "ma_vt": "A", "dvt": "Cái",
                     "so_luong": 2, "don_gia": 100000, "thanh_tien": 200000}],
          "tong": 200000, "vat": 16000, "vat_pct": 8,
          "tong_cong": 216000,
          "bang_chu": "hai trăm mười sáu nghìn đồng",
          "nguoi_lap": "Test Admin"}
    out = str(tmp_path / "bb.pdf")
    path, loi = mod.pdf_bien_ban(bb, out)
    assert loi is None, loi
    assert path == out and os.path.getsize(out) > 1500
    reg, _ = mod.pdf_fonts()
    assert reg == "Uni", f"font Unicode chưa đăng ký: {reg}"


def test_pdf_baocao(app, tmp_path):
    out = str(tmp_path / "bc.pdf")
    path, loi = mod.pdf_baocao(app.con, "m", 2026, out)
    assert loi is None, loi
    assert os.path.getsize(out) > 1000


# ---------------------------------- 5. Validate đầu vào — không âm thầm sửa số
def test_add_cart_chan_sl_sai(app):
    app.show("sale")
    app.update()
    app.v_ma.set("A")
    app._on_ma_typed(None)
    app.v_sl.set("abc")
    app._add_cart()
    assert app.cart == [], "SL sai vẫn được thêm vào giỏ"
    assert "không hợp lệ" in app.v_gia.cget("text").lower()
    app.v_sl.set("-5")
    app._add_cart()
    assert app.cart == [], "SL âm vẫn được thêm vào giỏ"


def test_add_cart_chan_gia_mo_ho(app):
    app.show("sale")
    app.update()
    app.v_ma.set("A")
    app._on_ma_typed(None)
    app.v_sl.set("1")
    app.v_gia_nhap.delete(0, "end")
    app.v_gia_nhap.insert(0, "15,099.000")   # mơ hồ -> phải chặn
    app._add_cart()
    assert app.cart == [], "giá mơ hồ vẫn được chấp nhận"
    assert "không hợp lệ" in app.v_gia.cget("text").lower()


def test_lap_bien_ban_chan_ngay_sai(app):
    app.show("sale")
    app.update()
    app.v_ma.set("A")
    app._on_ma_typed(None)
    app.v_sl.set("1")
    app._add_cart()
    assert len(app.cart) == 1
    app.v_ngay.delete(0, "end")
    app.v_ngay.insert(0, "05/10/2026")       # sai định dạng
    n0 = app.con.execute(
        "SELECT COUNT(*) FROM phieu_giaodich").fetchone()[0]
    app._lap_bien_ban()
    n1 = app.con.execute(
        "SELECT COUNT(*) FROM phieu_giaodich").fetchone()[0]
    assert n1 == n0, "ngày sai định dạng vẫn được ghi phiếu"
    assert "YYYY-MM-DD" in app.v_gia.cget("text")
    assert len(app.cart) == 1, "giỏ bị xóa dù chưa ghi được phiếu"
    app._clear_cart()


# ---------------------------- 6. Giao hàng theo hóa đơn trước: đúng mặt hàng
def test_giao_theo_hoadon_truoc(app):
    core.xuat_hoadon_truoc(app.con, "2026-10-10", "A", 10, ma_kh="VDH",
                           so_hoa_don="HD200", nguoi_lap="tester")
    n0 = app.con.execute(
        "SELECT COUNT(*) FROM phieu_giaodich WHERE loai_phieu='XUAT'"
    ).fetchone()[0]

    def _add(ma, sl):
        app.v_ma.set(ma)
        app._on_ma_typed(None)
        app.v_sl.set(str(sl))
        app._add_cart()

    # (a) giao B theo hóa đơn của A -> phải CHẶN, không ghi phiếu, giỏ giữ nguyên
    app.show("sale")
    app.update()
    app.v_kh.set("Bệnh viện Việt Đức")
    app.v_hoadon.delete(0, "end")
    app.v_hoadon.insert(0, "HD200")
    _add("B", 1)
    app._lap_bien_ban()
    n1 = app.con.execute(
        "SELECT COUNT(*) FROM phieu_giaodich WHERE loai_phieu='XUAT'"
    ).fetchone()[0]
    assert n1 == n0, "giao mặt B trên hóa đơn của A vẫn lọt!"
    assert "chưa được xuất hóa đơn" in app.v_gia.cget("text")
    assert len(app.cart) == 1
    app._clear_cart()

    # (b) giao A x 5 (<= 10 đã xuất HĐ) -> OK
    _add("A", 5)
    app._lap_bien_ban()
    n2 = app.con.execute(
        "SELECT COUNT(*) FROM phieu_giaodich WHERE loai_phieu='XUAT'"
    ).fetchone()[0]
    assert n2 == n0 + 1

    # (c) giao A x 6 tiếp (5+6 > 10) -> phải CHẶN
    app.v_hoadon.delete(0, "end")
    app.v_hoadon.insert(0, "HD200")
    _add("A", 6)
    app._lap_bien_ban()
    n3 = app.con.execute(
        "SELECT COUNT(*) FROM phieu_giaodich WHERE loai_phieu='XUAT'"
    ).fetchone()[0]
    assert n3 == n2, "giao vượt số đã xuất hóa đơn vẫn lọt!"
    assert "vượt" in app.v_gia.cget("text")
    assert len(app.cart) == 1
    app._clear_cart()
    app.v_hoadon.delete(0, "end")


# ------------------------------------ 7. Đổi ngôn ngữ rebuild TOÀN BỘ giao diện
def test_doi_ngon_ngu_rebuild(app):
    app.show("home")
    app._doi_ngon_ngu("en")
    app.update()
    sidebar_txt = " ".join(b.cget("text") for b in app.nav.values())
    assert "Overview" in sidebar_txt and "Sales" in sidebar_txt, sidebar_txt
    assert app.tb_title.cget("text") == "Overview"   # breadcrumb dịch lazy
    app._doi_ngon_ngu("vi")
    app.update()
    sidebar_txt = " ".join(b.cget("text") for b in app.nav.values())
    assert "Tổng quan" in sidebar_txt


# ------------------------------------------------- 8. DB path không phải _MEIPASS
def test_db_path_dung():
    assert mod.DB_PATH == core.DB_PATH
    assert "_MEI" not in mod.DB_PATH
