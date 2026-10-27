# -*- coding: utf-8 -*-
"""test_core_v3_fixes.py — Regression tests cho các patch qlvt_core.py (V3).

Mọi bug core nêu trong review V1/V2 đều có test ở đây:
  âm kho, XUAT số âm, hóa đơn xuyên mặt hàng, xoa_khachhang thiếu commit,
  backup copy file sống, VAT hardcode, PDF font Helvetica, prefix PX/HĐ,
  định giá tồn kho lệch view, luu_hop_dong không validate.
Chạy: python3 -m pytest test_core_v3_fixes.py -v
"""
import os
import sqlite3
import sys
import uuid

import pytest

SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
DB = os.path.join(SRC, f"_tcv3_{uuid.uuid4().hex[:6]}.db")
os.environ["QLVT_DB"] = DB

import qlvt_core as core          # noqa: E402
from i18n import get_lang         # noqa: E402


@pytest.fixture(scope="module")
def con():
    c, _ = core.ensure_db(DB)
    core.ensure_auth_schema(c)
    c.execute("INSERT INTO dm_vattu (ma_vt,ten_vt,dvt,don_gia) "
              "VALUES ('A','Kim tiêm','Cái',100000)")
    c.execute("INSERT INTO dm_vattu (ma_vt,ten_vt,dvt,don_gia) "
              "VALUES ('B','Băng dính','Cuộn',50000)")
    c.execute("INSERT INTO dm_khachhang (ma_kh,ten_kh) VALUES ('KH1','BV A')")
    c.commit()
    yield c
    c.close()
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(DB + ext):
            os.remove(DB + ext)


# ------------------------------------------------ 1. Âm kho bị chặn mặc định
def test_chan_xuat_vuot_ton(con):
    with pytest.raises(ValueError, match="Tồn kho"):
        core.ghi_phieu(con, "XUAT", "2026-10-01", "A", 10, 100000,
                       ma_kh="KH1")


def test_cho_am_kho_explicit(con):
    # Người dùng xác nhận -> cờ tường minh -> được ghi, tồn âm có chủ đích
    sp = core.ghi_phieu(con, "XUAT", "2026-10-01", "A", 10, 100000,
                        ma_kh="KH1", cho_am_kho=True)
    assert sp.startswith("PX-")
    tk = {r["ma_vt"]: r["ton_kho"] for r in core.ton_kho(con)}
    assert tk["A"] == -10


def test_xuat_trong_ton_ok(con):
    core.ghi_phieu(con, "NHAP", "2026-10-02", "B", 100, 45000)
    sp = core.ghi_phieu(con, "XUAT", "2026-10-03", "B", 100, 50000,
                        ma_kh="KH1")
    assert sp.startswith("PX-")
    tk = {r["ma_vt"]: r["ton_kho"] for r in core.ton_kho(con)}
    assert tk["B"] == 0


# ------------------------------------------- 2. Số lượng <= 0 bị chặn mọi loại
@pytest.mark.parametrize("loai,sl", [
    ("NHAP", -5), ("XUAT", -500), ("NHAP", 0), ("KYGUI", -1),
])
def test_chan_so_luong_khong_duong(con, loai, sl):
    with pytest.raises(ValueError):
        core.ghi_phieu(con, loai, "2026-10-04", "A", sl, 100000,
                       ma_kh="KH1", cho_am_kho=True)


def test_xuat_am_khong_lam_tang_ton(con):
    """Bug V1: XUAT -500 được nhận và tồn kho TĂNG ngược. Phải chặn."""
    tk0 = {r["ma_vt"]: r["ton_kho"] for r in core.ton_kho(con)}["A"]
    with pytest.raises(ValueError):
        core.ghi_phieu(con, "XUAT", "2026-10-04", "A", -500, 100000,
                       ma_kh="KH1")
    tk1 = {r["ma_vt"]: r["ton_kho"] for r in core.ton_kho(con)}["A"]
    assert tk1 == tk0


# --------------------------------- 3. Hóa đơn trước: đúng (so_hoa_don, ma_vt)
def test_hoadon_truoc_dung_mat_hang(con):
    core.ghi_phieu(con, "NHAP", "2026-10-05", "A", 1000, 90000)
    # B phải đủ tồn để phép thử chạm đúng check HÓA ĐƠN (check tồn chạy trước)
    core.ghi_phieu(con, "NHAP", "2026-10-05", "B", 500, 45000)
    core.xuat_hoadon_truoc(con, "2026-10-06", "A", 10, ma_kh="KH1",
                           so_hoa_don="HD100", nguoi_lap="t")
    # Bug V1: giao B (không có dòng hóa đơn nào) trên HD100 của A -> lọt.
    with pytest.raises(ValueError, match="vượt"):
        core.ghi_phieu(con, "XUAT", "2026-10-07", "B", 10, 50000,
                       ma_kh="KH1", so_hoa_don="HD100")
    # Giao A đúng hạn mức: OK
    core.ghi_phieu(con, "XUAT", "2026-10-07", "A", 10, 100000,
                   ma_kh="KH1", so_hoa_don="HD100")
    # Giao A vượt hạn mức: chặn
    with pytest.raises(ValueError, match="vượt"):
        core.ghi_phieu(con, "XUAT", "2026-10-08", "A", 1, 100000,
                       ma_kh="KH1", so_hoa_don="HD100")


# ------------------------------------------ 4. xoa_khachhang có commit thật
def test_xoa_khachhang_commit(con):
    con.execute("INSERT INTO dm_khachhang (ma_kh,ten_kh) "
                "VALUES ('KHX','BV X')")
    con.commit()
    core.xoa_khachhang(con, "KHX")
    con2 = sqlite3.connect(DB)
    try:
        n = con2.execute("SELECT COUNT(*) FROM dm_khachhang "
                         "WHERE ma_kh='KHX'").fetchone()[0]
    finally:
        con2.close()
    assert n == 0, "xóa KH chưa được commit — kết nối khác vẫn thấy"


# --------------------------------------------------- 5. backup_db nhất quán
def test_backup_db_mở_được_và_đủ_dữ_liệu(con, tmp_path):
    n_goc = con.execute("SELECT COUNT(*) FROM phieu_giaodich").fetchone()[0]
    path, mb = core.backup_db(con, backup_dir=str(tmp_path))
    assert path and os.path.exists(path) and mb > 0
    bc = sqlite3.connect(path)
    try:
        n_copy = bc.execute(
            "SELECT COUNT(*) FROM phieu_giaodich").fetchone()[0]
        assert bc.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        bc.close()
    assert n_copy == n_goc


# ------------------------------------------------------ 6. VAT tham số hóa
def test_bien_ban_vat_pct(con):
    sp = core.ghi_phieu(con, "XUAT", "2026-10-09", "A", 5, 100000,
                        ma_kh="KH1", cho_am_kho=True)
    bb8 = core.bien_ban(con, sp)
    assert abs(bb8["vat"] - bb8["tong"] * 0.08) < 0.01
    assert bb8["vat_pct"] == 8.0
    bb5 = core.bien_ban(con, sp, vat_pct=5)
    assert abs(bb5["vat"] - bb5["tong"] * 0.05) < 0.01
    assert abs(bb5["tong_cong"] - (bb5["tong"] + bb5["vat"])) < 0.01


# --------------------------------------- 7. PDF core: font Unicode + so_phieu
def test_xuat_pdf_theo_phieu_unicode(con, tmp_path):
    sp1 = core.ghi_phieu(con, "XUAT", "2026-10-10", "A", 2, 100000,
                         ma_kh="KH1", cho_am_kho=True)
    core.ghi_phieu(con, "XUAT", "2026-10-10", "B", 3, 50000,
                   ma_kh="KH1", cho_am_kho=True)
    out = str(tmp_path / "bb.pdf")
    path, loi = core.xuat_pdf(con, out, so_phieu=sp1)
    assert loi is None, loi
    assert path == out and os.path.getsize(out) > 1500
    reg, bold = core.dang_ky_font_pdf()
    if os.path.exists("C:/Windows/Fonts/arial.ttf") or \
            os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        assert reg == "Uni" and bold == "Uni-Bold"


def test_xuat_baocao_pdf_3_loai(con, tmp_path):
    for loai in ("m", "q", "s"):
        out = str(tmp_path / f"bc_{loai}.pdf")
        path, loi = core.xuat_baocao_pdf(con, loai, 2026, out)
        assert loi is None, loi
        assert os.path.getsize(path) > 800


def test_lang_param_khong_lam_ro_lang_global(con, tmp_path):
    lang_truoc = get_lang()
    out = str(tmp_path / "bc_en.pdf")
    path, loi = core.xuat_baocao_pdf(con, "m", 2026, out, lang="en")
    assert loi is None, loi
    assert get_lang() == lang_truoc, "lang param làm rò rỉ trạng thái global"


# -------------------------------------------- 8. Prefix riêng cho HĐ trước
def test_prefix_xuat_hoadon_truoc(con):
    s = core.next_so_phieu(con, "XUAT_HOADON_TRUOC")
    assert s.startswith(f"XH-{core.date.today().year}-"), s
    sp = core.xuat_hoadon_truoc(con, "2026-10-11", "B", 5, ma_kh="KH1",
                                so_hoa_don="HD200", nguoi_lap="t")
    assert sp.startswith("XH-"), sp


# ------------------------------------------------- 9. Alias đúng chính tả
def test_phan_quyen_alias():
    assert core.phan_quyen is core.phan_quyyen
    assert core.phan_quyen("admin", "xuat") is True
    assert core.phan_quyen("nhanvien", "xuat") is False


# ------------------------------------- 10. luu_hop_dong validate + audit
def test_luu_hop_dong_validate(con):
    with pytest.raises(ValueError):
        core.luu_hop_dong(con, "HD1", "KH1", "A", 0, 100000)
    with pytest.raises(ValueError):
        core.luu_hop_dong(con, "HD1", "KH_KHONG_TON_TAI", "A", 10, 100000)
    n_log0 = con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    core.luu_hop_dong(con, "HD1", "KH1", "A", 10, 100000,
                      ngay_ky="2026-01-01", nguoi_thao_tac="tester")
    row = con.execute("SELECT * FROM hop_dong WHERE so_hd='HD1'").fetchone()
    assert row and row["so_luong"] == 10
    n_log1 = con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert n_log1 == n_log0 + 1, "lưu hợp đồng không ghi audit log"


# ---------------------------- 11. Định giá tồn kho nhất quán với view v_tonkho
def test_ton_kho_nhat_quan_voi_view(con):
    fn = {r["ma_vt"]: r["gia_tri_ton"] for r in core.ton_kho(con)}
    view = {r["ma_vt"]: r["gia_tri_ton"]
            for r in con.execute("SELECT * FROM v_tonkho")}
    for ma in fn:
        assert abs((fn[ma] or 0) - (view.get(ma) or 0)) < 0.01, \
            f"{ma}: hàm ton_kho() lệch view v_tonkho"
