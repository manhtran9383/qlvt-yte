"""
test_desktop.py — Kiểm thử app DESKTOP (CustomTkinter) không cần màn hình.

Chạy headless: khởi động app, render từng màn hình, giao dịch qua DOM,
đóng app. Nếu chạy qua hết mà không ném exception thì giao diện đúng.

  python test_desktop.py
"""
import os
import sys
import traceback

os.environ.setdefault("DISPLAY", "")  # headless nếu có
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
import qlvt_core as core

# Tk cần 1 display. Trên Windows desktop session thường có; nếu không,
# dùng Xvfb trên Linux. Ở đây bọc try để báo rõ nguyên nhân nếu fail.
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
    """Tự tạo dữ liệu kiểm thử (không dựa vào dữ liệu mẫu của schema)."""
    con.execute("PRAGMA foreign_keys = OFF")
    for v in [
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
    con.execute("INSERT INTO bang_gia (ma_vt,ma_kh,don_gia) VALUES (?,?,?)",
                ("S53153", "VDH", 231000))
    con.execute(
        "INSERT INTO hop_dong (so_hd,ma_kh,ma_vt,so_luong,don_gia,ngay_ky,"
        "ngay_hieu_luc,ngay_het_han) VALUES (?,?,?,?,?,?,?,?)",
        ("HD-TEST-01", "VDH", "S53153", 1000, 231000, "2026-01-01",
         "2026-01-01", "2026-12-31"))
    con.execute(
        "INSERT INTO cong_viec (noi_dung,ma_kh,khoa,nguoi_lien_he,nguoi_giao,"
        "deadline,muc_do,trang_thai,ghi_chu) VALUES (?,?,?,?,?,?,?,?,?)",
        ("Gọi xác nhận đơn hàng tháng 2", "VDH", "Hồi sức", "BS. An",
         "Manh", "2026-02-01", "Cao", "Đang làm", ""))
    con.commit()


def main():
    import tkinter as tk
    try:
        root = ctk.CTk()
    except Exception as e:
        print(f"Không tạo được CTk: {e}")
        print("(Có thể do môi trường không có display — trên desktop thì có)")
        return 2

    # import app nhưng KHÔNG mainloop
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "app_desktop", os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_desktop.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_td.db")
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(DB + ext):
            os.remove(DB + ext)

    app = mod.App.__new__(mod.App)
    ctk.CTk.__init__(app)
    app.title("test")
    app.geometry("1280x760")
    app.con, app.is_new = core.ensure_db(DB)
    tao_du_lieu_test(app.con)
    app.cart = []
    app.cart_nhap = []
    app.user = {"vai_tro": "admin", "ten_hien_thi": "Test Admin", "hoat_dong": 1}
    app._build()

    print("=" * 64)
    print(" KIỂM THỬ APP DESKTOP (CustomTkinter)")
    print("=" * 64)

    # ---- 1. render tất cả màn hình ----
    print("\n--- Render 8 màn hình ---")
    for key, label in [("home", "Tổng quan"), ("sale", "Bán hàng"), ("in", "Nhập kho"),
                       ("stock", "Tồn kho"), ("cust", "Khách hàng"),
                       ("contract", "Hợp đồng"), ("report", "Báo cáo")]:
        try:
            app.show(key)
            app.update_idletasks()
            app.update()
            check(f"Màn hình '{label}' render không lỗi", True)
        except Exception as e:
            check(f"Màn hình '{label}' render không lỗi", False,
                  f"{type(e).__name__}: {e}")
            traceback.print_exc()

    # ---- 2. nội dung từng màn ----
    print("\n--- Nội dung render ---")
    try:
        app.show("home"); app.update()
        txt = _dump(app.main)
        check("Home có 4 KPI kiểu mockup", all(k in txt for k in
              ["Doanh số tháng", "Giá trị tồn kho", "Cần nhập thêm",
               "Hàng sắp hết / đã hết hạn"]))
        check("Home có đồ thị 24 tháng", "Biến động doanh số 24 tháng gần nhất" in txt)
        check("Home có so sánh tháng trước", "so với tháng trước" in txt)
        check("Home có cảnh báo 'Cảnh báo cần xử lý'", "Cảnh báo cần xử lý" in txt)
        check("Home có 'Top sản phẩm'", "Top sản phẩm" in txt)
        check("Home có 'Top khách hàng'", "Top khách hàng" in txt)
    except Exception as e:
        check("Nội dung Home", False, str(e))

    try:
        app.show("stock"); app.update()
        txt = _dump(app.main)
        check("Tồn kho liệt kê được mã VT", "S53156" in txt or "019-406600" in txt)
        check("Tồn kho có cột Tối thiểu", "Tối thiểu" in txt)
        check("Tồn kho có trạng thái Ổn định/Cần nhập",
              "Ổn định" in txt or "Cần nhập" in txt)
    except Exception as e:
        check("Nội dung Tồn kho", False, str(e))

    try:
        app.show("cust"); app.update()
        txt = _dump(app.main)
        check("Khách hàng có Việt Đức", "Việt Đức" in txt)
        check("Khách hàng có mã số thuế", "Mã số thuế" in txt)
    except Exception as e:
        check("Nội dung Khách hàng", False, str(e))

    # ---- 3. luồng bán hàng qua DOM ----
    print("\n--- Luồng Bán hàng qua giao diện ---")
    try:
        app.show("sale"); app.update()
        app.v_kh.set("Bệnh viện Việt Đức")
        app.v_ma.set("S53153")
        app._on_ma_typed(None)
        app.update()
        check("Gõ mã VT tự hiển thị thông tin giá",
              "231,000" in (app.v_gia.cget("text") or "") or "231000" in (app.v_gia.cget("text") or ""),
              app.v_gia.cget("text"))
        app.v_sl.set("25")
        import unittest.mock as _mock
        with _mock.patch("tkinter.messagebox.askyesno", return_value=True):
            app._add_cart()
        app.update()
        check("Thêm vào giỏ thành công", len(app.cart) == 1, f"({len(app.cart)})")
        check("Giá lấy theo hợp đồng 231.000",
              app.cart and app.cart[0]["don_gia"] == 231000,
              f"({app.cart[0]['don_gia'] if app.cart else '-'})")
        check("Tổng tiền = 25 x 231.000 = 5.775.000",
              "5,775,000" in (app.v_tong.cget("text") or ""),
              app.v_tong.cget("text"))

        app.v_khoa.set("Hồi sức ngoại")
        app.v_nguoi.set("BS. Trần Văn A")
        app.v_hd.set("04-21/BVLKTW-CV")
        app._lap_bien_ban()
        app.update()
        check("Lập biên bản tạo cửa sổ in", True)
        # tìm toplevel bằng cách duyệt children của app (không phải root)
        import tkinter as tk
        tl = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
        check("Cửa sổ biên bản mở ra", len(tl) >= 1, f"({len(tl)})")
        for w in tl:
            w.destroy()

        # DB phải có phiếu
        n = app.con.execute(
            "SELECT COUNT(*) FROM phieu_giaodich WHERE loai_phieu='XUAT'").fetchone()[0]
        check("Phiếu xuất đã ghi vào DB", n >= 1, f"({n})")

        # tồn kho phải giảm
        tk_ = {r["ma_vt"]: r["ton_kho"] for r in core.ton_kho(app.con)}
        check("Tồn kho S53153 đã trừ 25 đơn vị", tk_.get("S53153") == -25,
              f"({tk_.get('S53153')})")
    except Exception as e:
        check("Luồng Bán hàng", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    # ---- 4. luồng nhập kho ----
    print("\n--- Luồng Nhập kho qua giao diện ---")
    try:
        app.show("in"); app.update()
        app.n_ma.set("1104B")
        app._on_nhap_typed(None)
        app.update()
        check("Gõ mã khi nhập tự điền đơn giá",
              app.n_gia.get().replace(",", "").replace(".", "") != "",
              app.n_gia.get())
        app.n_sl.set("30")
        app.n_hsd.set("2026-12-31")
        app.n_lo.set("L2610-A")
        before = app.con.execute(
            "SELECT COUNT(*) FROM phieu_giaodich WHERE loai_phieu='NHAP'").fetchone()[0]
        app._luu_nhap()
        app.update()
        after = app.con.execute(
            "SELECT COUNT(*) FROM phieu_giaodich WHERE loai_phieu='NHAP'").fetchone()[0]
        check("Lưu phiếu nhập thành công", after == before + 1,
              f"({before} -> {after})")
        check("Thông báo thành công hiển thị",
              "Đã lưu" in (app.n_msg.cget("text") or ""),
              app.n_msg.cget("text"))
    except Exception as e:
        check("Luồng Nhập kho", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    # ---- 5. báo cáo 3 tab ----
    # DB seed không có giao dịch → seed vài phiếu xuất để báo cáo có nội dung.
    # (Nếu không, tab vẫn render đúng nhưng hiện "Chưa có dữ liệu".)
    print("\n--- Báo cáo ---")
    try:
        import datetime as _dt
        for i, (ma, kh, sl) in enumerate([
            ("S53153", "VDH", 100), ("S53156", "BVN", 80), ("1104B", "VDH", 50),
            ("S53156", "VDH", 120), ("1104B", "BVN", 60)]):
            ngay = f"2026-0{(i % 3) + 1}-15"
            core.ghi_phieu(app.con, "NHAP", ngay, ma, sl + 500, 1500000,
                           han_su_dung="2027-06-01", nguoi_lap="seed")
            core.ghi_phieu(app.con, "XUAT", ngay, ma, sl, 1500000,
                           ma_kh=kh, khoa_nhan="Hồi sức ngoại", nguoi_lap="seed")
        app.con.commit()

        app.show("report"); app.update()
        for tab in ["Tháng", "Quý", "Thị phần"]:
            app.r_tab.set(tab)
            app._draw_report(tab)
            app.update()
            txt = _dump(app.r_box)
            check(f"Tab '{tab}' render có nội dung", len(txt.strip()) > 20,
                  f"({len(txt.strip())} ký tự)")
    except Exception as e:
        check("Báo cáo", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    # ---- 6. hộp thoại lỗi: phiếu trống ----
    print("\n--- Kiểm tra lỗi ---")
    try:
        app.show("sale"); app.update()
        app._clear_cart()
        app.update()
        n_before = app.con.execute("SELECT COUNT(*) FROM phieu_giaodich").fetchone()[0]
        app.cart = []
        app._lap_bien_ban()
        n_after = app.con.execute("SELECT COUNT(*) FROM phieu_giaodich").fetchone()[0]
        check("Không lập biên bản khi phiếu trống", n_after == n_before,
              f"({n_before} -> {n_after})")
    except Exception as e:
        check("Kiểm tra phiếu trống", False, str(e))

    try:
        app.con.close()
    except Exception:
        pass
    try:
        app.destroy()
    except Exception:
        pass
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(DB + ext):
            os.remove(DB + ext)

    print()
    print("=" * 64)
    print(f" KẾT QUẢ: {passed} PASS · {failed} FAIL")
    print("=" * 64)
    return 0 if failed == 0 else 1


def _dump(widget):
    """Thu thập toàn bộ text trong cây widget."""
    out = []
    def walk(w):
        for attr in ("text", "value"):
            try:
                v = getattr(w, "cget")(attr)
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


if __name__ == "__main__":
    sys.exit(main())
