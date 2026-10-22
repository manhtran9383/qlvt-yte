"""
test_core.py — Kiểm thử lõi nghiệp vụ qlvt_core.

Cả 2 phương án (Desktop & Web) đều dùng lõi này. Nếu test này PASS thì
nghiệp vụ đã đúng, giao diện chỉ việc gọi.

Test TỰ CHẨN dữ liệu (tao_du_lieu_test) nên không phụ thuộc bất kỳ dữ liệu mẫu
nào trong schema.sql — DB gốc đã xóa toàn bộ danh mục.

Chạy:  python test_core.py
"""
import os
import sys
import uuid
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qlvt_core as core

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"_test_{uuid.uuid4().hex[:6]}.db")

passed = failed = 0


def check(label, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {label}")
    else:
        failed += 1
        print(f"  FAIL {label} {extra}")


# ---------------------------------------------------------------- fixtures
def tao_du_lieu_test(con):
    """Tự tạo dữ liệu kiểm thử. Không dựa vào dữ liệu mẫu của schema."""
    # Không tắt FK — insert theo thứ tự cha trước con thì OK
    for v in [
        # ma_vt, ten_vt, dvt, hang_sx, nuoc_sx, nhom_vt, so_dk, don_gia, ton_toi_thieu
        ("S53156", "KIM TIÊM SAFETY 21G", "Cái", "BD", "Việt Nam",
         "Dụng cụ y tế", "DK001", 147000, 0),
        ("S53153", "BĂNG DÍNH Y TẾ 3M", "Cuộn", "3M", "Mỹ",
         "Vật tư tiêu hao", "DK002", 231000, 0),
        ("1104B", "DUNG DỊCH HOẠT TÍNH", "Chai", "Fresenius", "Đức",
         "Dung dịch", "DK003", 15099000, 0),
    ]:
        con.execute(
            "INSERT INTO dm_vattu (ma_vt,ten_vt,dvt,hang_sx,nuoc_sx,nhom_vt,"
            "so_dk,don_gia,ton_toi_thieu) VALUES (?,?,?,?,?,?,?,?,?)", v)

    con.execute(
        "INSERT INTO dm_khachhang (ma_kh,ten_kh,dia_chi,ma_so_thue,khu_vuc) "
        "VALUES (?,?,?,?,?)",
        ("VDH", "Bệnh viện Việt Đức", "764 Giải Phóng, Hà Nội",
         "0101234567", "Miền Bắc"))
    con.execute(
        "INSERT INTO dm_khachhang (ma_kh,ten_kh,dia_chi,ma_so_thue,khu_vuc) "
        "VALUES (?,?,?,?,?)",
        ("BVN", "Bệnh viện Bạch Mai", "78 Giải Phóng, Hà Nội",
         "0101234568", "Miền Bắc"))

    # Bảng giá riêng cho Việt Đức (thay giá kế hoạch)
    con.execute("INSERT INTO bang_gia (ma_vt,ma_kh,don_gia) VALUES (?,?,?)",
                ("S53153", "VDH", 231000))

    # Hợp đồng thầu
    con.execute(
        "INSERT INTO hop_dong (so_hd,ma_kh,ma_vt,so_luong,don_gia,ngay_ky,"
        "ngay_hieu_luc,ngay_het_han) VALUES (?,?,?,?,?,?,?,?)",
        ("HD-TEST-01", "VDH", "S53153", 1000, 231000, "2026-01-01",
         "2026-01-01", "2026-12-31"))

    # Công việc
    con.execute(
        "INSERT INTO cong_viec (noi_dung,ma_kh,khoa,nguoi_lien_he,nguoi_giao,"
        "deadline,muc_do,trang_thai,ghi_chu) VALUES (?,?,?,?,?,?,?,?,?)",
        ("Gọi xác nhận đơn hàng tháng 2", "VDH", "Hồi sức", "BS. An",
         "Manh", "2026-02-01", "Cao", "Đang làm", ""))
    con.commit()


def main():
    print("=" * 62)
    print(" KIỂM THỬ LÕI NGHIỆP VỤ qlvt_core")
    print("=" * 62)

    # ---------- 1. Khởi tạo ----------
    con, is_new = core.ensure_db(DB)
    check("Tạo DB mới + cài schema", is_new)
    check("integrity_check = ok",
          con.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
    tao_du_lieu_test(con)
    for t, n in [("dm_vattu", 3), ("dm_khachhang", 2), ("bang_gia", 1),
                 ("hop_dong", 1), ("cong_viec", 1)]:
        got = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        check(f"{t} có {n} bản ghi", got == n, f"(thực tế {got})")

    # ---------- 2. Sinh số phiếu ----------
    s1 = core.next_so_phieu(con, "XUAT")
    check("Số phiếu XUAT có dạng PX-năm-0001",
          s1.startswith(f"PX-{core.date.today().year}-"), s1)

    # ---------- 3. Ghi nhập kho ----------
    pn = core.ghi_phieu(con, "NHAP", "2026-01-10", "S53156", 500, 147000,
                        so_lo="L2601", han_su_dung="2027-01-10",
                        nguoi_lap="Manh", ghi_chu="Nhập đợt 1")
    check("Ghi phiếu NHập", pn.startswith("PN-"), pn)

    # ---------- 4. Ghi xuất hàng ----------
    px = core.ghi_phieu(con, "XUAT", "2026-01-15", "S53156", 200, 147000,
                        ma_kh="VDH", khoa_nhan="Hồi sức ngoại", nguoi_goi="BS. A",
                        nguoi_lap="Manh")
    check("Ghi phiếu XUất", px.startswith("PX-"), px)

    # ---------- 5. Tồn kho = nhập - xuất ----------
    tk = {r["ma_vt"]: r["ton_kho"] for r in core.ton_kho(con)}
    check("Tồn kho S53156 = 500 - 200 = 300", tk.get("S53156") == 300,
          f"(thực tế {tk.get('S53156')})")

    # ---------- 6. Giá bán theo bệnh viện ----------
    g_vdh, src_vdh = core.gia_ban(con, "S53153", "VDH")
    check("Giá S53153 cho Việt Đức = 231.000 (theo bảng giá/hợp đồng)",
          g_vdh == 231000, f"(thực tế {g_vdh}, nguồn={src_vdh})")
    g_x, src_x = core.gia_ban(con, "S53156", "VDH")
    check("Giá S53156 không có trong bảng giá → fallback giá kế hoạch 147.000",
          g_x == 147000 and src_x == "giá kế hoạch", f"(thực tế {g_x}, {src_x})")

    # ---------- 7. Cảnh báo ----------
    # đặt tồn tối thiểu cao để chắc chắn có cảnh báo
    con.execute("UPDATE dm_vattu SET ton_toi_thieu = 1000 WHERE ma_vt='S53156'")
    con.commit()
    cb = core.canh_bao(con)
    check("Có cảnh báo cần nhập thêm cho S53156",
          any(c["ma_vt"] == "S53156" for c in cb["can_nhap"]),
          f"({len(cb['can_nhap'])} cảnh báo)")

    # ---------- 8. Cảnh báo hết hạn ----------
    core.ghi_phieu(con, "NHAP", "2025-01-01", "1104B", 10, 15099000,
                   so_lo="L-EXP", han_su_dung="2024-06-01", nguoi_lap="Manh")
    cb2 = core.canh_bao(con)
    check("Có cảnh báo hết hạn cho 1104B",
          any(c["ma_vt"] == "1104B" for c in cb2["het_han"]),
          f"({len(cb2['het_han'])} mặt hàng hết hạn)")

    # ---------- 9. Báo cáo ----------
    ds_t = core.doanh_so_thang(con, 2026)
    check("Doanh số tháng 1/2026 = 200 x 147.000 = 29.400.000",
          any(r["thang"] == "01" and abs(r["doanh_so"] - 29400000) < 1 for r in ds_t),
          f"({[(r['thang'], r['doanh_so']) for r in ds_t]})")
    ds_k = core.doanh_so_theo_khach(con, 2026)
    check("Doanh số theo khách có Việt Đức",
          any("Việt Đức" in (r["ten_kh"] or "") for r in ds_k))
    ts = core.thi_phan(con, 2026)
    check("Tỷ lệ thị phần tổng = 100%",
          abs(sum(t["ti_le"] for t in ts) - 100) < 0.01,
          f"(tổng {sum(t['ti_le'] for t in ts):.4f})")
    td = core.tien_do_hop_dong(con)
    check("Tiến độ hợp đồng trả về 1 dòng (khớp hợp đồng fixture)", len(td) == 1,
          f"({len(td)})")

    # ---------- 10. doanh_so_thang_gan_nhat (24 tháng gần nhất) ----------
    # Test DB chỉ có dữ liệu tháng 1/2026 → ds24 sẽ có 24 tháng (11/2024..01/2026)
    # hầu hết = 0, chỉ 01/2026 = 29.4M
    ds24 = core.doanh_so_thang_gan_nhat(con, 24)
    check("doanh_so_thang_gan_nhat trả về 24 tháng", len(ds24) == 24, f"({len(ds24)})")
    check("Kết thúc tại 01/2026 (tháng có dữ liệu)",
          ds24[-1]["nam"] == 2026 and ds24[-1]["thang"] == 1)
    check("Doanh số 01/2026 = 29.4M", ds24[-1]["doanh_so"] == 29400000)
    check("Không có tháng nào giá trị âm", all((r["doanh_so"] or 0) >= 0 for r in ds24))
    check("Tổng 24 tháng = 29.4M", sum(r["doanh_so"] for r in ds24) == 29400000)
    # n > số tháng thực → vẫn trả đủ n tháng (padding 0)
    ds_all = core.doanh_so_thang_gan_nhat(con, 100)
    check("n=100 → trả 100 tháng (padding 0 trước dữ liệu)", len(ds_all) == 100)

    # ---------- 11. Số tiền bằng chữ ----------
    cases = [
        (0, "không đồng"),
        (5000, "năm nghìn đồng"),
        (147000, "một trăm bốn mươi bảy nghìn đồng"),
        (29400000, "hai mươi chín triệu bốn trăm nghìn đồng"),
        (1234567, "một triệu hai trăm ba mươi bốn nghìn năm trăm sáu mươi bảy đồng"),
    ]
    for so, mong_doi in cases:
        got = core.so_tien_bang_chu(so)
        check(f"Số tiền bằng chữ: {so:,} -> '{mong_doi}'", got == mong_doi, f"(ra '{got}')")

    # ---------- 12. Biên bản giao hàng ----------
    bb = core.bien_ban(con, px)
    check("Biên bản lấy được phiếu", bb is not None)
    if bb is not None:
        check("Biên bản đúng tên khách hàng", "Việt Đức" in (bb["ten_kh"] or ""), bb["ten_kh"])
        check("Biên bản đúng khoa nhận", bb["khoa_nhan"] == "Hồi sức ngoại")
        check("Biên bản tổng = 29.400.000", abs(bb["tong"] - 29400000) < 1, f"({bb['tong']})")
        check("Biên bản VAT 8% = 2.352.000", abs(bb["vat"] - 2352000) < 1, f"({bb['vat']})")
        check("Biên bản tổng cộng = 31.752.000", abs(bb["tong_cong"] - 31752000) < 1)
        check("Biên bản có số tiền bằng chữ",
              bb["bang_chu"].endswith("đồng") and len(bb["bang_chu"]) > 10, bb["bang_chu"])

    # ---------- 13. Danh mục & tìm kiếm ----------
    check("Tìm kiếm vật tư theo tên 'kim' ra >0 kết quả",
          len(core.ds_vattu(con, "kim")) > 0)
    check("Danh sách khách hàng = 2", len(core.ds_khachhang(con)) == 2)
    dp = core.ds_phieu(con, loai="XUAT")
    check("Lịch sử phiếu xuất có dữ liệu", len(dp) > 0, f"({len(dp)})")

    # ---------- 14. Audit log ----------
    # 3 phiếu ghi thành công (2 NHAP + 1 XUAT). 2 phiếu lỗi bị chặn TRƯỚC khi
    # vào bảng giao dịch nên không được log — đó đúng là hành vi mong muốn.
    n_log = con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    check("Audit log ghi đúng 3 thao tác thành công", n_log == 3, f"(thực tế {n_log})")
    check("Log không ghi nhận thao tác bị chặn",
          not con.execute(
              "SELECT 1 FROM audit_log WHERE chi_tiet LIKE '%KHAC%' OR chi_tiet LIKE '%x0%'"
          ).fetchone())

    # ---------- 15. Kiểm tra lỗi (validation) ----------
    try:
        core.ghi_phieu(con, "XUAT", "2026-01-20", "S53156", 0, 147000, ma_kh="VDH")
        check("Chặn số lượng = 0", False, "(không báo lỗi!)")
    except ValueError:
        check("Chặn số lượng = 0", True)

    try:
        core.ghi_phieu(con, "XUAT", "2026-01-20", "", 5, 147000, ma_kh="VDH")
        check("Chặn mã vật tư rỗng", False, "(không báo lỗi!)")
    except ValueError:
        check("Chặn mã vật tư rỗng", True)

    # khóa ngoại: mã khách hàng không tồn tại
    try:
        con.execute("INSERT INTO phieu_giaodich (so_phieu,loai_phieu,ngay_phieu,ma_vt,so_luong,don_gia,ma_kh) VALUES (?,?,?,?,?,?,?)",
                    ("PX-FK-1", "XUAT", "2026-01-20", "S53156", 5, 147000, "KHAC"))
        con.rollback()
        check("Chặn khách hàng không tồn tại (khóa ngoại)", False, "(đã ghi được!)")
    except sqlite3.IntegrityError:
        con.rollback()
        check("Chặn khách hàng không tồn tại (khóa ngoại)", True)

    con.close()
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(DB + ext):
            os.remove(DB + ext)

    print()
    print("=" * 62)
    print(f" KẾT QUẢ: {passed} PASS · {failed} FAIL")
    print("=" * 62)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
