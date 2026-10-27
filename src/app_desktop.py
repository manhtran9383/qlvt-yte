"""
app_desktop.py — Giao diện DESKTOP (CustomTkinter) cho QLVT Y tế.

Chạy:  python app_desktop.py

Bản viết lại (V3) — các thay đổi chính so với bản cũ:
  1. DB path: dùng core.DB_PATH (core._db_dir đã xử lý đúng bản frozen:
     cạnh .exe, fallback %LOCALAPPDATA%). KHÔNG đặt DB trong _MEIPASS
     (thư mục tạm bị xoá khi thoát -> mất dữ liệu).
  2. Theme: load neutral_theme.json trong try/except, có fallback — thiếu
     file (spec quên đóng gói) không còn làm exe crash lúc khởi động.
  3. to_float(): parse tất định, raise ValueError khi mơ hồ — không âm thầm
     nhân/chia 1000 hay trả 0. Mọi call-site đều bắt lỗi và báo đỏ.
  4. PDF (biên bản + báo cáo) render ở tầng GUI với font Unicode đăng ký
     qua reportlab (Arial/Segoe/DejaVu) — chữ tiếng Việt không còn lỗi glyph;
     không gọi core.xuat_pdf/xuat_baocao_pdf (chữ ký 2 bên từng lệch nhau).
  5. Biên bản giao hàng gộp ĐỦ các phiếu của giỏ hàng nhiều mặt (bản cũ
     chỉ in phiếu cuối -> thiếu hàng trên chứng từ).
  6. Màn Lịch sử KH đọc đúng tên cột của view (loai_phieu/ngay_phieu).
  7. Không còn "âm thầm đổi input": SL <= 0 / sai định dạng / ngày sai ->
     báo lỗi đỏ, không tự đổi thành 1, không ghi giá 0.
  8. Đổi ngôn ngữ rebuild TOÀN BỘ UI (bản cũ chỉ rebuild màn home -> sidebar
     nửa nạc nửa mỡ); ngôn ngữ lưu trong settings.json cạnh DB.
  9. Kiểm tra "giao không vượt hóa đơn" theo đúng (so_hoa_don, ma_vt)
     qua view v_xuat_hoadon_truoc — bản core cũ cộng gộp xuyên mặt hàng.
 10. Xóa code chết: self._token/xoa_session (sessions không dùng ở desktop),
     SCREEN_INFO dịch lúc import (nay dịch lazy).

Tương thích ngược: giữ nguyên tên widget/hàm mà test_desktop.py dùng
(v_kh, v_ma, v_sl, v_gia, v_tong, n_ma, n_gia, n_sl, n_msg, r_tab, r_nam,
r_box, _add_cart, _lap_bien_ban, _luu_nhap, _draw_report, show, _build...).
"""
import json
import os
import sys
import time
import traceback
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from datetime import date, datetime

import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qlvt_core as core
from i18n import t, tf, set_lang, get_lang

# ============================================================
# ĐƯỜNG DẪN & TÀI NGUYÊN
# ============================================================

def _resource_dir():
    """Thư mục tài nguyên (theme): _MEIPASS khi frozen, cạnh file khi chạy source."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _load_theme():
    """Nạp theme trung tính; thiếu file thì dùng theme mặc định, KHÔNG crash.

    (Bản cũ gọi thẳng ThemeManager.load_theme ở cấp module -> exe onefile
    chết ngay khi khởi động nếu spec thiếu neutral_theme.json trong datas.)
    """
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("green")
    for base in (_resource_dir(),
                 os.path.dirname(os.path.abspath(sys.executable))
                 if getattr(sys, "frozen", False) else ""):
        if not base:
            continue
        p = os.path.join(base, "neutral_theme.json")
        if os.path.exists(p):
            try:
                ctk.ThemeManager.load_theme(p)
                return True
            except Exception:
                continue
    return False


_THEME_OK = _load_theme()

# DB: để core quyết định (QLVT_DB env > cạnh exe/src > %LOCALAPPDATA%).
# Core._db_dir() đã xử lý đúng mọi chế độ frozen — GUI KHÔNG tự tính nữa.
DB_PATH = core.DB_PATH

# Settings nhỏ (ngôn ngữ) cạnh DB — sống sót qua các lần chạy, kể cả bản exe.
SETTINGS_PATH = os.path.join(os.path.dirname(DB_PATH) or ".", "settings.json")


def _load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_settings(d):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def _load_lang():
    lang = str(_load_settings().get("lang", "vi")).lower()
    set_lang(lang if lang in ("vi", "en") else "vi")


_load_lang()

# ============================================================
# HẰNG & HÀM TIỆN ÍCH
# ============================================================

TEN_VAI_TRO = {
    "admin": "Quản trị",
    "kinhdoanh": "Kinh doanh",
    "ketoan": "Kế toán",
    "kho": "Kho",
    "nhanvien": "Nhân viên",
}

LOAI_PHIEU_LABEL = {
    "NHAP": "Nhập kho", "XUAT": "Xuất bán", "KYGUI": "Ký gửi",
    "XUAT_KYGUI": "Xuất ký gửi", "XUAT_HOADON_TRUOC": "HĐ trước",
}

# màu
C_BG = "#f4f6f9"
C_CARD = "#ffffff"
C_BRAND = "#0e7c86"
C_OK = "#1a9c5b"
C_WARN = "#c77a00"
C_BAD = "#d1462f"
C_INK = "#0f2233"
C_MUT = "#5a6b7d"


def ten_vai_tro(v):
    return t(TEN_VAI_TRO.get(v, v))


def nguoi_lap_cua(app):
    """Tên người lập phiếu. Không xác định được -> 'Hệ thống' (đúng docstring)."""
    u = getattr(app, "user", None)
    if u:
        return u.get("ten_hien_thi") or u.get("username") or t("Hệ thống")
    return t("Hệ thống")


def fmt(n):
    """Số -> chuỗi nhóm nghìn, không thập phân (hiển thị)."""
    try:
        return f"{float(n or 0):,.0f}"
    except (TypeError, ValueError):
        return str(n)


def money(n):
    """Số tiền -> chuỗi gọn: tỷ / tr / đồng."""
    n = float(n or 0)
    if abs(n) >= 1e9:
        return tf("{:,.2f} tỷ", n / 1e9)
    if abs(n) >= 1e6:
        return f"{n / 1e6:,.1f} tr"
    return f"{n:,.0f}"


_ASCII_DIGITS = "0123456789"


def _groups_ok(head, sep):
    """head dạng N(ddd)(ddd)...: nhóm đầu 1-3 chữ số, các nhóm sau đúng 3 chữ số."""
    parts = head.split(sep)
    if len(parts) < 2:
        return False
    if not (1 <= len(parts[0]) <= 3):
        return False
    if any(c not in _ASCII_DIGITS for c in parts[0]):
        return False
    return all(len(g) == 3 and all(c in _ASCII_DIGITS for c in g)
               for g in parts[1:])


def to_float(s):
    """Parse số nhập từ bàn phím. Trả về float; ValueError nếu không xác định được.

    Quy tắc TẤT ĐỊNH (VND: 0-2 chữ số thập phân):
      None / "" / khoảng trắng          -> 0.0   (quy ước "chưa nhập")
      int/float (VD don_gia từ DB)      -> float(s)
      "15099000", "15 099 000"          -> 15099000.0  (space = phân cách nghìn)
      "15.000" / "15,099,000"           -> hàng nghìn khi đuôi SAU dấu tách
      "15.099.000" / "1.000.000.000"       cuối có ĐÚNG 3 chữ số và các nhóm
                                           đúng chuẩn 3 chữ số
      "1.5" / "0.5" / "15,5" / "147000.50" -> thập phân (đuôi 1-2 chữ số;
                                              chấm HOẶC phẩy đều nhận)
      "1.500,50" / "1,234,567.89"       -> hỗn hợp: dấu CUỐI = thập phân,
                                           dấu kia = nghìn (nhóm phải đúng 3)
      "-15.099.000"                     -> -15099000.0 (dấu được nhận)
      "15,099.000" (mơ hồ), "15.09.000" (sai nhóm), "abc", "nan", "inf",
      "1e5", "1.2.3.4", "5."            -> raise ValueError — KHÔNG đoán,
                                           KHÔNG âm thầm trả 0.

    Call-site BẮT BUỘC bắt ValueError và báo lỗi cho người dùng.
    """
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        s = str(s)
    s = s.strip().replace("\u00a0", " ")
    if s == "":
        return 0.0

    sign = 1.0
    if s[0] in "+-":
        sign = -1.0 if s[0] == "-" else 1.0
        s = s[1:]
    if not s:
        raise ValueError("Số không hợp lệ: chỉ có dấu '-'/'+'")

    # khoảng trắng chỉ hợp lệ khi nhóm đúng 3 chữ số ("15 099 000")
    if " " in s:
        if not _groups_ok(s, " "):
            raise ValueError(f"Phân cách khoảng trắng sai nhóm 3 chữ số: {s!r}")
        s = s.replace(" ", "")

    if any(c not in _ASCII_DIGITS and c not in ".," for c in s):
        raise ValueError(f"Ký tự không hợp lệ trong số: {s!r}")

    last_sep = max(s.rfind("."), s.rfind(","))
    if last_sep == -1:
        return sign * float(s)

    sep = s[last_sep]
    other = "," if sep == "." else "."
    head, tail = s[:last_sep], s[last_sep + 1:]
    if not tail or any(c not in _ASCII_DIGITS for c in tail):
        raise ValueError(f"Số không hợp lệ: {s!r}")

    if len(tail) in (1, 2):                       # dấu cuối = THẬP PHÂN
        if other in head:                          # phần nghìn = dấu còn lại
            if not _groups_ok(head, other):
                raise ValueError(f"Nhóm hàng nghìn không hợp lệ: {s!r}")
            head = head.replace(other, "")
        if head == "":
            head = "0"
        if any(c not in _ASCII_DIGITS for c in head):
            raise ValueError(f"Số mơ hồ (một dấu dùng 2 vai trò): {s!r}")
        return sign * float(head + "." + tail)

    if len(tail) == 3:                            # ứng viên HÀNG NGHÌN
        if other not in s and _groups_ok(s, sep):
            return sign * float(s.replace(sep, ""))
        raise ValueError(f"Số mơ hồ/không hợp lệ (đuôi 3 chữ số): {s!r}")

    raise ValueError(f"Số không hợp lệ ({len(tail)} chữ số sau dấu tách): {s!r}")


def parse_so_luong(s):
    """Parse số lượng (>0). ValueError nếu rỗng/không parse được/không dương."""
    sl = to_float(s)
    if sl <= 0:
        raise ValueError("Số lượng phải là số dương")
    return sl


def ngay_hop_le(s):
    """Validate ngày YYYY-MM-DD. Trả về chuỗi chuẩn hoặc None nếu rỗng.

    ValueError nếu sai định dạng — không đoán, không âm thầm thay bằng hôm nay.
    """
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError(
            tf("Ngày '{}' sai định dạng — dùng YYYY-MM-DD", s)) from None


# ============================================================
# PDF — render ở tầng GUI, font Unicode, dữ liệu truyền vào
# ============================================================

def pdf_fonts():
    """(regular, bold) font TTF hỗ trợ tiếng Việt — delegate về core.

    Một nguồn sự thật duy nhất: core.dang_ky_font_pdf() (GUI và PDF của
    core/CLI dùng chung). Fallback Helvetica nếu hệ thống không có TTF nào.
    """
    return core.dang_ky_font_pdf()


def _pdf_build(duong_dan, title, info_lines, table_header, table_rows,
               total_rows=None, footer_lines=None, signature=None):
    """Dựng 1 PDF A4: tiêu đề + khối thông tin + 1 bảng + tổng + chữ ký.

    Dùng chung cho biên bản giao hàng và báo cáo. Trả về None nếu OK,
    hoặc chuỗi lỗi.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                        Table, TableStyle)
    except ImportError:
        return "Thiếu thư viện reportlab. Cài: pip install reportlab"

    fname, fbold = pdf_fonts()
    try:
        doc = SimpleDocTemplate(duong_dan, pagesize=A4,
                                leftMargin=15 * mm, rightMargin=15 * mm,
                                topMargin=15 * mm, bottomMargin=15 * mm)
        st_title = ParagraphStyle("T", fontName=fbold, fontSize=15,
                                  alignment=1, spaceAfter=8)
        st_center = ParagraphStyle("C", fontName=fname, fontSize=11,
                                   alignment=1)
        st_info = ParagraphStyle("I", fontName=fname, fontSize=10,
                                 spaceAfter=2)
        el = []
        if title:
            el.append(Paragraph(title, st_title))
        for line in info_lines or []:
            centered = line.startswith("<c>")
            clean = line.replace("<c>", "").replace("</c>", "")
            el.append(Paragraph(clean, st_center if centered else st_info))
        el.append(Spacer(1, 4 * mm))

        data = [table_header] + table_rows
        ncols = len(table_header)
        avail = 180 * mm
        colw = [avail / ncols] * ncols
        tbl = Table(data, colWidths=colw, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), fbold),
            ("FONTNAME", (0, 1), (-1, -1), fname),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe6ea")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        el.append(tbl)

        for line in total_rows or []:
            el.append(Spacer(1, 1.5 * mm))
            el.append(Paragraph(line, ParagraphStyle(
                "R", fontName=fname, fontSize=10, alignment=2)))
        for line in footer_lines or []:
            el.append(Spacer(1, 2 * mm))
            el.append(Paragraph(line, st_info))
        if signature:
            el.append(Spacer(1, 8 * mm))
            sig = Table([signature], colWidths=[90 * mm, 90 * mm])
            sig.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), fname),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]))
            el.append(sig)
        doc.build(el)
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def pdf_bien_ban(bb, duong_dan):
    """In biên bản giao hàng từ dict bb (xem App._bien_ban_data). (path, lỗi)."""
    info = [
        "<c>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</c>",
        "<c><b>Độc lập - Tự do - Hạnh phúc</b></c>",
        "<c>———————————</c>",
        "<b>BIÊN BẢN GIAO HÀNG</b>",
        f"Số: {bb['so_phieu']} /BBGH",
        f"Ngày {bb['ngay']} tháng {bb['thang']} năm {bb['nam']}",
    ]
    if bb.get("so_hop_dong"):
        info.append(f"Số hợp đồng: {bb['so_hop_dong']}")
    info.append(f"Bên nhận: <b>{bb['ten_kh'] or '—'}</b>")
    if bb.get("dia_chi"):
        info.append(f"Địa chỉ: {bb['dia_chi']}")
    if bb.get("ma_so_thue"):
        info.append(f"Mã số thuế: {bb['ma_so_thue']}")
    if bb.get("khoa_nhan"):
        info.append(f"Khoa/Phòng nhận: {bb['khoa_nhan']}")
    if bb.get("nguoi_goi"):
        info.append(f"Người gọi hàng: {bb['nguoi_goi']}")
    info.append("Hai bên tiến hành kiểm tra và thống nhất giao nhận:")

    header = ["STT", "Tên vật tư", "Mã VT", "ĐVT", "Tổng SL",
              "Đơn giá", "Thành tiền"]
    rows = []
    for i, it in enumerate(bb["items"], 1):
        rows.append([str(i), it["ten_vt"], it["ma_vt"], it["dvt"] or "",
                     fmt(it["so_luong"]), fmt(it["don_gia"]),
                     fmt(it["thanh_tien"])])
    vat_pct = bb.get("vat_pct", 8)
    totals = [
        f"Tổng cộng: {fmt(bb['tong'])} ₫",
        f"Thuế GTGT {vat_pct:g}%: {fmt(bb['vat'])} ₫",
        f"<b>Tổng thanh toán: {fmt(bb['tong_cong'])} ₫</b>",
        f"Bằng chữ: {bb['bang_chu']}",
    ]
    footer = ["Chất lượng hàng mới 100%, còn hạn sử dụng, đúng quy cách đóng gói."]
    sig = ["ĐẠI DIỆN BÊN NHẬN\n(Ký, ghi rõ họ tên)",
           f"ĐẠI DIỆN BÊN GIAO\n(Ký, ghi rõ họ tên)\n\n\n{bb.get('nguoi_lap', '')}"]
    loi = _pdf_build(duong_dan, "", info, header, rows, totals, footer, sig)
    return (None, loi) if loi else (duong_dan, None)


def pdf_baocao(con, loai, nam, duong_dan):
    """Xuất báo cáo tháng('m')/quý('q')/thị phần('s'). (path, lỗi)."""
    totals = None
    if loai == "m":
        title = f"BÁO CÁO DOANH SỐ THÁNG NĂM {nam}"
        src = core.doanh_so_thang(con, nam)
        header = ["Tháng", "Số lượng", "Doanh số (₫)"]
        rows = [[f"Tháng {int(r['thang'])}", fmt(r["so_luong"]),
                 fmt(r["doanh_so"])] for r in src]
        totals = [f"Tổng số lượng: {fmt(sum(r['so_luong'] or 0 for r in src))}",
                  f"Tổng doanh số: {fmt(sum(r['doanh_so'] or 0 for r in src))} ₫"]
    elif loai == "q":
        title = f"BÁO CÁO DOANH SỐ QUÝ NĂM {nam}"
        quy = {}
        for r in core.doanh_so_thang(con, nam):
            q = (int(r["thang"]) - 1) // 3 + 1
            d = quy.setdefault(q, {"so_luong": 0, "doanh_so": 0})
            d["so_luong"] += r["so_luong"] or 0
            d["doanh_so"] += r["doanh_so"] or 0
        header = ["Quý", "Số lượng", "Doanh số (₫)"]
        rows = [[f"Quý {q}", fmt(d["so_luong"]), fmt(d["doanh_so"])]
                for q, d in sorted(quy.items())]
        totals = [f"Tổng số lượng: {fmt(sum(d['so_luong'] for d in quy.values()))}",
                  f"Tổng doanh số: {fmt(sum(d['doanh_so'] for d in quy.values()))} ₫"]
    elif loai == "s":
        title = f"BÁO CÁO THỊ PHẦN NĂM {nam}"
        src = core.thi_phan(con, nam)
        header = ["Khách hàng", "Doanh số (₫)", "Tỷ lệ (%)"]
        rows = [[r["ten_kh"], fmt(r["doanh_so"]), f"{r['ti_le']:.1f}"]
                for r in src]
    else:
        return None, f"Loại báo cáo không hợp lệ: {loai}"
    if not rows:
        return None, "Chưa có dữ liệu bán hàng trong năm."
    loi = _pdf_build(duong_dan, title, [], header, rows, totals)
    return (None, loi) if loi else (duong_dan, None)


# ============================================================
# APP
# ============================================================

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(t("QLVT Y tế — Quản lý vật tư y tế"))
        self.geometry("1280x760")
        self.configure(fg_color=C_BG)
        self.con, self.is_new = core.ensure_db()   # DB path do core quyết định
        try:
            core.ensure_auth_schema(self.con)
        except Exception as e:
            # Không chết im lặng: báo người dùng biết schema có vấn đề.
            messagebox.showwarning(
                "QLVT Y tế",
                tf("Không nâng cấp được schema tài khoản: {}\n"
                   "Ứng dụng tiếp tục chạy, tính năng tài khoản có thể lỗi.", e))
        self.cart = []
        self.cart_nhap = []
        self.user = None          # tài khoản đang đăng nhập (dict)
        self._nav_items = []      # menu hiện tại, lọc theo quyền
        self.nav = {}
        self._login_dlg = None
        self._cur_screen = "home"
        self._bb_last = None      # biên bản gần nhất (dict) — preview + PDF
        self._kh_cache = []       # cache ds_khachhang cho màn hiện hành
        # Chưa đăng nhập thì KHÔNG dựng sidebar/topbar — chỉ hiện modal đăng nhập
        self._hien_man_hinh_dang_nhap()
        # Heartbeat: giữ event loop sống (workaround CTkToplevel trên frozen build)
        self._heartbeat_job = None
        self._heartbeat()

    def _heartbeat(self):
        self._heartbeat_job = self.after(200, self._heartbeat)

    # ==================== ĐĂNG NHẬP / ĐĂNG XUẤT ====================

    def _cap_nhat_topbar_user(self):
        if not self.user:
            self.who_name.configure(text="")
            self.who_role.configure(text="")
            self.avatar.configure(text="QL")
            return
        name = (self.user.get("ten_hien_thi")
                or self.user.get("username") or t("Người dùng"))
        self.who_name.configure(text=name)
        self.who_role.configure(text=ten_vai_tro(self.user.get("vai_tro", "")))
        initials = "".join(p[0] for p in name.split()[:2]).upper()
        self.avatar.configure(text=initials or "QL")

    def dang_xuat(self):
        if not messagebox.askyesno(t("Đăng xuất"),
                                   t("Bạn muốn đăng xuất khỏi phần mềm?")):
            return
        self.user = None
        self._nav_items = []
        self.nav = {}
        self._login_dlg = None
        for w in self.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self._hien_man_hinh_dang_nhap()

    # ==================== NGÔN NGỮ ====================

    def _doi_ngon_ngu(self, code):
        """Đổi ngôn ngữ: lưu settings + rebuild TOÀN BỘ UI (sidebar lẫn màn hình)."""
        set_lang(code)
        s = _load_settings()
        s["lang"] = code
        _save_settings(s)
        if not self.user:
            return
        cur = self._cur_screen
        for w in self.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self._build()
        self.show(cur if cur in self.nav else "home")

    def _doi_ngon_ngu_login(self, code, dlg):
        set_lang(code)
        s = _load_settings()
        s["lang"] = code
        _save_settings(s)
        self._hien_man_hinh_dang_nhap()   # dựng lại dialog theo ngôn ngữ mới

    # ==================== KIỂM QUYỀN ====================

    def co_quyen(self, chuc_nang):
        if not self.user:
            return False
        return core.phan_quyyen(self.user.get("vai_tro", ""), chuc_nang)

    def tu_choi(self, ten_chuc_nang):
        messagebox.showerror(
            t("Không đủ quyền"),
            tf("Tài khoản '{}' (vai trò {}) không được phép: {}.",
               self.user.get("username", "?"),
               ten_vai_tro(self.user.get("vai_tro", "")), ten_chuc_nang))
        self.show("home")

    # ==================== KHUNG ====================

    def _screen_info(self, key):
        """Breadcrumb (title, sub) — dịch lazy để đổi ngôn ngữ ăn ngay."""
        info = {
            "home": (t("Tổng quan"), t("Doanh số · tồn kho · cảnh báo")),
            "sale": (t("Bán hàng"), t("Xuất kho · phiếu giao hàng PDF")),
            "in": (t("Nhập kho"), t("Nhập vật tư từ nhà cung cấp")),
            "stock": (t("Tồn kho"), t("Danh mục vật tư & hạn sử dụng")),
            "cust": (t("Khách hàng"), t("Bệnh viện · phòng khám · kho")),
            "contract": (t("Hợp đồng thầu"), t("Tiến độ thực hiện hợp đồng")),
            "report": (t("Báo cáo"), t("Doanh số · thị phần · xuất file")),
            "kygui": (t("Ký gửi"), t("Quản lý hàng ký gửi")),
            "hoadontruoc": (t("Hóa đơn trước"), t("Quản lý hóa đơn chờ")),
            "lichsu": (t("Lịch sử KH"), t("Tra cứu lịch sử giao dịch")),
            "users": (t("Tài khoản"),
                      t("Tạo, sửa, khoá tài khoản và phân quyền")),
        }
        return info.get(key, (key, ""))

    def _build(self):
        # sidebar
        sb = ctk.CTkFrame(self, width=210, fg_color="#0b2530", corner_radius=0)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        ctk.CTkLabel(sb, text=t("QLVT Y TẾ"),
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color="#ffffff").pack(pady=(22, 2), padx=16, anchor="w")
        ctk.CTkLabel(sb, text=t("Vật tư tiêu hao & TBYT"),
                     font=ctk.CTkFont(size=10), text_color="#7fa3ad").pack(
            pady=(0, 18), padx=16, anchor="w")

        items = [
            ("home", "📊", t("Tổng quan"), "xem"),
            ("sale", "🧾", t("Bán hàng"), "xuat"),
            ("in", "📥", t("Nhập kho"), "nhap"),
            ("stock", "📦", t("Tồn kho"), "xem"),
            ("cust", "🏥", t("Khách hàng"), "khachhang"),
            ("contract", "📑", t("Hợp đồng thầu"), "hopdong"),
            ("report", "📈", t("Báo cáo"), "baocao"),
            ("kygui", "📦", t("Ký gửi"), "kygui"),
            ("hoadontruoc", "📄", t("Hóa đơn trước"), "hoadon_truoc"),
            ("lichsu", "🔍", t("Lịch sử KH"), "lichsu"),
        ]
        if self.user and self.user.get("vai_tro") == "admin":
            items.append(("users", "👥", t("Tài khoản"), "admin"))
        self._nav_items = items

        self.nav = {}
        for key, ic, label, quyen in items:
            if not self.co_quyen(quyen):
                continue
            b = ctk.CTkButton(sb, text=f"  {ic}  {label}", anchor="w",
                              font=ctk.CTkFont(size=13),
                              fg_color="transparent", text_color="#b9ced6",
                              hover_color="#123a47", height=38,
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=8, pady=1)
            self.nav[key] = b

        uf = ctk.CTkFrame(sb, fg_color="#123a47", corner_radius=8)
        uf.pack(side="bottom", fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(uf, text=t("🔒 Đăng xuất"), height=30,
                      font=ctk.CTkFont(size=11), fg_color="transparent",
                      text_color="#b9ced6", hover_color="#d1462f",
                      command=self.dang_xuat).pack(fill="x", padx=6, pady=(8, 4))
        ctk.CTkButton(uf, text=t("🔑 Đổi mật khẩu"), height=30,
                      font=ctk.CTkFont(size=11), fg_color="transparent",
                      text_color="#b9ced6", hover_color="#12a3af",
                      command=self._doi_mat_khau).pack(fill="x", padx=6,
                                                       pady=(0, 8))
        ctk.CTkLabel(sb, text=t("Phiên bản desktop 1.2"),
                     font=ctk.CTkFont(size=9),
                     text_color="#5d7f8a").pack(side="bottom", pady=6)

        # topbar
        self.topbar = ctk.CTkFrame(self, fg_color=C_CARD, height=58,
                                   corner_radius=0)
        self.topbar.pack(side="top", fill="x", padx=(210, 0))
        self.topbar.pack_propagate(False)
        tb = ctk.CTkFrame(self.topbar, fg_color="transparent")
        tb.pack(fill="both", expand=True, padx=22)
        self.tb_sub = ctk.CTkLabel(tb, text="", font=ctk.CTkFont(size=11),
                                   text_color=C_MUT, anchor="w")
        self.tb_sub.pack(fill="x")
        self.tb_title = ctk.CTkLabel(tb, text="", font=ctk.CTkFont(size=16,
                                    weight="bold"), text_color=C_INK, anchor="w")
        self.tb_title.pack(fill="x")

        right = ctk.CTkFrame(tb, fg_color="transparent")
        right.pack(side="right", fill="y")
        lang_frame = ctk.CTkFrame(right, fg_color="transparent")
        lang_frame.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(lang_frame, text=t("Ngôn ngữ"),
                     font=ctk.CTkFont(size=10),
                     text_color=C_MUT).pack(side="left", padx=(0, 4))
        self.lang_var = ctk.StringVar(value=get_lang())
        ctk.CTkComboBox(lang_frame, values=["vi", "en"],
                        variable=self.lang_var, width=60, height=28,
                        font=ctk.CTkFont(size=11),
                        command=self._doi_ngon_ngu).pack(side="left")

        self.avatar = ctk.CTkLabel(right, text="QL",
                                   font=ctk.CTkFont(size=12, weight="bold"),
                                   text_color=C_BRAND, fg_color="#e6f5f6",
                                   width=30, height=30, corner_radius=15)
        self.avatar.pack(side="left", padx=(0, 9))
        self.who = ctk.CTkFrame(right, fg_color="transparent")
        self.who.pack(side="left", fill="y")
        self.who_name = ctk.CTkLabel(self.who, text="",
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color=C_INK, anchor="w")
        self.who_name.pack(anchor="w")
        self.who_role = ctk.CTkLabel(self.who, text="",
                                     font=ctk.CTkFont(size=10),
                                     text_color=C_MUT, anchor="w")
        self.who_role.pack(anchor="w")

        self.main = ctk.CTkScrollableFrame(self, fg_color=C_BG)
        self.main.pack(side="left", fill="both", expand=True, padx=14, pady=14)

    def show(self, key):
        # Chặn ở tầng điều hướng: gọi thẳng scr_xxx() cũng phải qua đây
        quyen = dict((k, q) for k, _, _, q in self._nav_items).get(key, "xem")
        if key == "users" and (not self.user
                               or self.user.get("vai_tro") != "admin"):
            self.tu_choi(t("Quản lý tài khoản"))
            return
        if not self.user:
            self._hien_man_hinh_dang_nhap()
            return
        if not self.co_quyen(quyen):
            self.tu_choi(tf("màn hình {}", key))
            return
        self._cur_screen = key
        for k, b in self.nav.items():
            b.configure(fg_color=C_BRAND if k == key else "transparent",
                        text_color="#ffffff" if k == key else "#b9ced6")
        for w in self.main.winfo_children():
            w.destroy()
        self._kh_cache = list(core.ds_khachhang(self.con))
        getattr(self, f"scr_{key}")()
        title, sub = self._screen_info(key)
        self.tb_title.configure(text=title)
        self.tb_sub.configure(text=sub)

    # ==================== TIỆN ÍCH CHUNG ====================

    def header(self, title, sub=""):
        f = ctk.CTkFrame(self.main, fg_color="transparent")
        f.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=C_INK).pack(anchor="w")
        if sub:
            ctk.CTkLabel(f, text=sub, font=ctk.CTkFont(size=11),
                         text_color=C_MUT).pack(anchor="w")

    def card(self, title=None, parent=None):
        host = parent or self.main
        c = ctk.CTkFrame(host, fg_color=C_CARD, corner_radius=12,
                         border_width=1, border_color="#e3e9ef")
        c.pack(fill="x", pady=6)
        if title:
            ctk.CTkLabel(c, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=C_INK).pack(anchor="w", padx=14, pady=(12, 4))
        return c

    def _ma_kh_theo_ten(self, ten):
        """ma_kh từ tên hiển thị (dùng cache của màn hình, không query mỗi phím)."""
        return next((k["ma_kh"] for k in self._kh_cache
                     if k["ten_kh"] == ten), None)

    def _reload_screen(self):
        """Render lại màn hiện tại (sau khi lưu) — không nhân bản widget."""
        self.show(self._cur_screen)

    # ==================== TÀI KHOẢN (chỉ admin) ====================

    def scr_users(self):
        self.header(t("Tài khoản"),
                    t("Tạo, sửa, khoá tài khoản và phân quyền"))
        self.u_msg = ctk.CTkLabel(self.main, text="",
                                  font=ctk.CTkFont(size=11))
        self.u_msg.pack(anchor="w", pady=(0, 8))

        c = self.card(t("Thêm tài khoản mới"))
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        def field(row, label, value="", width=240):
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C_MUT, width=150).grid(
                row=row, column=0, sticky="w", pady=5)
            e = ctk.CTkEntry(f, width=width, height=30)
            if value:
                e.insert(0, value)
            e.grid(row=row, column=1, sticky="w", pady=5)
            return e

        self.u_ten = field(0, t("Tên đăng nhập *"))
        self.u_mk = field(1, t("Mật khẩu *"))
        self.u_mk.configure(show="●")
        self.u_hien_thi = field(2, t("Tên hiển thị *"))
        self.u_email = field(3, t("Email"))
        ctk.CTkLabel(f, text=t("Vai trò"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=150).grid(
            row=4, column=0, sticky="w", pady=5)
        self.u_vai = ctk.CTkComboBox(
            f, width=240, height=30,
            values=[f"{k} — {ten_vai_tro(k)}" for k in core.VAI_TRO],
            state="readonly")
        self.u_vai.set("kho — Kho")
        self.u_vai.grid(row=4, column=1, sticky="w", pady=5)
        ctk.CTkLabel(f, text=t("Phòng ban"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=150).grid(
            row=5, column=0, sticky="w", pady=5)
        self.u_khoa = ctk.CTkEntry(f, width=240, height=30)
        self.u_khoa.grid(row=5, column=1, sticky="w", pady=5)
        self.u_doi_mk = ctk.CTkCheckBox(
            f, text=t("Bắt đổi mật khẩu ở lần đăng nhập đầu"),
            font=ctk.CTkFont(size=11))
        self.u_doi_mk.grid(row=6, column=1, sticky="w", pady=(4, 0))
        ctk.CTkButton(f, text=t("Thêm tài khoản"), height=34, fg_color=C_BRAND,
                      hover_color="#12a3af",
                      command=self._them_user).grid(
            row=7, column=1, sticky="w", pady=(10, 0))

        # chú thích bảng quyền
        q = self.card(t("Bảng quyền theo vai trò"))
        qb = ctk.CTkFrame(q, fg_color="transparent")
        qb.pack(fill="x", padx=14, pady=(0, 12))
        for vai in core.VAI_TRO:
            ds = [ten for ten, _lbl in core.quyen_chuc_nang().items()
                  if core.phan_quyyen(vai, ten)]
            ctk.CTkLabel(qb, text=f"{ten_vai_tro(vai)}: {', '.join(ds) or '—'}",
                         font=ctk.CTkFont(size=10),
                         text_color=C_MUT).pack(anchor="w", pady=1)

        c2 = self.card(t("Danh sách tài khoản"))
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        self.u_box = b2
        self._load_users()

    def _load_users(self):
        for w in self.u_box.winfo_children():
            w.destroy()
        rows = core.ds_users(self.con)
        cols = [t("ID"), t("Tên đăng nhập"), t("Tên hiển thị"), t("Vai trò"),
                t("Phòng ban"), t("Email"), t("Trạng thái"),
                t("Đăng nhập cuối"), t("Thao tác")]
        widths = [36, 130, 160, 100, 80, 170, 80, 140, 210]
        for i, col_name in enumerate(cols):
            ctk.CTkLabel(self.u_box, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        if not rows:
            ctk.CTkLabel(self.u_box, text=t("Chưa có tài khoản nào."),
                         text_color=C_MUT).grid(row=1, column=0, columnspan=9,
                                                pady=10)
            return
        for idx, r in enumerate(rows):
            la_admin = (r["username"] == "admin")
            st = t("Đang khoá") if r["hoat_dong"] == 0 else t("Hoạt động")
            st_cl = C_BAD if r["hoat_dong"] == 0 else C_OK
            vals = [str(r["id"]), r["username"], r["ten_hien_thi"],
                    ten_vai_tro(r["vai_tro"]), r["khoa"] or "—",
                    r["email"] or "—"]
            for i, v in enumerate(vals):
                ctk.CTkLabel(self.u_box, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=widths[i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            ctk.CTkLabel(self.u_box, text=st,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=st_cl, width=widths[6]).grid(
                row=idx + 1, column=6, padx=4, pady=3, sticky="w")
            ctk.CTkLabel(self.u_box,
                         text=r["lan_cuoi_dang_nhap"] or t("Chưa đăng nhập"),
                         font=ctk.CTkFont(size=10), text_color=C_MUT,
                         width=widths[7]).grid(row=idx + 1, column=7,
                                               padx=4, pady=3, sticky="w")
            btns = ctk.CTkFrame(self.u_box, fg_color="transparent")
            btns.grid(row=idx + 1, column=8, padx=4, pady=3, sticky="w")
            ctk.CTkButton(btns, text=t("Sửa"), width=52, height=24,
                          font=ctk.CTkFont(size=10),
                          command=lambda rr=r: self._sua_user(rr)).pack(
                side="left", padx=2)
            ctk.CTkButton(btns, text=t("Đặt lại MK"), width=82, height=24,
                          font=ctk.CTkFont(size=10),
                          command=lambda rr=r: self._dat_lai_mk(rr)).pack(
                side="left", padx=2)
            ctk.CTkButton(btns,
                          text=t("Khoá") if r["hoat_dong"] else t("Mở khoá"),
                          width=64, height=24, font=ctk.CTkFont(size=10),
                          fg_color=C_WARN if r["hoat_dong"] else C_OK,
                          hover_color=("#a06300" if r["hoat_dong"]
                                       else "#157a46"),
                          command=lambda rr=r: self._khoa_user(rr)).pack(
                side="left", padx=2)
            if not la_admin:
                ctk.CTkButton(btns, text=t("Xoá"), width=48, height=24,
                              font=ctk.CTkFont(size=10), fg_color=C_BAD,
                              hover_color="#a83826",
                              command=lambda rr=r: self._xoa_user(rr)).pack(
                    side="left", padx=2)

    def _bao_user(self, text, loi=False):
        self.u_msg.configure(text=text, text_color=C_BAD if loi else C_OK)

    def _them_user(self):
        username = self.u_ten.get().strip()
        mk = self.u_mk.get()
        hien_thi = self.u_hien_thi.get().strip()
        vai = (self.u_vai.get() or "").split(" — ")[0]
        try:
            core.create_user(self.con, username, mk, hien_thi, vai,
                             email=self.u_email.get().strip(),
                             khoa=self.u_khoa.get().strip(),
                             doi_mk_lan_dau=bool(self.u_doi_mk.get()))
        except ValueError as e:
            self._bao_user(str(e), True)
            return
        for e in (self.u_ten, self.u_mk, self.u_hien_thi, self.u_email,
                  self.u_khoa):
            e.delete(0, "end")
        self._bao_user(tf("Đã tạo tài khoản '{}' với vai trò {}.",
                          username, ten_vai_tro(vai)))
        self._load_users()

    def _sua_user(self, r):
        w = ctk.CTkToplevel(self)
        w.title(tf("Sửa tài khoản — {}", r["username"]))
        w.geometry("420x400")
        w.configure(fg_color=C_BG)
        fr = ctk.CTkScrollableFrame(w, fg_color=C_BG)
        fr.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(fr, text=tf("Tên đăng nhập: {}", r["username"]),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", pady=(0, 8))
        ctk.CTkLabel(fr, text=t("Tên hiển thị"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_ten = ctk.CTkEntry(fr, width=360, height=30)
        e_ten.insert(0, r["ten_hien_thi"])
        e_ten.pack(pady=(4, 8))
        ctk.CTkLabel(fr, text="Email",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_email = ctk.CTkEntry(fr, width=360, height=30)
        e_email.insert(0, r["email"] or "")
        e_email.pack(pady=(4, 8))
        ctk.CTkLabel(fr, text=t("Phòng ban"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_khoa = ctk.CTkEntry(fr, width=360, height=30)
        e_khoa.insert(0, r["khoa"] or "")
        e_khoa.pack(pady=(4, 8))
        ctk.CTkLabel(fr, text=t("Vai trò"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_vai = ctk.CTkComboBox(
            fr, width=360, height=30,
            values=[f"{k} — {ten_vai_tro(k)}" for k in core.VAI_TRO],
            state="readonly")
        e_vai.set(f"{r['vai_tro']} — {ten_vai_tro(r['vai_tro'])}")
        e_vai.pack(pady=(4, 10))
        msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11))
        msg.pack(anchor="w", pady=(0, 6))

        def _ok():
            vai = e_vai.get().split(" — ")[0]
            try:
                core.sua_user(self.con, r["id"],
                              ten_hien_thi=e_ten.get().strip(), vai_tro=vai,
                              email=e_email.get().strip(),
                              khoa=e_khoa.get().strip(),
                              nguoi_thao_tac=self.user["username"])
            except ValueError as e:
                msg.configure(text=str(e), text_color=C_BAD)
                return
            msg.configure(text=t("Đã lưu."), text_color=C_OK)
            self.after(400, w.destroy)
            self._load_users()

        ctk.CTkButton(fr, text=t("Lưu"), height=34, fg_color=C_BRAND,
                      hover_color="#12a3af", command=_ok).pack(anchor="w")

    def _dat_lai_mk(self, r):
        if r["username"] == "admin" and self.user.get("username") != "admin":
            messagebox.showerror(
                t("Lỗi"), t("Chỉ tài khoản admin được đặt lại mật khẩu admin."))
            return
        w = ctk.CTkToplevel(self)
        w.title(tf("Đặt lại mật khẩu — {}", r["username"]))
        w.geometry("400x300")
        w.configure(fg_color=C_BG)
        fr = ctk.CTkFrame(w, fg_color=C_CARD, corner_radius=12)
        fr.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(fr, text=tf("Tài khoản: {}", r["username"]),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(
            pady=(16, 10), anchor="w", padx=16)
        ctk.CTkLabel(fr, text=t("Mật khẩu mới"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w", padx=16)
        e1 = ctk.CTkEntry(fr, width=340, height=32, show="●")
        e1.pack(padx=16, pady=4)
        ctk.CTkLabel(fr, text=t("Nhập lại mật khẩu"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w", padx=16)
        e2 = ctk.CTkEntry(fr, width=340, height=32, show="●")
        e2.pack(padx=16, pady=4)
        doi_lai = ctk.CTkCheckBox(
            fr, text=t("Buộc đổi lại mật khẩu ở lần đăng nhập kế"),
            font=ctk.CTkFont(size=11))
        doi_lai.select()
        doi_lai.pack(anchor="w", padx=16, pady=(10, 0))
        msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11))
        msg.pack(anchor="w", padx=16, pady=(6, 0))

        def _ok():
            if e1.get() != e2.get():
                msg.configure(text=t("Hai mật khẩu không khớp"),
                              text_color=C_BAD)
                return
            try:
                core.dat_lai_mat_khau(self.con, r["id"], e1.get(),
                                      nguoi_thao_tac=self.user["username"],
                                      doi_lai_phan_hoi=bool(doi_lai.get()))
            except ValueError as e:
                msg.configure(text=str(e), text_color=C_BAD)
                return
            msg.configure(text=t("Đã đặt lại mật khẩu."), text_color=C_OK)
            self.after(400, w.destroy)
            self._load_users()

        ctk.CTkButton(fr, text=t("Đặt lại"), height=34, fg_color=C_BRAND,
                      hover_color="#12a3af", command=_ok).pack(
            padx=16, pady=(12, 16), anchor="w")

    def _khoa_user(self, r):
        if r["username"] == "admin":
            messagebox.showerror(t("Lỗi"),
                                 t("Không thể khoá tài khoản admin hệ thống."))
            return
        if r["hoat_dong"]:
            if not messagebox.askyesno(
                    t("Khoá tài khoản"),
                    tf("Khoá tài khoản '{}'? Người này sẽ không đăng nhập được nữa.",
                       r["username"])):
                return
            try:
                core.sua_user(self.con, r["id"], hoat_dong=0,
                              nguoi_thao_tac=self.user["username"])
                core.don_session(self.con, r["id"])
                self._bao_user(tf("Đã khoá tài khoản '{}'.", r["username"]))
            except ValueError as e:
                self._bao_user(str(e), True)
        else:
            try:
                core.sua_user(self.con, r["id"], hoat_dong=1,
                              nguoi_thao_tac=self.user["username"])
                self._bao_user(tf("Đã mở khoá tài khoản '{}'.", r["username"]))
            except ValueError as e:
                self._bao_user(str(e), True)
        self._load_users()

    def _xoa_user(self, r):
        if r["username"] == "admin":
            messagebox.showerror(t("Lỗi"),
                                 t("Không thể xoá tài khoản admin hệ thống."))
            return
        if not messagebox.askyesno(
                t("Xoá tài khoản"),
                tf("Xoá vĩnh viễn tài khoản '{}'?\n"
                   "Lịch sử phiếu đã lập vẫn được giữ nguyên.", r["username"])):
            return
        try:
            core.xoa_user(self.con, r["id"],
                          nguoi_thao_tac=self.user["username"])
        except ValueError as e:
            self._bao_user(str(e), True)
            return
        self._bao_user(tf("Đã xoá tài khoản '{}'.", r["username"]))
        self._load_users()

    def _doi_mat_khau(self):
        if not self.user or "id" not in self.user:
            return
        w = ctk.CTkToplevel(self)
        w.title(t("Đổi mật khẩu"))
        w.geometry("400x340")
        w.configure(fg_color=C_BG)
        fr = ctk.CTkFrame(w, fg_color=C_CARD, corner_radius=12)
        fr.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(fr, text=tf("Tài khoản: {}",
                                 self.user.get("username", "?")),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(
            pady=(16, 10), padx=16, anchor="w")
        ctk.CTkLabel(fr, text=t("Mật khẩu hiện tại"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w", padx=16)
        e0 = ctk.CTkEntry(fr, width=340, height=32, show="●")
        e0.pack(padx=16, pady=4)
        ctk.CTkLabel(fr, text=t("Mật khẩu mới (tối thiểu 6 ký tự)"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w", padx=16)
        e1 = ctk.CTkEntry(fr, width=340, height=32, show="●")
        e1.pack(padx=16, pady=4)
        ctk.CTkLabel(fr, text=t("Nhập lại mật khẩu mới"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w", padx=16)
        e2 = ctk.CTkEntry(fr, width=340, height=32, show="●")
        e2.pack(padx=16, pady=4)
        msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11))
        msg.pack(anchor="w", padx=16, pady=(6, 0))

        def _ok():
            if e1.get() != e2.get():
                msg.configure(text=t("Hai mật khẩu mới không khớp"),
                              text_color=C_BAD)
                return
            loi = core.doi_mat_khau(self.con, self.user["id"], e0.get(),
                                    e1.get())
            if loi:
                msg.configure(text=loi, text_color=C_BAD)
                return
            self.user["phai_doi_mk"] = False
            msg.configure(text=t("Đã đổi mật khẩu."), text_color=C_OK)
            self.after(600, w.destroy)

        ctk.CTkButton(fr, text=t("Đổi mật khẩu"), height=34, fg_color=C_BRAND,
                      hover_color="#12a3af", command=_ok).pack(
            padx=16, pady=(12, 16), anchor="w")
        e0.focus_set()

    # ==================== 1. TỔNG QUAN ====================

    def scr_home(self):
        self.header(t("Tổng quan"),
                    t("Bức tranh kinh doanh & cảnh báo trong ngày"))
        tk_ = core.ton_kho(self.con)
        tong_gia_tri = sum(r["gia_tri_ton"] or 0 for r in tk_)
        tong_don_vi = sum(r["ton_kho"] or 0 for r in tk_)
        cb = core.canh_bao_v2(self.con, tk_)
        can_nhap = len(cb["can_nhap"])
        het_han = len(cb["het_han"])
        sap_het = len(cb["sap_het"])

        ds24 = core.doanh_so_thang_gan_nhat(self.con, 24)
        cur = ds24[-1] if ds24 else {"nam": date.today().year,
                                     "thang": date.today().month,
                                     "doanh_so": 0}
        prev = ds24[-2] if len(ds24) > 1 else None
        chenh = ((cur["doanh_so"] or 0) - (prev["doanh_so"] or 0)) if prev else 0
        tang = chenh >= 0

        row = ctk.CTkFrame(self.main, fg_color="transparent")
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure((0, 1, 2, 3), weight=1)
        kpis = [
            (tf("Doanh số tháng {}/{}", int(cur["thang"]), cur["nam"]),
             money(cur["doanh_so"]),
             ("▲ +" if tang else "▼ -") + money(abs(chenh))
             + t(" so với tháng trước"), C_BRAND),
            (t("Giá trị tồn kho"), money(tong_gia_tri),
             tf("{} mã vật tư · {} đơn vị", len(tk_), fmt(tong_don_vi)),
             "#2f6fd1"),
            (t("Cần nhập thêm"), tf("{} mã", can_nhap),
             t("Dưới mức tồn kho tối thiểu"), C_WARN),
            (t("Hàng sắp hết / đã hết hạn"), fmt(sap_het + het_han),
             t("Đơn vị cần ưu tiên xuất trước"), C_BAD),
        ]
        for i, (lb, vl, sb, cl) in enumerate(kpis):
            k = ctk.CTkFrame(row, fg_color=C_CARD, corner_radius=12,
                             border_width=1, border_color="#e3e9ef")
            k.grid(row=0, column=i, padx=5, sticky="nsew")
            ctk.CTkLabel(k, text=lb, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, wraplength=210,
                         justify="left").pack(pady=(12, 0), padx=12, anchor="w")
            ctk.CTkLabel(k, text=vl, font=ctk.CTkFont(size=22, weight="bold"),
                         text_color=cl).pack(pady=(2, 0), padx=12, anchor="w")
            ctk.CTkLabel(k, text=sb, font=ctk.CTkFont(size=10),
                         text_color=C_MUT, wraplength=210,
                         justify="left").pack(pady=(0, 12), padx=12, anchor="w")

        # --- Biến động doanh số 24 tháng ---
        c = self.card(t("Biến động doanh số 24 tháng gần nhất"))
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(b, text=t("Nguồn: phiếu xuất · tự động tổng hợp"),
                     font=ctk.CTkFont(size=10),
                     text_color=C_MUT).pack(anchor="w")
        if not ds24:
            ctk.CTkLabel(b, text=t("Chưa có dữ liệu bán hàng."),
                         text_color=C_MUT).pack(anchor="w", pady=(0, 8))
        else:
            self._chart_doanh_so(b, ds24)

        # --- Top sản phẩm | Cảnh báo ---
        g = ctk.CTkFrame(self.main, fg_color="transparent")
        g.pack(fill="x", pady=6)
        g.grid_columnconfigure(0, weight=27)
        g.grid_columnconfigure(1, weight=20)

        c2 = ctk.CTkFrame(g, fg_color=C_CARD, corner_radius=12,
                          border_width=1, border_color="#e3e9ef")
        c2.grid(row=0, column=0, padx=5, sticky="nsew", pady=6)
        ctk.CTkLabel(c2, text=t("Top sản phẩm theo doanh số"),
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_INK).pack(anchor="w", padx=14, pady=(12, 4))
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.doanh_so_theo_sp(self.con)[:8]
        if not rows:
            ctk.CTkLabel(b2, text=t("Chưa có dữ liệu bán hàng."),
                         text_color=C_MUT).pack(anchor="w")
        mx = (rows[0]["doanh_so"] or 0) if rows else 1
        for r in rows:
            f = ctk.CTkFrame(b2, fg_color="transparent")
            f.pack(fill="x", pady=4)
            top = ctk.CTkFrame(f, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(top, text=r["ma_vt"],
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_BRAND, width=86).pack(side="left")
            ctk.CTkLabel(top, text=r["ten_vt"][:44],
                         font=ctk.CTkFont(size=10), text_color=C_INK,
                         width=300, anchor="w").pack(side="left")
            ctk.CTkLabel(top, text=money(r["doanh_so"]),
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_INK).pack(side="right")
            self._ty_trong(f, (r["doanh_so"] or 0) / mx * 100 if mx else 0)

        c3 = ctk.CTkFrame(g, fg_color=C_CARD, corner_radius=12,
                          border_width=1, border_color="#e3e9ef")
        c3.grid(row=0, column=1, padx=5, sticky="nsew", pady=6)
        ctk.CTkLabel(c3, text=t("Cảnh báo cần xử lý"),
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_INK).pack(anchor="w", padx=14, pady=(12, 4))
        body = ctk.CTkFrame(c3, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(0, 12))
        if not (cb["can_nhap"] or cb["het_han"] or cb["sap_het"]):
            ctk.CTkLabel(body, text=t("Không có cảnh báo 🎉"),
                         text_color=C_OK,
                         font=ctk.CTkFont(size=13)).pack(anchor="w")
        for x in cb["can_nhap"][:6]:
            self._alert_row(body, t("NHẬP THÊM"),
                            f"{x['ma_vt']} — {x['ten_vt']}",
                            tf("Thiếu {}", fmt(x["thieu"])), C_WARN)
        for x in cb["het_han"][:4]:
            self._alert_row(body, t("HẾT HẠN"), f"{x['ma_vt']} — {x['ten_vt']}",
                            tf("{} đơn vị", fmt(x["so_luong"])), C_BAD)
        for x in cb["sap_het"][:4]:
            self._alert_row(body, t("<3 THÁNG"), f"{x['ma_vt']} — {x['ten_vt']}",
                            tf("{} đơn vị", fmt(x["so_luong"])), C_WARN)

        # --- Top khách hàng ---
        c4 = self.card(t("Top khách hàng theo doanh số"))
        b4 = ctk.CTkFrame(c4, fg_color="transparent")
        b4.pack(fill="x", padx=14, pady=(0, 12))
        krows = core.doanh_so_theo_khach(self.con)[:8]
        if not krows:
            ctk.CTkLabel(b4, text=t("Chưa có dữ liệu bán hàng."),
                         text_color=C_MUT).pack(anchor="w")
        kmx = (krows[0]["doanh_so"] or 0) if krows else 1
        for r in krows:
            f = ctk.CTkFrame(b4, fg_color="transparent")
            f.pack(fill="x", pady=4)
            top = ctk.CTkFrame(f, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(top, text=r["ten_kh"][:40],
                         font=ctk.CTkFont(size=11), text_color=C_INK,
                         width=360, anchor="w").pack(side="left")
            ctk.CTkLabel(top, text=money(r["doanh_so"]) + " ₫",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C_INK).pack(side="right")
            self._ty_trong(f, (r["doanh_so"] or 0) / kmx * 100 if kmx else 0)

        # --- sao lưu ---
        c5 = self.card(t("Sao lưu dữ liệu"))
        bf = ctk.CTkFrame(c5, fg_color="transparent")
        bf.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(
            bf,
            text=t("Tạo bản backup trước khi cập nhật phần mềm hoặc định kỳ. "
                   "Khôi phục từ file .db đã sao lưu."),
            text_color=C_MUT, font=ctk.CTkFont(size=11),
            wraplength=700, justify="left").pack(side="left")
        ctk.CTkButton(bf, text=t("📦 Sao lưu ngay"), width=150, height=32,
                      command=self._do_backup).pack(side="right")
        ctk.CTkButton(bf, text=t("♻️ Khôi phục"), width=130, height=32,
                      command=self._do_restore).pack(side="right", padx=(8, 0))

    def _ty_trong(self, parent, pct):
        pct = max(0.0, min(100.0, float(pct or 0)))
        cv = tk.Canvas(parent, width=300, height=6, bg="#edf1f5",
                       highlightthickness=0)
        cv.pack(fill="x", pady=(2, 0))
        if pct > 0:
            cv.create_rectangle(0, 0, 300 * pct / 100, 6, fill=C_BRAND,
                                outline="")

    def _chart_doanh_so(self, parent, rows):
        """Đồ thị cột doanh số 24 tháng — hover xem số chính xác."""
        W, H, PL, PB, PT = 920, 190, 58, 26, 14
        iw, ih = W - PL - 10, H - PB - PT
        mx = max((r["doanh_so"] or 0) for r in rows) or 1
        bw = iw / max(len(rows), 1)
        cv = tk.Canvas(parent, height=H, width=W, bg="#ffffff",
                       highlightthickness=0)
        cv.pack(fill="x", pady=(6, 6))

        for i in range(5):
            y = PT + ih - (ih * i / 4)
            cv.create_line(PL, y, W - 10, y, fill="#edf1f5", width=1)
            cv.create_text(PL - 6, y + 3, text=money(mx * i / 4), anchor="e",
                           font=("Segoe UI", 9), fill="#8a99a8")

        bars = []
        for i, r in enumerate(rows):
            hh = (r["doanh_so"] or 0) / mx * ih
            x = PL + i * bw + bw * 0.18
            rect = cv.create_rectangle(
                x, PT + ih - hh, x + bw * 0.64, PT + ih,
                fill=(C_BRAND if i == len(rows) - 1 else "#9fd3d8"), outline="")
            bars.append((rect, r))
            if i % 2 == 0 or i == len(rows) - 1:
                cv.create_text(x + bw * 0.32, H - 8,
                               text=f"{int(r['thang']):02d}/{str(r['nam'])[2:]}",
                               anchor="center", font=("Segoe UI", 9),
                               fill=C_MUT)

        tip = ctk.CTkLabel(parent, text="",
                           font=ctk.CTkFont(size=11, weight="bold"),
                           text_color=C_INK)
        tip.pack(anchor="w")

        def reset_mau():
            for i, (rect, _) in enumerate(bars):
                cv.itemconfigure(rect, fill=(C_BRAND if i == len(bars) - 1
                                             else "#9fd3d8"))

        def on_move(e):
            for rect, r in bars:
                x0, y0, x1, y1 = cv.coords(rect)
                if x0 <= e.x <= x1 and y0 <= e.y <= y1 + PB:
                    reset_mau()
                    cv.itemconfigure(rect, fill="#12a3af")
                    tip.configure(text=tf(
                        "{:02d}/{} — doanh số {} ₫ · {} đơn vị",
                        int(r["thang"]), r["nam"], fmt(r["doanh_so"]),
                        fmt(r["so_luong"])))
                    return
            reset_mau()
            tip.configure(text="")

        def on_leave(_):
            reset_mau()
            tip.configure(text="")

        cv.bind("<Motion>", on_move)
        cv.bind("<Leave>", on_leave)
        return cv

    def _do_backup(self):
        try:
            path, size_mb = core.backup_db(self.con)
            if path:
                messagebox.showinfo(
                    t("Sao lưu thành công"),
                    tf("Đã lưu backup:\n{}\n\nDung lượng: {:.1f} MB",
                       path, size_mb))
            else:
                messagebox.showerror(t("Lỗi"), t("Không thể tạo backup"))
        except Exception as e:
            messagebox.showerror(t("Lỗi"), str(e))

    def _do_restore(self):
        path = filedialog.askopenfilename(
            title=t("Chọn file backup để khôi phục"),
            filetypes=[("Backup QLVT", "qlvt_backup_*.db"),
                       ("SQLite DB", "*.db"), (t("Tất cả"), "*.*")])
        if not path:
            return
        if not messagebox.askyesno(
                t("Xác nhận khôi phục"),
                t("Dữ liệu hiện tại sẽ bị THAY BẰNG nội dung file:")
                + f"\n{os.path.basename(path)}\n\n"
                + t("Phần mềm tự động backup DB hiện tại trước khi khôi phục.")
                + "\n" + t("Tiếp tục?")):
            return
        con_moi = None
        try:
            self.con.close()
            con_moi = core.connect(DB_PATH, check_same_thread=False)
            bak, loi = core.khoi_phuc_db(con_moi, path)
            con_moi = None    # khoi_phuc_db đã đóng connection này
            if loi:
                messagebox.showerror(t("Lỗi"),
                                     tf("Không khôi phục được: {}", loi))
            else:
                messagebox.showinfo(
                    t("Khôi phục thành công"),
                    tf("Đã khôi phục từ:\n{}\n\nBackup DB cũ: {}", path,
                       os.path.basename(bak) if bak else "—"))
        except Exception as e:
            messagebox.showerror(t("Lỗi"), tf("Khôi phục thất bại: {}", e))
        finally:
            if con_moi is not None:
                try:
                    con_moi.close()
                except Exception:
                    pass
        try:
            self.con = core.connect(DB_PATH, check_same_thread=False)
        except Exception as e:
            messagebox.showerror(t("Lỗi"),
                                 tf("Không mở lại được DB: {}", e))
            return
        # Khôi phục có thể thay toàn bộ users -> buộc đăng nhập lại
        self.user = None
        self._nav_items = []
        self.nav = {}
        self._login_dlg = None
        for w in self.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self._hien_man_hinh_dang_nhap()

    def _alert_row(self, parent, tag, title, detail, color):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=3)
        ctk.CTkLabel(f, text=tag, font=ctk.CTkFont(size=9, weight="bold"),
                     text_color="#ffffff", fg_color=color, corner_radius=4,
                     width=76, height=20).pack(side="left")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=11),
                     text_color=C_INK, width=300, anchor="w").pack(
            side="left", padx=8)
        ctk.CTkLabel(f, text=detail, font=ctk.CTkFont(size=10),
                     text_color=C_MUT).pack(side="right")

    def _count_today(self):
        d = date.today().isoformat()
        return self.con.execute(
            "SELECT COUNT(*) FROM phieu_giaodich "
            "WHERE substr(ngay_lap,1,10)=?", (d,)).fetchone()[0]

    # ==================== 2. BÁN HÀNG ====================

    def scr_sale(self):
        self.header(t("Bán hàng"),
                    t("Xuất hàng · lập biên bản giao hàng tự động"))

        c = self.card(t("Thông tin giao hàng"))
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Khách hàng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=0, column=0, sticky="w", pady=5)
        self.v_kh = ctk.CTkComboBox(
            f, values=[k["ten_kh"] for k in self._kh_cache], width=380,
            height=32)
        self.v_kh.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Ngày giao"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=1, column=0, sticky="w", pady=5)
        self.v_ngay = ctk.CTkEntry(f, width=160, height=32)
        self.v_ngay.insert(0, date.today().isoformat())
        self.v_ngay.grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.v_ngay)).grid(
            row=1, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Số hợp đồng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=2, column=0, sticky="w", pady=5)
        self.v_hd = ctk.CTkComboBox(f, values=[], width=380, height=32)
        self.v_hd.grid(row=2, column=1, sticky="w", pady=5)
        self.v_kh.bind("<<ComboboxSelected>>",
                       lambda _: self._cap_nhat_hop_dong())

        ctk.CTkLabel(f, text=t("Khoa nhận"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=3, column=0, sticky="w", pady=5)
        self.v_khoa = ctk.CTkEntry(f, width=240, height=32,
                                   placeholder_text=t("VD: Hồi sức ngoại"))
        self.v_khoa.grid(row=3, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Người gọi hàng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=4, column=0, sticky="w", pady=5)
        self.v_nguoi = ctk.CTkEntry(f, width=240, height=32,
                                    placeholder_text=t("VD: BS. Nguyễn Văn A"))
        self.v_nguoi.grid(row=4, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Số hóa đơn"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=5, column=0, sticky="w", pady=5)
        self.v_hoadon = ctk.CTkEntry(
            f, width=240, height=32,
            placeholder_text=t("Giao theo hóa đơn trước (nếu có)"))
        self.v_hoadon.grid(row=5, column=1, sticky="w", pady=5)

        # --- thêm mặt hàng ---
        c2 = self.card(t("Thêm mặt hàng"))
        f2 = ctk.CTkFrame(c2, fg_color="transparent")
        f2.pack(fill="x", padx=14, pady=(0, 12))
        f2.grid_columnconfigure(0, weight=1)

        r = ctk.CTkFrame(f2, fg_color="transparent")
        r.pack(fill="x")
        r.grid_columnconfigure(0, weight=1)
        self.v_ma = ctk.CTkEntry(
            r, placeholder_text=t("Nhập mã hoặc tên vật tư…"), height=34)
        self.v_ma.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.v_ma.bind("<KeyRelease>", self._on_ma_typed)
        self.v_sl = ctk.CTkEntry(r, placeholder_text="SL", width=70, height=34)
        self.v_sl.insert(0, "1")
        self.v_sl.grid(row=0, column=1, padx=(0, 6))
        self.v_hsd = ctk.CTkEntry(r, placeholder_text=t("Hạn dùng"), width=110,
                                  height=34)
        self.v_hsd.grid(row=0, column=2, padx=(0, 6))
        ctk.CTkLabel(r, text=t("Giá"), font=ctk.CTkFont(size=9),
                     text_color=C_MUT).grid(row=1, column=0, sticky="w",
                                            pady=(8, 0))
        self.v_gia_nhap = ctk.CTkEntry(
            r, placeholder_text=t("Giá bán (tự điền)"), width=150, height=30)
        self.v_gia_nhap.grid(row=1, column=1, columnspan=2, sticky="w",
                             pady=(8, 0))
        # VAT % cho biên bản (mặc định 8 — sửa được, không hardcode nữa)
        ctk.CTkLabel(r, text=t("VAT %"), font=ctk.CTkFont(size=9),
                     text_color=C_MUT).grid(row=1, column=2, sticky="e",
                                            padx=(0, 34), pady=(8, 0))
        self.v_vat = ctk.CTkEntry(r, width=52, height=30)
        self.v_vat.insert(0, "8")
        self.v_vat.grid(row=1, column=3, sticky="w", pady=(8, 0))
        ctk.CTkButton(r, text=t("+ Thêm"), width=80, height=34,
                      fg_color=C_BRAND, hover_color="#12a3af",
                      command=self._add_cart).grid(row=0, column=3)

        self.v_gia = ctk.CTkLabel(r, text="", font=ctk.CTkFont(size=11),
                                  text_color=C_MUT)
        self.v_gia.grid(row=2, column=0, sticky="w", pady=(6, 0))

        self.v_goi_y = tk.Listbox(r, height=5, font=("Segoe UI", 10),
                                  bg="#ffffff", fg=C_INK,
                                  selectbackground=C_BRAND,
                                  selectforeground="#ffffff",
                                  highlightthickness=0, activestyle="none")
        self.v_goi_y.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.v_goi_y.bind("<<ListboxSelect>>", self._chon_goi_y)

        # --- giỏ hàng ---
        c3 = self.card(t("Chi tiết phiếu xuất"))
        self.cart_box = ctk.CTkFrame(c3, fg_color="transparent")
        self.cart_box.pack(fill="x", padx=14, pady=(0, 12))

        # v_tong phải tạo TRƯỚC khi _render_cart() chạy
        f3 = ctk.CTkFrame(self.main, fg_color="transparent")
        f3.pack(fill="x", pady=6)
        ctk.CTkButton(
            f3, text=t("🧾  Lập biên bản giao hàng"), height=42,
            font=ctk.CTkFont(size=14, weight="bold"), fg_color=C_BRAND,
            hover_color="#12a3af",
            command=self._lap_bien_ban).pack(side="left", padx=(0, 8))
        ctk.CTkButton(f3, text=t("Xóa phiếu"), height=42, fg_color="#eef2f6",
                      text_color=C_INK, hover_color="#e3e9ef",
                      command=self._clear_cart).pack(side="left")
        self.v_tong = ctk.CTkLabel(f3, text=t("Tổng: 0 ₫"),
                                   font=ctk.CTkFont(size=16, weight="bold"),
                                   text_color=C_INK)
        self.v_tong.pack(side="right")

        self._render_cart()

    def _chon_ngay(self, entry):
        """Popup lịch tkcalendar -> ghi YYYY-MM-DD vào entry."""
        try:
            import tkcalendar
        except ImportError:
            messagebox.showerror(
                t("Lỗi"),
                "Thiếu thư viện tkcalendar. Cài: pip install tkcalendar")
            return
        top = ctk.CTkToplevel(self)
        top.title(t("Chọn ngày"))
        top.geometry("320x320")
        try:
            cur = entry.get().strip()
            d = date.fromisoformat(cur) if cur else date.today()
        except ValueError:
            d = date.today()
        cal = tkcalendar.Calendar(top, year=d.year, month=d.month, day=d.day,
                                  date_pattern="yyyy-mm-dd")
        cal.pack(padx=14, pady=14)

        def _ok():
            entry.delete(0, "end")
            entry.insert(0, cal.get_date())
            top.destroy()

        ctk.CTkButton(top, text=t("Chọn"), command=_ok).pack(pady=(0, 12))

    def _cap_nhat_hop_dong(self):
        """Dropdown số HĐ: chỉ HĐ của KH đã chọn VÀ CÒN HẠN."""
        ma_kh = self._ma_kh_theo_ten(self.v_kh.get())
        if not ma_kh:
            self.v_hd.configure(values=[])
            self.v_hd.set("")
            return
        ds = [r[0] for r in core.ds_hop_dong_con_han(self.con, ma_kh)]
        self.v_hd.configure(values=ds)
        if ds and not self.v_hd.get():
            self.v_hd.set(ds[0])

    def _on_ma_typed(self, _):
        q = self.v_ma.get().strip()
        self.v_goi_y.delete(0, "end")
        if not q:
            self.v_gia.configure(text="")
            return
        rows = core.ds_vattu(self.con, q)
        if not rows:
            self.v_gia.configure(text=t("Không tìm thấy mã vật tư này."),
                                 text_color=C_BAD)
            return
        for v in rows[:5]:
            self.v_goi_y.insert(
                "end", f"{v['ma_vt']} — {v['ten_vt'][:44]} · {v['dvt']}")
        v = rows[0]
        ma_kh = self._ma_kh_theo_ten(self.v_kh.get())
        gia, nguon = core.gia_ban(self.con, v["ma_vt"], ma_kh)
        self.v_gia.configure(
            text=tf("{0} — {1}  ·  {2}  ·  {3}: {4} ₫", v["ma_vt"],
                    v["ten_vt"][:40], t("ĐVT"), t("Giá"), fmt(gia)),
            text_color=C_BRAND if nguon == "theo hợp đồng" else C_MUT)
        self.v_gia_nhap.delete(0, "end")
        self.v_gia_nhap.insert(0, fmt(gia))

    def _chon_goi_y(self, _):
        sel = self.v_goi_y.curselection()
        if not sel:
            return
        ma = self.v_goi_y.get(sel[0]).split(" — ")[0].strip()
        self.v_ma.delete(0, "end")
        self.v_ma.insert(0, ma)
        self._on_ma_typed(None)

    def _add_cart(self):
        q = self.v_ma.get().strip()
        if not q:
            return
        rows = core.ds_vattu(self.con, q)
        if not rows:
            self.v_gia.configure(text=t("Không tìm thấy mã vật tư."),
                                 text_color=C_BAD)
            return
        v = rows[0]
        # Số lượng: parse nghiêm ngặt — sai là BÁO LỖI, không âm thầm đổi thành 1
        try:
            sl = parse_so_luong(self.v_sl.get())
        except ValueError as e:
            self.v_gia.configure(text=tf("Số lượng không hợp lệ: {}", e),
                                 text_color=C_BAD)
            return
        # Hạn dùng (nếu nhập): phải đúng YYYY-MM-DD
        try:
            hsd = ngay_hop_le(self.v_hsd.get())
        except ValueError as e:
            self.v_gia.configure(text=str(e), text_color=C_BAD)
            return
        # Cảnh báo vượt tồn (ghi đè được — quyết định nghiệp vụ của người dùng)
        tk_ = next((r["ton_kho"] or 0 for r in core.ton_kho(self.con)
                    if r["ma_vt"] == v["ma_vt"]), None)
        cho_am_kho = False
        if tk_ is not None and sl > tk_:
            if not messagebox.askyesno(
                    t("Cảnh báo tồn kho"),
                    tf("Tồn kho hiện chỉ còn {} {}.\n"
                       "Bạn định xuất {} — vượt tồn kho {}.\n\n"
                       "Vẫn tiếp tục thêm vào giỏ?",
                       fmt(tk_), v["dvt"], fmt(sl), fmt(sl - tk_))):
                return
            # Người dùng xác nhận -> mang cờ xuống core (core mặc định CHẶN
            # âm kho; chỉ ghi khi cờ này được bật một cách có chủ đích).
            cho_am_kho = True
        ma_kh = self._ma_kh_theo_ten(self.v_kh.get())
        gia_auto, nguon = core.gia_ban(self.con, v["ma_vt"], ma_kh)
        # Giá người dùng nhập tay (nếu có) — parse nghiêm ngặt, lỗi là báo
        try:
            gia_nhap = to_float(self.v_gia_nhap.get())
        except ValueError as e:
            self.v_gia.configure(text=tf("Giá không hợp lệ: {}", e),
                                 text_color=C_BAD)
            return
        gia = gia_nhap if gia_nhap > 0 else gia_auto
        self.cart.append({"ma_vt": v["ma_vt"], "ten_vt": v["ten_vt"],
                          "dvt": v["dvt"], "so_luong": sl, "don_gia": gia,
                          "nguon": nguon if gia == gia_nhap else "nhập tay",
                          "han_su_dung": hsd, "cho_am_kho": cho_am_kho})
        self.v_ma.delete(0, "end")
        self.v_sl.delete(0, "end")
        self.v_sl.insert(0, "1")
        self.v_hsd.delete(0, "end")
        self.v_gia_nhap.delete(0, "end")
        self.v_gia.configure(text=tf("Đã thêm. Giá {} ₫ ({})", fmt(gia),
                                     t(nguon)), text_color=C_OK)
        self._render_cart()

    def _render_cart(self):
        widths = [30, 90, 300, 50, 50, 110, 120, 30]
        for w in self.cart_box.winfo_children():
            w.destroy()
        if not self.cart:
            ctk.CTkLabel(self.cart_box,
                         text=t("Phiếu đang trống — thêm mặt hàng ở trên."),
                         text_color=C_MUT,
                         font=ctk.CTkFont(size=12)).pack(anchor="w", pady=8)
            self.v_tong.configure(text=t("Tổng: 0 ₫"))
            return
        hd = ctk.CTkFrame(self.cart_box, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate([t("#"), t("Mã VT"), t("Tên vật tư"),
                                      t("ĐVT"), t("SL"), t("Đơn giá"),
                                      t("Thành tiền"), ""]):
            ctk.CTkLabel(hd, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        tong = 0.0
        for idx, it in enumerate(self.cart, 1):
            tt = it["so_luong"] * it["don_gia"]
            tong += tt
            vals = [str(idx), it["ma_vt"], it["ten_vt"][:40], it["dvt"],
                    fmt(it["so_luong"]), fmt(it["don_gia"]), fmt(tt), "✕"]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK if i != 7 else C_BAD,
                             width=widths[i]).grid(
                    row=idx, column=i, padx=4, pady=3, sticky="w")
        self.v_tong.configure(text=tf("Tổng: {} ₫", fmt(tong)))

    def _clear_cart(self):
        self.cart = []
        self._render_cart()

    def _lap_bien_ban(self):
        """Ghi phiếu xuất cho TỪNG mặt trong giỏ, rồi lập biên bản GỘP tất cả.

        - Lỗi giữa chừng: các mặt đã ghi được GIỮ (có số phiếu), các mặt chưa
          ghi ở lại giỏ để thử lại — không nhân bản, không mất.
        - Biên bản/PDF chứa ĐỦ mặt hàng (bản cũ chỉ in phiếu cuối -> thiếu hàng).
        """
        if not self.cart:
            self.v_gia.configure(text=t("Phiếu đang trống."), text_color=C_BAD)
            return
        ma_kh = self._ma_kh_theo_ten(self.v_kh.get())
        try:
            ngay = ngay_hop_le(self.v_ngay.get()) or date.today().isoformat()
        except ValueError as e:
            self.v_gia.configure(text=str(e), text_color=C_BAD)
            return
        so_hop_dong = self.v_hd.get().strip()
        so_hoa_don = self.v_hoadon.get().strip()
        nguoi_lap = nguoi_lap_cua(self)

        # Giao theo hóa đơn trước: pre-check ĐÚNG theo (hóa đơn, mặt hàng),
        # gộp SL các dòng cùng mặt — TRƯỚC khi ghi bất kỳ phiếu nào.
        if so_hoa_don:
            tong_theo_mat = {}
            for it in self.cart:
                tong_theo_mat[it["ma_vt"]] = (
                    tong_theo_mat.get(it["ma_vt"], 0.0) + it["so_luong"])
            for ma, sl in tong_theo_mat.items():
                loi_hd = self._kiem_tra_giao_hoadon(ma, so_hoa_don, sl)
                if loi_hd:
                    self.v_gia.configure(text=loi_hd, text_color=C_BAD)
                    return

        so_phieus, items_da_ghi = [], []
        loi = None
        for it in list(self.cart):
            try:
                sp = core.ghi_phieu(
                    self.con, "XUAT", ngay, it["ma_vt"], it["so_luong"],
                    it["don_gia"], ma_kh=ma_kh,
                    khoa_nhan=self.v_khoa.get().strip(),
                    nguoi_goi=self.v_nguoi.get().strip(),
                    so_hop_dong=so_hop_dong or None,
                    so_hoa_don=so_hoa_don or None,
                    han_su_dung=it.get("han_su_dung"), nguoi_lap=nguoi_lap,
                    cho_am_kho=bool(it.get("cho_am_kho")))
                so_phieus.append(sp)
                items_da_ghi.append(it)
                self.cart.remove(it)
            except Exception as e:
                loi = tf("Lỗi ở {}: {}", it["ma_vt"], e)
                break
        self._render_cart()
        if loi:
            msg = loi
            if so_phieus:
                msg += " · " + tf("Đã ghi được: {}", ", ".join(so_phieus))
            self.v_gia.configure(text=msg, text_color=C_BAD)
            return
        if not so_phieus:
            return

        bb = self._bien_ban_data(so_phieus, items_da_ghi, ma_kh, ngay,
                                 so_hop_dong, nguoi_lap)
        self._bb_last = bb
        self.v_gia.configure(
            text=tf("Đã ghi {} phiếu: {}", len(so_phieus),
                    ", ".join(so_phieus)), text_color=C_OK)
        self._show_bien_ban(bb)

    def _vat_pct(self):
        """% VAT từ ô nhập (mặc định 8). Sai -> None để caller báo lỗi."""
        try:
            v = to_float(self.v_vat.get())
        except ValueError:
            return None
        if v < 0 or v > 100:
            return None
        return v

    def _bien_ban_data(self, so_phieus, items, ma_kh, ngay, so_hop_dong,
                       nguoi_lap):
        """Dựng dữ liệu biên bản từ TOÀN BỘ phiếu vừa ghi (không chỉ phiếu cuối)."""
        kh = next((k for k in self._kh_cache if k["ma_kh"] == ma_kh), None)
        gom = {}
        for it in items:
            g = gom.setdefault(it["ma_vt"], {
                "ten_vt": it["ten_vt"], "ma_vt": it["ma_vt"],
                "dvt": it["dvt"], "so_luong": 0.0, "don_gia": it["don_gia"]})
            g["so_luong"] += it["so_luong"]
        items_bb, tong = [], 0.0
        for g in gom.values():
            tt = g["so_luong"] * g["don_gia"]
            tong += tt
            items_bb.append({**g, "thanh_tien": tt})
        vat_pct = self._vat_pct()
        if vat_pct is None:
            vat_pct = 8.0
        vat = tong * vat_pct / 100.0
        try:
            d = date.fromisoformat(ngay)
        except ValueError:
            d = date.today()
        return {
            "so_phieu": ", ".join(so_phieus),
            "so_phieus": so_phieus,
            "ngay": d.day, "thang": d.month, "nam": d.year,
            "ten_kh": (kh["ten_kh"] if kh else ""),
            "dia_chi": (kh["dia_chi"] if kh else ""),
            "ma_so_thue": (kh["ma_so_thue"] if kh else ""),
            "khoa_nhan": self.v_khoa.get().strip(),
            "nguoi_goi": self.v_nguoi.get().strip(),
            "so_hop_dong": so_hop_dong or "",
            "items": items_bb, "tong": tong, "vat": vat,
            "vat_pct": vat_pct, "tong_cong": tong + vat,
            "bang_chu": core.so_tien_bang_chu(tong + vat),
            "nguoi_lap": nguoi_lap,
        }

    def _xoa_dong_cart(self, idx):
        """Xóa 1 dòng khỏi giỏ xuất (chữ ✕ trước đây chỉ để trang trí)."""
        if 0 <= idx < len(self.cart):
            self.cart.pop(idx)
            self._render_cart()

    def _show_bien_ban(self, bb):
        w = ctk.CTkToplevel(self)
        w.title(tf("Biên bản giao hàng {}", bb["so_phieu"]))
        w.geometry("860x1000")
        w.configure(fg_color="#ffffff")
        fr = ctk.CTkScrollableFrame(w, fg_color="#ffffff")
        fr.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(fr, text=t("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        ctk.CTkLabel(fr, text=t("Độc lập - Tự do - Hạnh phúc"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        ctk.CTkLabel(fr, text="———————————", text_color=C_MUT).pack()
        ctk.CTkLabel(fr, text=t("BIÊN BẢN GIAO HÀNG"),
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(8, 2))
        ctk.CTkLabel(fr, text=tf("Số: {} /BBGH", bb["so_phieu"]),
                     font=ctk.CTkFont(size=11), text_color=C_MUT).pack()
        ctk.CTkLabel(
            fr, text=tf("Ngày {} tháng {} năm {}", bb["ngay"], bb["thang"],
                        bb["nam"]), font=ctk.CTkFont(size=11)).pack(pady=(6, 0))
        ctk.CTkLabel(
            fr, text=tf("Số hợp đồng: {}", bb["so_hop_dong"] or "…………………"),
            font=ctk.CTkFont(size=11)).pack()
        ctk.CTkLabel(fr, text=tf("Bên nhận: {}", bb["ten_kh"]),
                     font=ctk.CTkFont(size=12,
                                      weight="bold")).pack(pady=(8, 0))
        if bb["dia_chi"]:
            ctk.CTkLabel(fr, text=tf("Địa chỉ: {}", bb["dia_chi"]),
                         font=ctk.CTkFont(size=11)).pack()
        if bb["ma_so_thue"]:
            ctk.CTkLabel(fr, text=tf("Mã số thuế: {}", bb["ma_so_thue"]),
                         font=ctk.CTkFont(size=11)).pack()
        if bb["khoa_nhan"]:
            ctk.CTkLabel(fr,
                         text=tf("Khoa/Phòng nhận: {}", bb["khoa_nhan"]),
                         font=ctk.CTkFont(size=11)).pack()
        if bb["nguoi_goi"]:
            ctk.CTkLabel(fr,
                         text=tf("Người gọi hàng: {}", bb["nguoi_goi"]),
                         font=ctk.CTkFont(size=11)).pack()
        ctk.CTkLabel(
            fr, text=t("Hai bên tiến hành kiểm tra và thống nhất giao nhận:"),
            font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(12, 4))

        tb = ctk.CTkFrame(fr, fg_color="#ffffff", border_width=1,
                          border_color="#444444")
        tb.pack(fill="x")
        widths = [36, 300, 60, 60, 100, 110]
        for i, col_name in enumerate([t("STT"), t("Tên vật tư"), t("ĐVT"),
                                      t("Tổng SL"), t("Đơn giá"),
                                      t("Thành tiền")]):
            ctk.CTkLabel(tb, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#000000", width=widths[i]).grid(
                row=0, column=i, padx=4, pady=6, sticky="w")
        for idx, g in enumerate(bb["items"], 1):
            vals = [str(idx), tf("{}\nMã: {}", g["ten_vt"], g["ma_vt"]),
                    g["dvt"], fmt(g["so_luong"]), fmt(g["don_gia"]),
                    fmt(g["thanh_tien"])]
            for i, v in enumerate(vals):
                ctk.CTkLabel(tb, text=v, font=ctk.CTkFont(size=10),
                             text_color="#000000", width=widths[i]).grid(
                    row=idx, column=i, padx=4, pady=4, sticky="w")

        ctk.CTkLabel(fr, text=tf("Tổng cộng: {} ₫", fmt(bb["tong"])),
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="e", pady=(8, 0))
        ctk.CTkLabel(fr, text=tf("(Bằng chữ: {})", bb["bang_chu"]),
                     font=ctk.CTkFont(size=11)).pack(anchor="e")
        ctk.CTkLabel(
            fr,
            text=tf("Thuế GTGT {}%: {} ₫   ·   Tổng thanh toán: {} ₫",
                    f"{bb['vat_pct']:g}", fmt(bb["vat"]),
                    fmt(bb["tong_cong"])),
            font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="e")
        ctk.CTkLabel(
            fr,
            text=t("Chất lượng hàng mới 100%, còn hạn sử dụng, "
                   "đúng quy cách đóng gói."),
            font=ctk.CTkFont(size=10)).pack(anchor="w", pady=(12, 0))

        sg = ctk.CTkFrame(fr, fg_color="transparent")
        sg.pack(fill="x", pady=(16, 0))
        sg.grid_columnconfigure((0, 1), weight=1)
        for i, col_name in enumerate([t("ĐẠI DIỆN BÊN NHẬN"),
                                      t("ĐẠI DIỆN BÊN GIAO")]):
            ctk.CTkLabel(sg, text=col_name,
                         font=ctk.CTkFont(size=11, weight="bold")).grid(
                row=0, column=i, padx=20, sticky="w")
            ctk.CTkLabel(sg, text=t("(Ký, ghi rõ họ tên)"),
                         font=ctk.CTkFont(size=9), text_color=C_MUT).grid(
                row=1, column=i, padx=20, sticky="w")

        msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11))
        msg.pack(pady=(10, 0))
        ctk.CTkButton(
            fr, text=t("In / Lưu PDF"), height=38, fg_color=C_BRAND,
            hover_color="#12a3af",
            command=lambda: self._in_bien_ban(msg)).pack(pady=(8, 4))

    def _in_bien_ban(self, msg_label=None):
        """Lưu biên bản hiện tại (_bb_last) ra PDF — font Unicode, đủ mặt hàng."""
        bb = self._bb_last
        if not bb:
            return
        first = bb["so_phieus"][0] if bb.get("so_phieus") else "phieu"
        path = filedialog.asksaveasfilename(
            title=t("Lưu biên bản PDF"), defaultextension=".pdf",
            initialfile=f"BienBan_{first.replace(',', '_')}.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        out, loi = pdf_bien_ban(bb, path)
        if loi:
            text = tf("Không xuất được PDF: {}", loi)
            if msg_label is not None:
                msg_label.configure(text=text, text_color=C_BAD)
            else:
                messagebox.showerror(t("Lỗi"), text)
            return
        text = tf("Đã xuất PDF: {}", out)
        if msg_label is not None:
            msg_label.configure(text=text, text_color=C_OK)
        else:
            messagebox.showinfo(t("Xuất PDF"), text)

    # ==================== 3. NHẬP KHO ====================

    def scr_in(self):
        self.header(t("Nhập kho"),
                    t("Nhập nhiều mã vật tư → tồn kho & cảnh báo hạn dùng "
                      "tự cập nhật"))
        c = self.card(t("Phiếu nhập kho"))
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Ngày nhập"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=0, column=0, sticky="w", pady=5)
        self.n_ngay = ctk.CTkEntry(f, width=160, height=32)
        self.n_ngay.insert(0, date.today().isoformat())
        self.n_ngay.grid(row=0, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.n_ngay)).grid(
            row=0, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Mã vật tư"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=1, column=0, sticky="w", pady=5)
        self.n_ma = ctk.CTkEntry(f, width=240, height=32,
                                 placeholder_text=t("Nhập mã…"))
        self.n_ma.grid(row=1, column=1, sticky="w", pady=5)
        self.n_ma.bind("<KeyRelease>", self._on_nhap_typed)

        ctk.CTkLabel(f, text=t("Số lượng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=2, column=0, sticky="w", pady=5)
        self.n_sl = ctk.CTkEntry(f, width=120, height=32)
        self.n_sl.insert(0, "1")
        self.n_sl.grid(row=2, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Hạn sử dụng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=3, column=0, sticky="w", pady=5)
        self.n_hsd = ctk.CTkEntry(f, width=160, height=32,
                                  placeholder_text="YYYY-MM-DD")
        self.n_hsd.grid(row=3, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.n_hsd)).grid(
            row=3, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Đơn giá nhập"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=4, column=0, sticky="w", pady=5)
        self.n_gia = ctk.CTkEntry(f, width=160, height=32)
        self.n_gia.grid(row=4, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Số lô"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=5, column=0, sticky="w", pady=5)
        self.n_lo = ctk.CTkEntry(f, width=200, height=32,
                                 placeholder_text=t("VD: LOT-2026-08"))
        self.n_lo.grid(row=5, column=1, sticky="w", pady=5)

        self.n_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                  text_color=C_MUT)
        self.n_msg.grid(row=6, column=1, sticky="w", pady=(8, 0))

        ctk.CTkButton(f, text=t("➕ Thêm vào phiếu"), height=36,
                      fg_color=C_BRAND, hover_color="#12a3af",
                      command=self._add_nhap).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.n_goi_y = tk.Listbox(f, height=5, font=("Segoe UI", 10),
                                  bg="#ffffff", fg=C_INK,
                                  selectbackground=C_BRAND,
                                  selectforeground="#ffffff",
                                  highlightthickness=0, activestyle="none")
        self.n_goi_y.grid(row=8, column=0, columnspan=3, sticky="ew",
                          pady=(4, 0))
        self.n_goi_y.bind("<<ListboxSelect>>", self._chon_goi_y_nhap)

        c3 = self.card(t("Chi tiết phiếu nhập"))
        self.cart_nhap_box = ctk.CTkFrame(c3, fg_color="transparent")
        self.cart_nhap_box.pack(fill="x", padx=14, pady=(0, 12))

        f3 = ctk.CTkFrame(self.main, fg_color="transparent")
        f3.pack(fill="x", pady=6)
        ctk.CTkButton(f3, text=t("💾 Lưu phiếu nhập"), height=42,
                      fg_color=C_BRAND, hover_color="#12a3af",
                      command=self._luu_nhap).pack(side="left", padx=(0, 8))
        ctk.CTkButton(f3, text=t("Xóa phiếu"), height=42, fg_color="#eef2f6",
                      text_color=C_INK, hover_color="#e3e9ef",
                      command=self._clear_nhap).pack(side="left")
        self.n_tong = ctk.CTkLabel(f3, text=t("Tổng SL: 0"),
                                   font=ctk.CTkFont(size=16, weight="bold"),
                                   text_color=C_INK)
        self.n_tong.pack(side="right")

        self._render_nhap_cart()

    def _doc_dong_nhap(self):
        """Đọc 1 dòng nhập từ form -> dict; ValueError kèm thông báo nếu sai.

        Ô giá trống -> dùng giá danh mục của vật tư.
        """
        q = self.n_ma.get().strip()
        if not q:
            raise ValueError(t("Nhập mã vật tư trước."))
        rows = core.ds_vattu(self.con, q)
        if not rows:
            raise ValueError(t("Mã vật tư không tồn tại."))
        v = rows[0]
        sl = parse_so_luong(self.n_sl.get())
        hsd = ngay_hop_le(self.n_hsd.get())
        raw_gia = self.n_gia.get().strip()
        gia = to_float(raw_gia) if raw_gia else float(v["don_gia"] or 0)
        if gia < 0:
            raise ValueError(t("Đơn giá không hợp lệ."))
        return {"ma_vt": v["ma_vt"], "ten_vt": v["ten_vt"], "dvt": v["dvt"],
                "so_luong": sl, "don_gia": gia,
                "so_lo": self.n_lo.get().strip(), "han_su_dung": hsd,
                "nguoi_lap": nguoi_lap_cua(self)}

    def _add_nhap(self):
        try:
            dong = self._doc_dong_nhap()
        except ValueError as e:
            self.n_msg.configure(text=str(e), text_color=C_BAD)
            return
        self.cart_nhap.append(dong)
        for w_ in (self.n_ma, self.n_gia, self.n_lo, self.n_hsd):
            w_.delete(0, "end")
        self.n_sl.delete(0, "end")
        self.n_sl.insert(0, "1")
        self.n_msg.configure(
            text=tf("Đã thêm {} x {}.", dong["ma_vt"], fmt(dong["so_luong"])),
            text_color=C_OK)
        self._render_nhap_cart()

    def _render_nhap_cart(self):
        widths = [30, 90, 300, 50, 50, 110, 110, 120, 40]
        for w in self.cart_nhap_box.winfo_children():
            w.destroy()
        if not self.cart_nhap:
            ctk.CTkLabel(self.cart_nhap_box,
                         text=t("Phiếu đang trống — thêm vật tư ở trên."),
                         text_color=C_MUT,
                         font=ctk.CTkFont(size=12)).pack(anchor="w", pady=8)
            self.n_tong.configure(text=t("Tổng SL: 0"))
            return
        hd = ctk.CTkFrame(self.cart_nhap_box, fg_color="#fafcfd",
                          corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate([t("#"), t("Mã VT"), t("Tên vật tư"),
                                      t("ĐVT"), t("SL"), t("Đơn giá"),
                                      t("Số lô"), t("HSD"), t("Xóa")]):
            ctk.CTkLabel(hd, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        tong_sl = 0.0
        for idx, it in enumerate(self.cart_nhap, 1):
            tong_sl += it["so_luong"]
            vals = [str(idx), it["ma_vt"], it["ten_vt"][:40], it["dvt"],
                    fmt(it["so_luong"]), fmt(it["don_gia"]),
                    it["so_lo"] or "", it["han_su_dung"] or "", ""]
            for i, v in enumerate(vals):
                if i == 8:
                    continue
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=widths[i]).grid(
                    row=idx, column=i, padx=4, pady=3, sticky="w")
            ctk.CTkButton(hd, text="✕", width=36, height=22,
                          fg_color=C_BAD, hover_color="#a83826",
                          command=lambda i=idx: self._xoa_dong_nhap(
                              i)).grid(row=idx, column=8, padx=4, pady=3)
        self.n_tong.configure(text=tf(
            "Tổng SL: {} | Giá trị: {}", fmt(tong_sl),
            money(sum(i["so_luong"] * i["don_gia"] for i in self.cart_nhap))))

    def _xoa_dong_nhap(self, idx):
        if 0 <= idx - 1 < len(self.cart_nhap):
            self.cart_nhap.pop(idx - 1)
            self._render_nhap_cart()

    def _clear_nhap(self):
        self.cart_nhap = []
        self._render_nhap_cart()

    def _on_nhap_typed(self, _):
        q = self.n_ma.get().strip()
        self.n_goi_y.delete(0, "end")
        rows = core.ds_vattu(self.con, q)[:5] if q else []
        if rows:
            for v in rows:
                self.n_goi_y.insert(
                    "end", f"{v['ma_vt']} — {v['ten_vt'][:44]} · {v['dvt']}")
            v = rows[0]
            self.n_gia.delete(0, "end")
            self.n_gia.insert(0, fmt(v["don_gia"]))
            self.n_msg.configure(text=f"{v['ma_vt']} — {v['ten_vt'][:44]}",
                                 text_color=C_OK)
        else:
            self.n_msg.configure(text=t("Không tìm thấy mã vật tư."),
                                 text_color=C_BAD)

    def _chon_goi_y_nhap(self, _):
        sel = self.n_goi_y.curselection()
        if not sel:
            return
        ma = self.n_goi_y.get(sel[0]).split(" — ")[0].strip()
        self.n_ma.delete(0, "end")
        self.n_ma.insert(0, ma)
        self._on_nhap_typed(None)

    def _luu_nhap(self):
        """Lưu phiếu nhập.

        - Giỏ trống: lưu 1 dòng từ form (chế độ nhanh).
        - Giỏ có dòng: pre-validate TOÀN BỘ trước khi ghi; lỗi giữa chừng thì
          các dòng đã ghi được GỠ khỏi giỏ (không lưu lại -> không trùng),
          dòng lỗi ở lại kèm thông báo.
        """
        if not self.cart_nhap:
            try:
                dong = self._doc_dong_nhap()
                ngay = ngay_hop_le(self.n_ngay.get()) or date.today().isoformat()
            except ValueError as e:
                self.n_msg.configure(text=str(e), text_color=C_BAD)
                return
            try:
                sp = core.ghi_phieu(self.con, "NHAP", ngay, dong["ma_vt"],
                                    dong["so_luong"], dong["don_gia"],
                                    so_lo=dong["so_lo"],
                                    han_su_dung=dong["han_su_dung"],
                                    nguoi_lap=dong["nguoi_lap"])
            except Exception as e:
                self.n_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)
                return
            self.n_msg.configure(
                text=tf("Đã lưu {} — tồn kho đã cập nhật.", sp),
                text_color=C_OK)
            self._clear_nhap()
            for w_ in (self.n_ma, self.n_gia, self.n_lo, self.n_hsd):
                w_.delete(0, "end")
            self.n_ngay.delete(0, "end")
            self.n_ngay.insert(0, date.today().isoformat())
            return

        try:
            ngay = ngay_hop_le(self.n_ngay.get()) or date.today().isoformat()
        except ValueError as e:
            self.n_msg.configure(text=str(e), text_color=C_BAD)
            return
        # Pre-validate toàn bộ dòng TRƯỚC khi ghi bất kỳ dòng nào
        for i, it in enumerate(self.cart_nhap, 1):
            if it["so_luong"] <= 0:
                self.n_msg.configure(
                    text=tf("Dòng {} ({}): số lượng phải > 0.", i,
                            it["ma_vt"]), text_color=C_BAD)
                return
        da_luu, loi = [], None
        for it in list(self.cart_nhap):
            try:
                sp = core.ghi_phieu(self.con, "NHAP", ngay, it["ma_vt"],
                                    it["so_luong"], it["don_gia"],
                                    so_lo=it["so_lo"],
                                    han_su_dung=it["han_su_dung"],
                                    nguoi_lap=it["nguoi_lap"])
                da_luu.append(sp)
                self.cart_nhap.remove(it)
            except Exception as e:
                loi = tf("Lỗi {}: {}", it["ma_vt"], e)
                break
        self._render_nhap_cart()
        if loi:
            self.n_msg.configure(
                text=loi + (tf(" · Đã lưu: {}", ", ".join(da_luu))
                            if da_luu else ""), text_color=C_BAD)
            return
        self.n_msg.configure(
            text=tf("Đã lưu {} — tồn kho đã cập nhật.", ", ".join(da_luu)),
            text_color=C_OK)
        self.n_ngay.delete(0, "end")
        self.n_ngay.insert(0, date.today().isoformat())

    def _thoat_ung_dung(self):
        if getattr(self, "_heartbeat_job", None):
            try:
                self.after_cancel(self._heartbeat_job)
            except Exception:
                pass
            self._heartbeat_job = None
        try:
            self.con.close()
        except Exception:
            pass
        self.destroy()

    def _hien_man_hinh_dang_nhap(self):
        """Hộp thoại đăng nhập MODAL, canh giữa cửa sổ chính."""
        if getattr(self, "_login_dlg", None):
            try:
                self._login_dlg.grab_release()
            except Exception:
                pass
            try:
                self._login_dlg.destroy()
            except Exception:
                pass
            self._login_dlg = None

        dlg = ctk.CTkToplevel(self)
        self._login_dlg = dlg
        dlg.title(t("Đăng nhập — QLVT Y tế"))
        dlg.resizable(False, False)
        dlg.configure(fg_color=C_CARD)
        dlg.protocol("WM_DELETE_WINDOW", self._thoat_ung_dung)

        W, H = 420, 430
        try:
            self.update_idletasks()
            px, py = self.winfo_rootx(), self.winfo_rooty()
            pw, ph = self.winfo_width(), self.winfo_height()
            if pw <= 1 or ph <= 1:
                px = (self.winfo_screenwidth() - W) // 2
                py = (self.winfo_screenheight() - H) // 3
            else:
                px = px + (pw - W) // 2
                py = py + (ph - H) // 2
        except Exception:
            px = (dlg.winfo_screenwidth() - W) // 2
            py = (dlg.winfo_screenheight() - H) // 3
        dlg.geometry("%dx%d+%d+%d" % (W, H, max(0, px), max(0, py)))

        card = ctk.CTkFrame(dlg, fg_color=C_CARD, corner_radius=0)
        card.pack(fill="both", expand=True)

        lang_top = ctk.CTkFrame(card, fg_color="transparent")
        lang_top.pack(fill="x", padx=30, pady=(10, 0))
        ctk.CTkLabel(lang_top, text=t("Ngôn ngữ"),
                     font=ctk.CTkFont(size=10),
                     text_color=C_MUT).pack(side="right", padx=(8, 0))
        login_lang_var = ctk.StringVar(value=get_lang())
        ctk.CTkComboBox(lang_top, values=["vi", "en"],
                        variable=login_lang_var, width=60, height=26,
                        font=ctk.CTkFont(size=10),
                        command=lambda v: self._doi_ngon_ngu_login(
                            v, dlg)).pack(side="right")

        ctk.CTkLabel(card, text=t("QLVT Y TẾ"),
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C_BRAND).pack(pady=(30, 2), padx=30, anchor="w")
        ctk.CTkLabel(card,
                     text=t("Quản lý vật tư y tế — đăng nhập để tiếp tục"),
                     font=ctk.CTkFont(size=11), text_color=C_MUT).pack(
            padx=30, anchor="w")

        ctk.CTkLabel(card, text=t("Tên đăng nhập"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(pady=(22, 4), padx=30, anchor="w")
        self.lg_user = ctk.CTkEntry(card, width=340, height=38,
                                    placeholder_text="VD: admin")
        self.lg_user.pack(padx=30, anchor="w")

        ctk.CTkLabel(card, text=t("Mật khẩu"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(pady=(10, 4), padx=30, anchor="w")
        self.lg_pass = ctk.CTkEntry(card, width=340, height=38, show="\u25cf",
                                    placeholder_text="\u2022\u2022\u2022\u2022"
                                                      "\u2022\u2022")
        self.lg_pass.pack(padx=30, anchor="w")

        self.lg_msg = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=11),
                                   text_color=C_BAD)
        self.lg_msg.pack(pady=(8, 0), padx=30, anchor="w")

        ctk.CTkButton(card, text=t("Đăng nhập"), width=340, height=40,
                      fg_color=C_BRAND, hover_color="#12a3af",
                      command=self._dang_nhap).pack(pady=(14, 8), padx=30)
        ctk.CTkLabel(
            card,
            text=t("Tài khoản mặc định: admin / admin123 "
                   "(đổi ngay sau khi vào)"),
            font=ctk.CTkFont(size=10), text_color=C_MUT).pack(
            pady=(0, 24), padx=30, anchor="w")

        for e in (self.lg_user, self.lg_pass):
            e.bind("<Return>", lambda _e: self._dang_nhap())
        dlg.bind("<Escape>", lambda _e: self._thoat_ung_dung())
        dlg.grab_set()
        dlg.after(150, dlg.lift)
        dlg.after(200, self.lg_user.focus_force)

    def _dang_nhap(self):
        username = self.lg_user.get().strip()
        password = self.lg_pass.get()
        if not username or not password:
            self.lg_msg.configure(text=t("Nhập tên đăng nhập và mật khẩu"))
            return
        user = core.authenticate(self.con, username, password)
        if not user:
            # Không lộ tài khoản có tồn tại hay không
            self.lg_msg.configure(
                text=t("Sai tên đăng nhập hoặc mật khẩu"))
            self.lg_pass.delete(0, "end")
            return
        self.user = user
        self.lg_msg.configure(text="")
        self.lg_pass.delete(0, "end")
        if getattr(self, "_heartbeat_job", None):
            try:
                self.after_cancel(self._heartbeat_job)
            except Exception:
                pass
            self._heartbeat_job = None
        if getattr(self, "_login_dlg", None):
            try:
                self._login_dlg.grab_release()
                self._login_dlg.destroy()
            except Exception:
                pass
            self._login_dlg = None
        self._build()
        self.show("home")
        self._cap_nhat_topbar_user()
        if user.get("phai_doi_mk"):
            messagebox.showwarning(
                t("Đổi mật khẩu bắt buộc"),
                t("Tài khoản này đang dùng mật khẩu mặc định.\n"
                  "Vui lòng đổi mật khẩu ngay."))
            self._doi_mat_khau()

    # ==================== 4. TỒN KHO ====================

    def scr_stock(self):
        self.header(t("Tồn kho"), t("Theo dõi hạn sử dụng & đề xuất nhập thêm"))
        c = self.card(t("Số lượng tồn kho"))
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.ton_kho(self.con)
        if not rows:
            ctk.CTkLabel(b, text=t("Chưa có dữ liệu tồn kho."),
                         text_color=C_MUT).pack(anchor="w")
            return
        widths = [90, 300, 50, 60, 70, 110, 130, 60]
        hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate([t("Mã VT"), t("Tên vật tư"), t("ĐVT"),
                                      t("Tồn"), t("Tối thiểu"), t("Giá trị"),
                                      t("Trạng thái"), ""]):
            ctk.CTkLabel(hd, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        for idx, r in enumerate(rows):
            tk_ = r["ton_kho"] or 0
            mn = r["ton_toi_thieu"] or 0
            if mn > 0 and tk_ < mn:
                st, cl = t("Cần nhập"), C_WARN
            else:
                st, cl = t("Ổn định"), C_OK
            vals = [r["ma_vt"], r["ten_vt"][:40], r["dvt"], fmt(tk_), fmt(mn),
                    money(r["gia_tri_ton"]), st]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=cl if i == 6 else C_INK,
                             width=widths[i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            ctk.CTkButton(hd, text=t("Sửa"), width=50, height=22,
                          font=ctk.CTkFont(size=10),
                          command=lambda rr=r: self._sua_toi_thieu(rr)).grid(
                row=idx + 1, column=7, padx=4, pady=3)

    def _sua_toi_thieu(self, r):
        top = ctk.CTkToplevel(self)
        top.title(t("Sửa tồn kho tối thiểu"))
        top.geometry("320x170")
        ctk.CTkLabel(top, text=f"{r['ma_vt']} — {r['ten_vt'][:40]}",
                     font=ctk.CTkFont(size=11,
                                      weight="bold")).pack(padx=14, pady=(14, 4))
        e = ctk.CTkEntry(top, width=140, height=30)
        e.insert(0, str(r["ton_toi_thieu"] or 0))
        e.pack(padx=14, pady=4)
        msg = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=10),
                           text_color=C_BAD)
        msg.pack(padx=14)

        def _ok():
            try:
                mn = to_float(e.get())
            except ValueError:
                msg.configure(text=t("Số không hợp lệ"))
                return
            if mn < 0:
                msg.configure(text=t("Số không hợp lệ"))
                return
            self.con.execute(
                "UPDATE dm_vattu SET ton_toi_thieu=? WHERE ma_vt=?",
                (mn, r["ma_vt"]))
            self.con.commit()
            top.destroy()
            self._reload_screen()

        ctk.CTkButton(top, text=t("Lưu"), command=_ok).pack(pady=(6, 12))

    # ==================== 5. KHÁCH HÀNG ====================

    def scr_cust(self):
        self.header(t("Khách hàng"),
                    t("Thêm mới / cập nhật thông tin khách hàng"))
        f = self.card(t("Thông tin khách hàng"))
        fr = ctk.CTkFrame(f, fg_color="transparent")
        fr.pack(fill="x", padx=14, pady=(0, 6))
        self._kh_edit = {"ma": None}
        self._kh_widgets = {}
        fields = [("ma", t("Mã KH (trống = tự tạo)"), 120),
                  ("ten", t("Tên khách hàng *"), 260),
                  ("dc", t("Địa chỉ"), 300),
                  ("mst", t("Mã số thuế"), 140),
                  ("kv", t("Khu vực"), 120)]
        for i, (_k, lb, w) in enumerate(fields):
            ctk.CTkLabel(fr, text=lb, font=ctk.CTkFont(size=10),
                         text_color=C_MUT, width=w, anchor="w").grid(
                row=0, column=i, padx=3, sticky="w")
        for i, (k, _lb, w) in enumerate(fields):
            e = ctk.CTkEntry(fr, width=w, height=28,
                             font=ctk.CTkFont(size=11))
            e.grid(row=1, column=i, padx=3)
            self._kh_widgets[k] = e
        ctk.CTkButton(fr, text=t("💾 Lưu"), width=90, height=28,
                      command=self._save_kh).grid(row=1, column=5, padx=6)
        ctk.CTkButton(fr, text=t("🧹 Xóa form"), width=100, height=28,
                      command=self._clear_kh).grid(row=1, column=6, padx=3)
        self._kh_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                    text_color=C_OK)
        self._kh_msg.pack(padx=14, pady=(0, 10))

        c = self.card(t("Danh sách khách hàng"))
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        widths = [250, 60, 90, 130, 330, 60]
        hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate([t("Tên khách hàng"), t("Mã"),
                                      t("Khu vực"), t("Mã số thuế"),
                                      t("Địa chỉ"), ""]):
            ctk.CTkLabel(hd, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        for idx, r in enumerate(self._kh_cache):
            vals = [r["ten_kh"], r["ma_kh"], r["khu_vuc"] or "—",
                    r["ma_so_thue"] or "—", (r["dia_chi"] or "—")[:46]]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=widths[i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            ctk.CTkButton(hd, text=t("Sửa"), width=50, height=22,
                          font=ctk.CTkFont(size=10),
                          command=lambda rr=r: self._load_kh(rr)).grid(
                row=idx + 1, column=5, padx=4, pady=3)

    def _load_kh(self, r):
        self._kh_edit["ma"] = r["ma_kh"]
        mapping = {"ma": "ma_kh", "ten": "ten_kh", "dc": "dia_chi",
                   "mst": "ma_so_thue", "kv": "khu_vuc"}
        for k, w in self._kh_widgets.items():
            v = r[mapping[k]] if r[mapping[k]] is not None else ""
            w.delete(0, "end")
            w.insert(0, str(v))
        self._kh_msg.configure(text=tf("Đang sửa: {}", r["ma_kh"]),
                               text_color=C_WARN)

    def _clear_kh(self):
        self._kh_edit["ma"] = None
        for w in self._kh_widgets.values():
            w.delete(0, "end")
        self._kh_msg.configure(text="", text_color=C_OK)

    def _save_kh(self):
        vals = {k: w.get().strip() for k, w in self._kh_widgets.items()}
        try:
            ma = core.luu_khachhang(self.con, ma_kh=vals["ma"] or None,
                                    ten_kh=vals["ten"], dia_chi=vals["dc"],
                                    ma_so_thue=vals["mst"],
                                    khu_vuc=vals["kv"])
        except ValueError as e:
            self._kh_msg.configure(text=f"❌ {e}", text_color=C_BAD)
            return
        self._reload_screen()   # render lại 1 lần, không nhân bản widget
        self._kh_msg.configure(text=tf("✅ Đã lưu: {}", ma), text_color=C_OK)

    # ==================== 6. HỢP ĐỒNG ====================

    def scr_contract(self):
        self.header(t("Hợp đồng thầu"), t("Thêm hợp đồng & tiến độ thực hiện"))
        f = self.card(t("Thêm hợp đồng mới"))
        fr = ctk.CTkFrame(f, fg_color="transparent")
        fr.pack(fill="x", padx=14, pady=(0, 12))
        self._hd_msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11),
                                    text_color=C_OK)
        self._hd_msg.grid(row=0, column=0, columnspan=8, sticky="w",
                          pady=(0, 6))

        ctk.CTkLabel(fr, text=t("Khách hàng"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=110).grid(row=1, column=0,
                                                       sticky="w")
        self.hd_kh = ctk.CTkComboBox(
            fr, values=[k["ten_kh"] for k in self._kh_cache], width=200,
            height=28)
        self.hd_kh.grid(row=1, column=1, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Số HĐ"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=110).grid(row=1, column=2,
                                                       sticky="w")
        self.hd_so = ctk.CTkEntry(fr, width=160, height=28)
        self.hd_so.grid(row=1, column=3, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Mã VT"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=110).grid(row=1, column=4,
                                                       sticky="w")
        self.hd_ma = ctk.CTkEntry(fr, width=130, height=28)
        self.hd_ma.grid(row=1, column=5, sticky="w", padx=2)

        ctk.CTkLabel(fr, text="SL", font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=60).grid(row=2, column=0,
                                                      sticky="w")
        self.hd_sl = ctk.CTkEntry(fr, width=90, height=28)
        self.hd_sl.insert(0, "1")
        self.hd_sl.grid(row=2, column=1, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Đơn giá"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=60).grid(row=2, column=2,
                                                      sticky="w")
        self.hd_gia = ctk.CTkEntry(fr, width=130, height=28)
        self.hd_gia.grid(row=2, column=3, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Ngày ký"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=80).grid(row=2, column=4,
                                                      sticky="w")
        self.hd_ky = ctk.CTkEntry(fr, width=130, height=28,
                                  placeholder_text="YYYY-MM-DD")
        self.hd_ky.insert(0, date.today().isoformat())
        self.hd_ky.grid(row=2, column=5, sticky="w", padx=2)
        ctk.CTkButton(fr, text="📅", width=32, height=28,
                      command=lambda: self._chon_ngay(self.hd_ky)).grid(
            row=2, column=6, padx=2)
        ctk.CTkLabel(fr, text=t("Hết hạn"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=80).grid(row=3, column=0,
                                                      sticky="w")
        self.hd_het = ctk.CTkEntry(fr, width=130, height=28,
                                   placeholder_text="YYYY-MM-DD")
        self.hd_het.grid(row=3, column=1, sticky="w", padx=2)
        ctk.CTkButton(fr, text="📅", width=32, height=28,
                      command=lambda: self._chon_ngay(self.hd_het)).grid(
            row=3, column=2, padx=2)
        ctk.CTkButton(fr, text=t("💾 Lưu HĐ"), width=100, height=28,
                      fg_color=C_BRAND,
                      command=self._luu_hop_dong).grid(row=3, column=3, padx=2)

        c = self.card(t("Tiến độ hợp đồng"))
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.tien_do_hop_dong(self.con)
        if not rows:
            ctk.CTkLabel(b, text=t("Chưa có hợp đồng nào."),
                         text_color=C_MUT).pack(anchor="w")
            return
        widths = [110, 200, 90, 60, 60, 60, 60, 130]
        hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate([t("Số HĐ"), t("Khách hàng"), t("Mã VT"),
                                      t("Tổng SL"), t("Đã TH"), t("Còn lại"),
                                      t("Tiến độ")]):
            ctk.CTkLabel(hd, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        for idx, r in enumerate(rows):
            sl = r["so_luong"] or 0
            done = r["da_thuc_hien"] or 0
            pc = (done / sl * 100) if sl else 0
            ten_kh = next((k["ten_kh"] for k in self._kh_cache
                           if k["ma_kh"] == r["ma_kh"]), r["ma_kh"] or "")
            vals = [r["so_hd"], ten_kh[:24], r["ma_vt"], fmt(sl), fmt(done),
                    fmt(r["con_lai"]), f"{pc:.0f}%"]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=widths[i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            pb = ctk.CTkProgressBar(hd, width=110, height=8, corner_radius=4)
            pb.set(min(1.0, max(0.0, pc / 100)))
            pb.grid(row=idx + 1, column=7, padx=(0, 4), sticky="w")

    def _luu_hop_dong(self):
        ma_kh = self._ma_kh_theo_ten(self.hd_kh.get())
        if not ma_kh:
            self._hd_msg.configure(text=t("Vui lòng chọn khách hàng."),
                                   text_color=C_BAD)
            return
        so_hd = self.hd_so.get().strip()
        if not so_hd:
            self._hd_msg.configure(text=t("Thiếu số hợp đồng."),
                                   text_color=C_BAD)
            return
        ma_vt = self.hd_ma.get().strip()
        if not ma_vt:
            self._hd_msg.configure(text=t("Thiếu mã vật tư."),
                                   text_color=C_BAD)
            return
        if not core.ds_vattu(self.con, ma_vt):
            self._hd_msg.configure(
                text=tf("Mã vật tư '{}' không tồn tại.", ma_vt),
                text_color=C_BAD)
            return
        try:
            sl = parse_so_luong(self.hd_sl.get())
            gia = to_float(self.hd_gia.get())
            ngay_ky = ngay_hop_le(self.hd_ky.get())
            ngay_het = ngay_hop_le(self.hd_het.get())
        except ValueError as e:
            self._hd_msg.configure(text=str(e), text_color=C_BAD)
            return
        try:
            core.luu_hop_dong(self.con, so_hd, ma_kh, ma_vt, sl, gia,
                              ngay_ky=ngay_ky, ngay_het_han=ngay_het,
                              nguoi_thao_tac=nguoi_lap_cua(self))
        except Exception as e:
            self._hd_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)
            return
        self._reload_screen()
        self._hd_msg.configure(text=tf("✅ Đã lưu HĐ: {}", so_hd),
                               text_color=C_OK)

    # ==================== 7. BÁO CÁO ====================

    def scr_report(self):
        self.header(t("Báo cáo"), t("Tháng · Quý · Thị phần — chọn năm, xuất PDF"))
        f0 = ctk.CTkFrame(self.main, fg_color="transparent")
        f0.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(f0, text=t("Năm"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=50).pack(side="left")
        cac_nam = self._ds_nam_co_du_lieu()
        self.r_nam = ctk.CTkComboBox(
            f0, values=cac_nam or [str(date.today().year)], width=120,
            height=30, command=lambda _: self._draw_report(self.r_tab.get()))
        self.r_nam.set(str(date.today().year))
        self.r_nam.pack(side="left")
        ctk.CTkButton(f0, text=t("📄 Xuất PDF"), width=130, height=30,
                      command=self._xuat_baocao_pdf).pack(side="right")

        self.r_tab = ctk.CTkSegmentedButton(
            self.main, values=[t("Tháng"), t("Quý"), t("Thị phần")],
            font=ctk.CTkFont(size=12, weight="bold"), fg_color="#e3e9ef",
            selected_color=C_BRAND, selected_hover_color="#12a3af",
            command=lambda v: self._draw_report(v))
        self.r_tab.pack(anchor="w", pady=(0, 10))
        self.r_tab.set(t("Tháng"))
        self.r_box = ctk.CTkFrame(self.main, fg_color="transparent")
        self.r_box.pack(fill="x")
        self._draw_report(t("Tháng"))

    def _ds_nam_co_du_lieu(self):
        """Các năm có dữ liệu bán hàng (query đọc-only duy nhất còn ở tầng GUI
        — nên chuyển thành hàm core.ds_nam() khi refactor core)."""
        rows = self.con.execute(
            "SELECT DISTINCT substr(ngay_phieu,1,4) FROM phieu_giaodich "
            "WHERE ngay_phieu IS NOT NULL AND ngay_phieu != '' "
            "ORDER BY 1 DESC").fetchall()
        return [r[0] for r in rows if r[0] and r[0].isdigit()]

    def _xuat_baocao_pdf(self):
        loai = {t("Tháng"): "m", t("Quý"): "q",
                t("Thị phần"): "s"}.get(self.r_tab.get(), "m")
        try:
            nam = int(self.r_nam.get())
        except ValueError:
            messagebox.showerror(t("Lỗi"), t("Năm không hợp lệ"))
            return
        path = filedialog.asksaveasfilename(
            title=t("Lưu báo cáo PDF"), defaultextension=".pdf",
            initialfile=f"BaoCao_{loai}_{nam}.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        out, loi = pdf_baocao(self.con, loai, nam, path)
        if loi:
            messagebox.showerror(t("Lỗi"), tf("Không xuất được PDF: {}", loi))
            return
        messagebox.showinfo(t("Xuất PDF"), tf("Đã lưu:\n{}", out))

    def _draw_report(self, tab):
        for w in self.r_box.winfo_children():
            w.destroy()
        raw_nam = self.r_nam.get()
        nam = int(raw_nam) if raw_nam.isdigit() else date.today().year

        def _bar_chart(parent, rows, label_fn):
            mx = max((r["doanh_so"] or 0) for r in rows) or 1
            cv = tk.Canvas(parent, height=180, bg="#ffffff",
                           highlightthickness=0)
            cv.pack(fill="x", pady=(0, 10))
            bw, gap, base = 60, 18, 150
            for i, r in enumerate(rows):
                h = int((r["doanh_so"] or 0) / mx * 120)
                x0 = 20 + i * (bw + gap)
                cv.create_rectangle(x0, base - h, x0 + bw, base,
                                    fill=C_BRAND, outline="")
                cv.create_text(x0 + bw // 2, base - h - 8,
                               text=label_fn(r),
                               font=("Segoe UI", 9, "bold"), fill=C_INK)
                cv.create_text(x0 + bw // 2, base + 12,
                               text=money(r["doanh_so"]),
                               font=("Segoe UI", 8), fill=C_MUT)

        if tab == t("Tháng"):
            rows = core.doanh_so_thang(self.con, nam)
            c = self.card(tf("Doanh số theo tháng — {}", nam), parent=self.r_box)
            b = ctk.CTkFrame(c, fg_color="transparent")
            b.pack(fill="x", padx=14, pady=(0, 12))
            if not rows:
                ctk.CTkLabel(b, text=t("Chưa có dữ liệu bán hàng trong năm."),
                             text_color=C_MUT).pack(anchor="w")
                return
            _bar_chart(b, rows, lambda r: str(int(r["thang"])))
            self._bang_don_gian(b, [t("Tháng"), t("Số lượng"), t("Doanh số")],
                                [[tf("Tháng {}", int(r["thang"])),
                                  fmt(r["so_luong"]),
                                  money(r["doanh_so"]) + " ₫"] for r in rows],
                                [80, 100, 150])
        elif tab == t("Quý"):
            q = {}
            for r in core.doanh_so_thang(self.con, nam):
                qi = (int(r["thang"]) - 1) // 3 + 1
                d = q.setdefault(qi, {"so_luong": 0, "doanh_so": 0})
                d["so_luong"] += r["so_luong"] or 0
                d["doanh_so"] += r["doanh_so"] or 0
            rows = [{"quy": k, **v} for k, v in sorted(q.items())]
            c = self.card(tf("Doanh số theo quý — {}", nam), parent=self.r_box)
            b = ctk.CTkFrame(c, fg_color="transparent")
            b.pack(fill="x", padx=14, pady=(0, 12))
            if not rows:
                ctk.CTkLabel(b, text=t("Chưa có dữ liệu bán hàng trong năm."),
                             text_color=C_MUT).pack(anchor="w")
                return
            _bar_chart(b, rows, lambda r: tf("Quý {}", r["quy"]))
            self._bang_don_gian(b, [t("Quý"), t("Số lượng"), t("Doanh số")],
                                [[tf("Quý {}", r["quy"]), fmt(r["so_luong"]),
                                  money(r["doanh_so"]) + " ₫"] for r in rows],
                                [80, 100, 150])
        else:
            rows = core.thi_phan(self.con, nam)
            c = self.card(tf("Thị phần nội bộ — {}", nam), parent=self.r_box)
            b = ctk.CTkFrame(c, fg_color="transparent")
            b.pack(fill="x", padx=14, pady=(0, 12))
            if not rows:
                ctk.CTkLabel(b, text=t("Chưa có dữ liệu."),
                             text_color=C_MUT).pack(anchor="w")
                return
            self._bang_don_gian(
                b, [t("Khách hàng"), t("Thị phần"), t("Doanh số")],
                [[r["ten_kh"][:30], f"{r['ti_le']:.1f}%",
                  money(r["doanh_so"] or 0) + " ₫"] for r in rows[:10]],
                [250, 80, 150])

    def _bang_don_gian(self, parent, cols, rows, widths):
        hd = ctk.CTkFrame(parent, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate(cols):
            ctk.CTkLabel(hd, text=col_name,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(6, 2), sticky="w")
        for idx, vals in enumerate(rows):
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=widths[i]).grid(
                    row=idx + 1, column=i, padx=4, pady=2, sticky="w")

    # ==================== 9. KÝ GỬI ====================

    def scr_kygui(self):
        self.header(t("Ký gửi"),
                    t("Quản lý hàng ký gửi — xuất ký gửi cho khách hàng"))
        c = self.card(t("Phiếu ký gửi"))
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Khách hàng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=0, column=0, sticky="w", pady=5)
        self.kg_kh = ctk.CTkComboBox(
            f, values=[k["ten_kh"] for k in self._kh_cache], width=380,
            height=32)
        self.kg_kh.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Loại phiếu"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=1, column=0, sticky="w", pady=5)
        self.kg_loai = ctk.CTkComboBox(f, values=["KYGUI", "XUAT_KYGUI"],
                                       width=200, height=32)
        self.kg_loai.set("KYGUI")
        self.kg_loai.grid(row=1, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Ngày"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=2, column=0, sticky="w", pady=5)
        self.kg_ngay = ctk.CTkEntry(f, width=160, height=32)
        self.kg_ngay.insert(0, date.today().isoformat())
        self.kg_ngay.grid(row=2, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.kg_ngay)).grid(
            row=2, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Mã vật tư"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=3, column=0, sticky="w", pady=5)
        self.kg_ma = ctk.CTkEntry(f, width=240, height=32,
                                  placeholder_text=t("Nhập mã VT…"))
        self.kg_ma.grid(row=3, column=1, sticky="w", pady=5)
        self.kg_ma.bind("<KeyRelease>", self._on_kygui_typed)

        ctk.CTkLabel(f, text=t("Số lượng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=4, column=0, sticky="w", pady=5)
        self.kg_sl = ctk.CTkEntry(f, width=120, height=32)
        self.kg_sl.insert(0, "1")
        self.kg_sl.grid(row=4, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Khoa nhận"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=5, column=0, sticky="w", pady=5)
        self.kg_khoa = ctk.CTkEntry(f, width=240, height=32,
                                    placeholder_text=t("VD: Hồi sức ngoại"))
        self.kg_khoa.grid(row=5, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Ghi chú"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=6, column=0, sticky="w", pady=5)
        self.kg_gc = ctk.CTkEntry(
            f, width=380, height=32,
            placeholder_text=t("VD: Ký gửi theo HĐ số …"))
        self.kg_gc.grid(row=6, column=1, sticky="w", pady=5)

        self.kg_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                   text_color=C_MUT)
        self.kg_msg.grid(row=7, column=1, sticky="w", pady=(8, 0))

        ctk.CTkButton(f, text=t("Lưu phiếu ký gửi"), height=36,
                      fg_color=C_BRAND, hover_color="#12a3af",
                      command=self._luu_kygui).grid(
            row=8, column=1, sticky="w", pady=(10, 0))

        # --- tồn ký gửi ---
        c2 = self.card(t("Tồn kho ký gửi"))
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        rows_ton = core.ton_kho_kygui(self.con)
        if not rows_ton:
            ctk.CTkLabel(b2, text=t("Chưa có hàng ký gửi."),
                         text_color=C_MUT).pack(anchor="w")
        else:
            widths = [200, 90, 300, 50, 90]
            hd = ctk.CTkFrame(b2, fg_color="#fafcfd", corner_radius=8)
            hd.pack(fill="x")
            for i, col_name in enumerate([t("Khách hàng"), t("Mã VT"),
                                          t("Tên vật tư"), t("ĐVT"),
                                          t("Tồn ký gửi")]):
                ctk.CTkLabel(hd, text=col_name,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=C_MUT, width=widths[i]).grid(
                    row=0, column=i, padx=4, pady=(8, 2), sticky="w")
            for idx, r in enumerate(rows_ton):
                vals = [r["ten_kh"], r["ma_vt"], r["ten_vt"][:40], r["dvt"],
                        fmt(r["ton_kygui"])]
                for i, v in enumerate(vals):
                    ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                                 text_color=C_INK, width=widths[i]).grid(
                        row=idx + 1, column=i, padx=4, pady=3, sticky="w")

        # --- lịch sử phiếu ký gửi ---
        c3 = self.card(t("Lịch sử phiếu ký gửi"))
        b3 = ctk.CTkFrame(c3, fg_color="transparent")
        b3.pack(fill="x", padx=14, pady=(0, 12))
        rows_kygui = core.ds_phieu(self.con, loai="KYGUI", limit=10)
        rows_xuat = core.ds_phieu(self.con, loai="XUAT_KYGUI", limit=10)
        if not rows_kygui and not rows_xuat:
            ctk.CTkLabel(b3, text=t("Chưa có phiếu ký gửi nào."),
                         text_color=C_MUT).pack(anchor="w")
        else:
            all_rows = ([(r, t("Ký gửi")) for r in rows_kygui]
                        + [(r, t("Xuất ký gửi")) for r in rows_xuat])
            self._bang_don_gian(
                b3,
                [t("Số phiếu"), t("Loại"), t("Ngày"), t("Mã VT"),
                 t("Tên VT"), t("SL")],
                [[r["so_phieu"], loai, r["ngay_phieu"], r["ma_vt"],
                  (r["ten_vt"] or "")[:38], fmt(r["so_luong"])]
                 for r, loai in all_rows],
                [110, 110, 90, 90, 280, 50])

    def _on_kygui_typed(self, _):
        q = self.kg_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if rows:
            v = rows[0]
            self.kg_msg.configure(text=f"{v['ma_vt']} — {v['ten_vt'][:44]}",
                                  text_color=C_OK)
        else:
            self.kg_msg.configure(text=t("Không tìm thấy mã vật tư."),
                                  text_color=C_BAD)

    def _luu_kygui(self):
        ma_kh = self._ma_kh_theo_ten(self.kg_kh.get())
        if not ma_kh:
            self.kg_msg.configure(text=t("Vui lòng chọn khách hàng."),
                                  text_color=C_BAD)
            return
        q = self.kg_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if not rows:
            self.kg_msg.configure(text=t("Chọn mã vật tư hợp lệ."),
                                  text_color=C_BAD)
            return
        v = rows[0]
        try:
            sl = parse_so_luong(self.kg_sl.get())
            ngay = ngay_hop_le(self.kg_ngay.get()) or date.today().isoformat()
        except ValueError as e:
            self.kg_msg.configure(text=str(e), text_color=C_BAD)
            return
        try:
            sp = core.ghi_phieu_kygui(
                self.con, self.kg_loai.get(), ngay, v["ma_vt"], sl,
                ma_kh=ma_kh, khoa_nhan=self.kg_khoa.get().strip(),
                nguoi_lap=nguoi_lap_cua(self),
                ghi_chu=self.kg_gc.get().strip())
        except ValueError as e:
            self.kg_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)
            return
        self._reload_screen()
        self.kg_msg.configure(
            text=tf("Đã lưu {} — tồn kho ký gửi đã cập nhật.", sp),
            text_color=C_OK)

    # ==================== 10. HÓA ĐƠN TRƯỚC ====================

    def scr_hoadontruoc(self):
        self.header(t("Hóa đơn trước"),
                    t("Xuất hàng trước, xuất hóa đơn sau — theo dõi tiến độ giao"))
        c = self.card(t("Phiếu xuất hóa đơn trước"))
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Ngày xuất"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=0, column=0, sticky="w", pady=5)
        self.hd_ngay = ctk.CTkEntry(f, width=160, height=32)
        self.hd_ngay.insert(0, date.today().isoformat())
        self.hd_ngay.grid(row=0, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.hd_ngay)).grid(
            row=0, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Mã vật tư"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=1, column=0, sticky="w", pady=5)
        self.hd_ma = ctk.CTkEntry(f, width=240, height=32,
                                  placeholder_text=t("Nhập mã VT…"))
        self.hd_ma.grid(row=1, column=1, sticky="w", pady=5)
        self.hd_ma.bind("<KeyRelease>", self._on_hoadon_typed)

        ctk.CTkLabel(f, text=t("Số lượng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=2, column=0, sticky="w", pady=5)
        self.hd_sl = ctk.CTkEntry(f, width=120, height=32)
        self.hd_sl.insert(0, "1")
        self.hd_sl.grid(row=2, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Khách hàng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=3, column=0, sticky="w", pady=5)
        self.hd_kh = ctk.CTkComboBox(
            f, values=[k["ten_kh"] for k in self._kh_cache], width=380,
            height=32)
        self.hd_kh.grid(row=3, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Số hóa đơn *"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=4, column=0, sticky="w", pady=5)
        self.hd_so = ctk.CTkEntry(f, width=240, height=32,
                                  placeholder_text="VD: 001/2026/HD")
        self.hd_so.grid(row=4, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Số hợp đồng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=5, column=0, sticky="w", pady=5)
        self.hd_hd = ctk.CTkEntry(f, width=240, height=32,
                                  placeholder_text="VD: 04-21/BVLKTW-CV")
        self.hd_hd.grid(row=5, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Ghi chú"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=6, column=0, sticky="w", pady=5)
        self.hd_gc = ctk.CTkEntry(
            f, width=380, height=32,
            placeholder_text=t("VD: Xuất trước theo yêu cầu…"))
        self.hd_gc.grid(row=6, column=1, sticky="w", pady=5)

        self.hd_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                   text_color=C_MUT)
        self.hd_msg.grid(row=7, column=1, sticky="w", pady=(8, 0))

        ctk.CTkButton(f, text=t("Lưu"), height=36, fg_color=C_BRAND,
                      hover_color="#12a3af",
                      command=self._luu_hoadon).grid(
            row=8, column=1, sticky="w", pady=(10, 0))

        # --- bảng tiến độ ---
        c2 = self.card(t("Tiến độ hóa đơn trước"))
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.tien_do_hoadon_truoc(self.con)
        if not rows:
            ctk.CTkLabel(b2, text=t("Chưa có dữ liệu hóa đơn trước."),
                         text_color=C_MUT).pack(anchor="w")
        else:
            self._bang_don_gian(
                b2,
                [t("Số HĐ"), t("Khách hàng"), t("Mã VT"), t("Tên VT"),
                 t("SL đã xuất"), t("SL đã giao"), t("Còn lại")],
                [[r["so_hoa_don"], r["ten_kh"], r["ma_vt"],
                  (r["ten_vt"] or "")[:38], fmt(r["sl_da_xuat_hd"]),
                  fmt(r["sl_da_giao"]), fmt(r["sl_con_lai"])] for r in rows],
                [110, 200, 90, 280, 80, 80, 60])

    def _on_hoadon_typed(self, _):
        q = self.hd_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if rows:
            v = rows[0]
            self.hd_msg.configure(text=f"{v['ma_vt']} — {v['ten_vt'][:44]}",
                                  text_color=C_OK)
        else:
            self.hd_msg.configure(text=t("Không tìm thấy mã vật tư."),
                                  text_color=C_BAD)

    def _kiem_tra_giao_hoadon(self, ma_vt, so_hoa_don, sl):
        """Chặn GIAO vượt hóa đơn trước — đúng theo (so_hoa_don, ma_vt).

        Core cũ cộng gộp xuyên mặt hàng (giao B trên hóa đơn của A vẫn lọt).
        Kiểm tra qua view v_xuat_hoadon_truoc: mặt hàng chưa có dòng hóa đơn
        nào -> chưa được giao theo hóa đơn đó; đã giao + sắp giao > đã xuất
        hóa đơn -> chặn. Trả về None nếu OK, hoặc chuỗi lỗi.
        """
        for r in core.tien_do_hoadon_truoc(self.con):
            if r["so_hoa_don"] == so_hoa_don and r["ma_vt"] == ma_vt:
                da_xuat = r["sl_da_xuat_hd"] or 0
                da_giao = r["sl_da_giao"] or 0
                if da_giao + sl > da_xuat:
                    return tf(
                        "Giao {} vượt số đã xuất hóa đơn {} của {} "
                        "(hóa đơn {}, đã giao {}).", fmt(sl), fmt(da_xuat),
                        ma_vt, so_hoa_don, fmt(da_giao))
                return None
        return tf("Mặt hàng {} chưa được xuất hóa đơn trước cho hóa đơn {}.",
                  ma_vt, so_hoa_don)

    def _luu_hoadon(self):
        ma_kh = self._ma_kh_theo_ten(self.hd_kh.get())
        if not ma_kh:
            self.hd_msg.configure(text=t("Vui lòng chọn khách hàng."),
                                  text_color=C_BAD)
            return
        q = self.hd_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if not rows:
            self.hd_msg.configure(text=t("Chọn mã vật tư hợp lệ."),
                                  text_color=C_BAD)
            return
        v = rows[0]
        so_hd = self.hd_so.get().strip()
        if not so_hd:
            self.hd_msg.configure(text=t("Số hóa đơn là bắt buộc."),
                                  text_color=C_BAD)
            return
        try:
            sl = parse_so_luong(self.hd_sl.get())
            ngay = ngay_hop_le(self.hd_ngay.get()) or date.today().isoformat()
        except ValueError as e:
            self.hd_msg.configure(text=str(e), text_color=C_BAD)
            return
        try:
            sp = core.xuat_hoadon_truoc(
                self.con, ngay, v["ma_vt"], sl, ma_kh=ma_kh,
                so_hoa_don=so_hd, so_hop_dong=self.hd_hd.get().strip(),
                nguoi_lap=nguoi_lap_cua(self),
                ghi_chu=self.hd_gc.get().strip())
        except ValueError as e:
            self.hd_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)
            return
        self._reload_screen()
        self.hd_msg.configure(
            text=tf("Đã lưu {} — tiến độ hóa đơn đã cập nhật.", sp),
            text_color=C_OK)

    # ==================== 11. LỊCH SỬ KHÁCH HÀNG ====================

    def scr_lichsu(self):
        self.header(t("Lịch sử khách hàng"),
                    t("Tra cứu giao dịch theo khách hàng & khoảng thời gian"))
        c = self.card(t("Tìm kiếm"))
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Khách hàng"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=0, column=0, sticky="w", pady=5)
        self.ls_kh = ctk.CTkComboBox(
            f, values=[k["ten_kh"] for k in self._kh_cache], width=380,
            height=32)
        self.ls_kh.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Từ ngày"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=1, column=0, sticky="w", pady=5)
        self.ls_tu = ctk.CTkEntry(f, width=160, height=32,
                                  placeholder_text="YYYY-MM-DD")
        self.ls_tu.grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.ls_tu)).grid(
            row=1, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Đến ngày"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(
            row=2, column=0, sticky="w", pady=5)
        self.ls_den = ctk.CTkEntry(f, width=160, height=32,
                                   placeholder_text="YYYY-MM-DD")
        self.ls_den.grid(row=2, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.ls_den)).grid(
            row=2, column=2, sticky="w", padx=(4, 0))

        self.ls_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                   text_color=C_MUT)
        self.ls_msg.grid(row=3, column=1, sticky="w", pady=(8, 0))

        ctk.CTkButton(f, text=t("Tìm"), height=36, fg_color=C_BRAND,
                      hover_color="#12a3af",
                      command=self._tim_lichsu).grid(row=4, column=1,
                                                     sticky="w", pady=(10, 0))

        c2 = self.card(t("Kết quả"))
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        self.ls_box = b2

    def _tim_lichsu(self):
        ma_kh = self._ma_kh_theo_ten(self.ls_kh.get())
        if not ma_kh:
            self.ls_msg.configure(text=t("Vui lòng chọn khách hàng."),
                                  text_color=C_BAD)
            return
        try:
            tu = ngay_hop_le(self.ls_tu.get())
            den = ngay_hop_le(self.ls_den.get())
        except ValueError as e:
            self.ls_msg.configure(text=str(e), text_color=C_BAD)
            return
        if tu and den and tu > den:
            self.ls_msg.configure(
                text=t("'Từ ngày' phải trước 'Đến ngày'."), text_color=C_BAD)
            return
        try:
            rows = core.lich_su_khachhang(self.con, ma_kh, tu, den)
        except Exception as e:
            self.ls_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)
            return
        for w in self.ls_box.winfo_children():
            w.destroy()
        if not rows:
            ctk.CTkLabel(self.ls_box, text=t("Không tìm thấy giao dịch nào."),
                         text_color=C_MUT,
                         font=ctk.CTkFont(size=12)).pack(anchor="w", pady=8)
            self.ls_msg.configure(text=t("Không tìm thấy giao dịch nào."),
                                  text_color=C_MUT)
            return
        # ĐÚNG tên cột của view: loai_phieu / ngay_phieu (bản cũ đọc
        # r["loai"]/r["ngay"] -> IndexError, màn này chưa từng chạy được)
        self._bang_don_gian(
            self.ls_box,
            [t("Số phiếu"), t("Loại"), t("Ngày"), t("Mã VT"), t("Tên VT"),
             t("SL"), t("Đơn giá"), t("Thành tiền")],
            [[r["so_phieu"],
              t(LOAI_PHIEU_LABEL.get(r["loai_phieu"], r["loai_phieu"])),
              r["ngay_phieu"], r["ma_vt"], (r["ten_vt"] or "")[:36],
              fmt(r["so_luong"]), fmt(r["don_gia"]), fmt(r["thanh_tien"])]
             for r in rows],
            [110, 100, 90, 90, 250, 50, 100, 110])
        self.ls_msg.configure(
            text=tf("Tìm thấy {} giao dịch.", len(rows)), text_color=C_OK)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # Log cạnh DB (thư mục đã được đảm bảo ghi được), KHÔNG cạnh
    # sys.executable (chạy từ source sẽ ghi vào thư mục cài Python).
    LOG_FILE = os.path.join(os.path.dirname(DB_PATH) or ".", "app.log")

    def log(msg):
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except OSError:
            pass

    log("=== MAIN START ===")
    if not _THEME_OK:
        log("[canh bao] neutral_theme.json khong nap duoc - dung theme mac dinh"
            " (them file vao datas trong .spec de het canh bao nay)")
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except OSError:
            pass
        try:
            messagebox.showerror(
                "QLVT Y tế",
                f"Lỗi khởi động: {e}\n\nChi tiết trong: {LOG_FILE}")
        except Exception:
            pass
        sys.exit(1)
    log("=== MAIN END ===")
