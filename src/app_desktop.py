"""
app_desktop.py — Giao diện DESKTOP (CustomTkinter) cho QLVY Y tế

Chạy:  python app_desktop.py

Dùng chung lõi nghiệp vụ qlvt_core với bản web → 2 giao diện, 1 bộ nghiệp vụ.
"""
import os
import sys
import tkinter as tk
from datetime import date

import customtkinter as ctk
import tkinter.messagebox as messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qlvt_core as core
from i18n import t, tf, set_lang, get_lang

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

# Khi đóng gói PyInstaller (onefile), __file__ trỏ tới thư mục tạm _MEIPASS.
# DB phải nằm cạnh file exe (thư mục thực thi) để dữ liệu bền vững giữa các lần chạy.
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_APP_DIR, "qlvt.db")

# Tên hiển thị của vai trò (dùng cho cả UI lẫn báo cáo)
TEN_VAI_TRO = {
    "admin": "Quản trị",
    "kinhdoanh": "Kinh doanh",
    "ketoan": "Kế toán",
    "kho": "Kho",
    "nhanvien": "Nhân viên",
}


def ten_vai_tro(v):
    return TEN_VAI_TRO.get(v, v)


def nguoi_lap_cua(app):
    """Tên người lập phiếu để ghi vào sổ. Lấy từ tài khoản đang đăng nhập;
    rơi về 'Hệ thống' nếu không xác định được — không hard-code tên cứng."""
    if getattr(app, "user", None):
        return app.user.get("ten_hien_thi") or app.user.get("username") or ""
    return ""

# màu
C_BG = "#f4f6f9"
C_CARD = "#ffffff"
C_BRAND = "#0e7c86"
C_OK = "#1a9c5b"
C_WARN = "#c77a00"
C_BAD = "#d1462f"
C_INK = "#0f2233"
C_MUT = "#5a6b7d"


def fmt(n):
    try:
        return f"{float(n or 0):,.0f}"
    except Exception:
        return str(n)


def money(n):
    n = float(n or 0)
    if abs(n) >= 1e9:
        return tf("{:,.2f} tỷ", n/1e9)
    if abs(n) >= 1e6:
        return f"{n/1e6:,.1f} tr"
    return f"{n:,.0f}"


def to_float(s):
    """Parse số nhập từ bàn phím. Chấp nhận cả '15099000', '15.099.000',
    '15,099,000' — vì người dùng hay dùng dấu phẩy/chấm phân cách hàng nghìn."""
    if s is None:
        return 0.0
    t = str(s).strip().replace(",", "").replace(".", "").replace(" ", "")
    if not t or t in ("-", "+"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(t("QLVT Y tế — Quản lý vật tư y tế"))
        self.geometry("1280x760")
        self.configure(fg_color=C_BG)
        self.con, self.is_new = core.ensure_db(DB_PATH)
        # Nâng cấp bảng users/sessions cho DB cũ rồi đảm bảo luôn có admin
        try:
            core.ensure_auth_schema(self.con)
        except Exception as e:
            print(tf("[canh bao] nâng cấp schema auth: {}", e))
        self.cart = []
        self.cart_nhap = []
        self.user = None          # tài khoản đang đăng nhập (dict)
        self._nav_items = []      # menu hiện tại, lọc theo quyền
        self.nav = {}
        self._login_dlg = None
        self._token = None
        # Chưa đăng nhập thì KHÔNG dựng sidebar/topbar — chỉ hiện modal đăng nhập
        self._hien_man_hinh_dang_nhap()
        # Heartbeat để giữ event loop sống (fix CTkToplevel không hiển thị trên frozen build)
        self._heartbeat_job = None
        self._heartbeat()

    def _heartbeat(self):
        """Gọi lại mỗi 200ms để event loop không thoát sớm khi chỉ có timer events."""
        self._heartbeat_job = self.after(200, self._heartbeat)

    # ==================== ĐĂNG NHẬP / ĐĂNG XUẤT ====================

    def _cap_nhat_topbar_user(self):
        """Cập nhật avatar + tên + vai trò trên top bar sau khi đăng nhập."""
        if not self.user:
            self.who_name.configure(text="")
            self.who_role.configure(text="")
            self.avatar.configure(text="QL")
            return
        name = self.user.get("ten_hien_thi") or self.user.get("username") or "Người dùng"
        role = ten_vai_tro(self.user.get("vai_tro", ""))
        self.who_name.configure(text=name)
        self.who_role.configure(text=role)
        # Avatar: 2 chữ cái đầu của tên
        parts = name.split()
        initials = "".join(p[0] for p in parts[:2]).upper()
        self.avatar.configure(text=initials or "QL")

    def dang_xuat(self):
        """Đăng xuất: xoá phiên (nếu có) và quay lại màn hình đăng nhập."""
        if not messagebox.askyesno(t("Đăng xuất"), t("Bạn muốn đăng xuất khỏi phần mềm?")):
            return
        if getattr(self, "_token", None):
            try:
                core.xoa_session(self.con, self._token)
            except Exception:
                pass
        self._token = None
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

    def _doi_ngon_ngu(self, code: str):
        """Đổi ngôn ngữ giao diện và rebuild UI."""
        from i18n import set_lang
        set_lang(code)
        # Rebuild topbar text
        self._cap_nhat_topbar_user()
        # Rebuild current screen
        self.show("home")

    def _doi_ngon_ngu_login(self, code: str, dlg):
        """Đổi ngôn ngữ ở màn hình login — destroy & rebuild dialog."""
        from i18n import set_lang
        set_lang(code)
        # Reload login dialog with new language
        self._hien_man_hinh_dang_nhap()

    # ==================== KIỂM QUYỀN ====================
    def co_quyen(self, chuc_nang):
        """True nếu tài khoản hiện tại được phép dùng chức năng."""
        if not self.user:
            return False
        return core.phan_quyyen(self.user["vai_tro"], chuc_nang)

    def tu_choi(self, ten_chuc_nang):
        """Hành động dựng phòng khi gọi thẳng 1 màn hình không được phép."""
        messagebox.showerror(
            "Không đủ quyền",
            tf("Tài khoản '{}' (vai trò {}) không được phép: {}.", self.user['username'], ten_vai_tro(self.user['vai_tro']), ten_chuc_nang))
        self.show("home")

    # ==================== KHUNG ====================
    # Thông tin màn hình cho breadcrumb (mockup style)
    SCREEN_INFO = {
        "home":   ("Tổng quan", "Doanh số · tồn kho · cảnh báo"),
        "sale":   ("Bán hàng", "Xuất kho · phiếu giao hàng PDF"),
        "in":     ("Nhập kho", "Nhập vật tư từ nhà cung cấp"),
        "stock":  ("Tồn kho", "Danh mục vật tư & hạn sử dụng"),
        "cust":   ("Khách hàng", "Bệnh viện · phòng khám · kho"),
        "contract": ("Hợp đồng thầu", "Tiến độ thực hiện hợp đồng"),
        "report": ("Báo cáo", "Doanh số · thị phần · xuất file"),
        "kygui":  ("Ký gửi", "Quản lý hàng ký gửi"),
        "hoadontruoc": ("Hóa đơn trước", "Quản lý hóa đơn chờ"),
        "lichsu": ("Lịch sử KH", "Tra cứu lịch sử giao dịch"),
        "users":  ("Tài khoản", "Tạo, sửa, khoá tài khoản và phân quyền"),
    }

    def _build(self):
        # sidebar
        sb = ctk.CTkFrame(self, width=210, fg_color="#0b2530", corner_radius=0)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        ctk.CTkLabel(sb, text="QLVT Y TẾ", font=ctk.CTkFont(size=17, weight="bold"),
                     text_color="#ffffff").pack(pady=(22, 2), padx=16, anchor="w")
        ctk.CTkLabel(sb, text=t("Vật tư tiêu hao & TBYT"), font=ctk.CTkFont(size=10),
                     text_color="#7fa3ad").pack(pady=(0, 18), padx=16, anchor="w")

        # Menu lọc theo quyền: mỗi mục gắn 1 chức năng.
        # 'xem' = chỉ cần quyền đọc; admin luôn được.
        items = [
            ("home", "📊", "Tổng quan", "xem"),
            ("sale", "🧾", "Bán hàng", "xuat"),
            ("in", "📥", "Nhập kho", "nhap"),
            ("stock", "📦", "Tồn kho", "xem"),
            ("cust", "🏥", "Khách hàng", "khachhang"),
            ("contract", "📑", "Hợp đồng thầu", "hopdong"),
            ("report", "📈", "Báo cáo", "baocao"),
            ("kygui", "📦", "Ký gửi", "kygui"),
            ("hoadontruoc", "📄", "Hóa đơn trước", "hoadon_truoc"),
            ("lichsu", "🔍", "Lịch sử KH", "lichsu"),
        ]
        if self.user and self.user["vai_tro"] == "admin":
            items.append(("users", "👥", "Tài khoản", "admin"))
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

        # Khối nút đăng xuất + đổi mật khẩu (chỉ còn ở sidebar footer)
        uf = ctk.CTkFrame(sb, fg_color="#123a47", corner_radius=8)
        uf.pack(side="bottom", fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(uf, text=t("🔒 Đăng xuất"), height=30, font=ctk.CTkFont(size=11),
                      fg_color="transparent", text_color="#b9ced6",
                      hover_color="#d1462f", command=self.dang_xuat).pack(
            fill="x", padx=6, pady=(8, 4))
        ctk.CTkButton(uf, text=t("🔑 Đổi mật khẩu"), height=30, font=ctk.CTkFont(size=11),
                      fg_color="transparent", text_color="#b9ced6",
                      hover_color="#12a3af", command=self._doi_mat_khau).pack(
            fill="x", padx=6, pady=(0, 8))

        ctk.CTkLabel(sb, text=t("Phiên bản desktop 1.1"),
                     font=ctk.CTkFont(size=9), text_color="#5d7f8a").pack(
            side="bottom", pady=6)

        # Top bar (mockup style): breadcrumb left, user avatar/name/role right
        self.topbar = ctk.CTkFrame(self, fg_color=C_CARD, height=58, corner_radius=0)
        self.topbar.pack(side="top", fill="x", padx=(210, 0))  # offset for sidebar
        self.topbar.pack_propagate(False)
        tb = ctk.CTkFrame(self.topbar, fg_color="transparent")
        tb.pack(fill="both", expand=True, padx=22, pady=0)

        # Left: breadcrumb
        self.tb_sub = ctk.CTkLabel(tb, text="", font=ctk.CTkFont(size=11),
                                    text_color=C_MUT, anchor="w")
        self.tb_sub.pack(fill="x")
        self.tb_title = ctk.CTkLabel(tb, text="", font=ctk.CTkFont(size=16, weight="bold"),
                                      text_color=C_INK, anchor="w")
        self.tb_title.pack(fill="x")

        # Right: user avatar + name + role
        right = ctk.CTkFrame(tb, fg_color="transparent")
        right.pack(side="right", fill="y")

        # Language selector
        lang_frame = ctk.CTkFrame(right, fg_color="transparent")
        lang_frame.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(lang_frame, text=t("Ngôn ngữ"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT).pack(side="left", padx=(0, 4))
        self.lang_var = ctk.StringVar(value="vi")
        lang_combo = ctk.CTkComboBox(lang_frame, values=["vi", "en"],
                                      variable=self.lang_var, width=60, height=28,
                                      font=ctk.CTkFont(size=11),
                                      command=lambda v: self._doi_ngon_ngu(v))
        lang_combo.pack(side="left")

        self.avatar = ctk.CTkLabel(right, text="QL", font=ctk.CTkFont(size=12, weight="bold"),
                                   text_color=C_BRAND, fg_color="#e6f5f6",
                                   width=30, height=30, corner_radius=15)
        self.avatar.pack(side="left", padx=(0, 9))
        self.who = ctk.CTkFrame(right, fg_color="transparent")
        self.who.pack(side="left", fill="y")
        self.who_name = ctk.CTkLabel(self.who, text="", font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color=C_INK, anchor="w")
        self.who_name.pack(anchor="w")
        self.who_role = ctk.CTkLabel(self.who, text="", font=ctk.CTkFont(size=10),
                                     text_color=C_MUT, anchor="w")
        self.who_role.pack(anchor="w")

        # main
        self.main = ctk.CTkScrollableFrame(self, fg_color=C_BG)
        self.main.pack(side="left", fill="both", expand=True, padx=14, pady=14)

    def show(self, key):
        # Chặn ở tầng điều hướng: gõ thẳng scr_xxx() cũng phải bị chặn
        quyen = dict((k, q) for k, _, _, q in self._nav_items).get(key, "xem")
        if key == "users" and (not self.user or self.user["vai_tro"] != "admin"):
            self.tu_choi("Quản lý tài khoản")
            return
        if not self.user:
            self._hien_man_hinh_dang_nhap()
            return
        if not self.co_quyen(quyen):
            self.tu_choi(tf("màn hình {}", key))
            return
        for k, b in self.nav.items():
            b.configure(fg_color=C_BRAND if k == key else "transparent",
                        text_color="#ffffff" if k == key else "#b9ced6")
        for w in self.main.winfo_children():
            w.destroy()
        getattr(self, f"scr_{key}")()

        # Cập nhật top bar breadcrumb
        title, sub = self.SCREEN_INFO.get(key, (key, ""))
        self.tb_title.configure(text=title)
        self.tb_sub.configure(text=sub)

    # ==================== TÀI KHOẢN (chỉ admin) ====================
    def scr_users(self):
        self.header("Tài khoản", "Tạo, sửa, khoá tài khoản và phân quyền")
        self.u_msg = ctk.CTkLabel(self.main, text="", font=ctk.CTkFont(size=11))
        self.u_msg.pack(anchor="w", pady=(0, 8))

        c = self.card("Thêm tài khoản mới")
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        def field(row, label, value="", width=240):
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C_MUT, width=150).grid(row=row, column=0, sticky="w", pady=5)
            e = ctk.CTkEntry(f, width=width, height=30)
            if value:
                e.insert(0, value)
            e.grid(row=row, column=1, sticky="w", pady=5)
            return e

        self.u_ten = field(0, "Tên đăng nhập *")
        self.u_mk = field(1, "Mật khẩu *")
        self.u_mk.configure(show="●")
        self.u_hien_thi = field(2, "Tên hiển thị *")
        self.u_email = field(3, "Email")
        ctk.CTkLabel(f, text=t("Vai trò"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=150).grid(row=4, column=0, sticky="w", pady=5)
        self.u_vai = ctk.CTkComboBox(f, width=240, height=30,
                                      values=[f"{k} — {ten_vai_tro(k)}"
                                              for k in core.VAI_TRO],
                                      state="readonly")
        self.u_vai.set("kho — Kho")
        self.u_vai.grid(row=4, column=1, sticky="w", pady=5)
        ctk.CTkLabel(f, text=t("Phòng ban"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=150).grid(row=5, column=0, sticky="w", pady=5)
        self.u_khoa = ctk.CTkEntry(f, width=240, height=30)
        self.u_khoa.grid(row=5, column=1, sticky="w", pady=5)
        self.u_doi_mk = ctk.CTkCheckBox(f, text=t("Bắt đổi mật khẩu ở lần đăng nhập đầu"),
                                         font=ctk.CTkFont(size=11))
        self.u_doi_mk.grid(row=6, column=1, sticky="w", pady=(4, 0))
        ctk.CTkButton(f, text=t("Thêm tài khoản"), height=34, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._them_user).grid(
            row=7, column=1, sticky="w", pady=(10, 0))

        # bảng danh sách
        c2 = self.card("Danh sách tài khoản")
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        self.u_box = b2
        self._load_users()

    def _load_users(self):
        for w in self.u_box.winfo_children():
            w.destroy()
        rows = core.ds_users(self.con)
        cols = ["ID", "Tên đăng nhập", "Tên hiển thị", "Vai trò", "Phòng ban",
                "Email", "Trạng thái", "Đăng nhập cuối", "Thao tác"]
        widths = [36, 130, 160, 100, 80, 170, 80, 140, 190]
        for i, col_name in enumerate(cols):
            ctk.CTkLabel(self.u_box, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=widths[i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        if not rows:
            ctk.CTkLabel(self.u_box, text=t("Chưa có tài khoản nào."),
                         text_color=C_MUT).grid(row=1, column=0, columnspan=9, pady=10)
            return
        for idx, r in enumerate(rows):
            la_admin = (r["username"] == "admin")
            st = "Đang khoá" if r["hoat_dong"] == 0 else "Hoạt động"
            st_cl = C_BAD if r["hoat_dong"] == 0 else C_OK
            vals = [str(r["id"]), r["username"], r["ten_hien_thi"],
                    ten_vai_tro(r["vai_tro"]), r["khoa"] or "—",
                    r["email"] or "—"]
            for i, v in enumerate(vals):
                ctk.CTkLabel(self.u_box, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=widths[i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            ctk.CTkLabel(self.u_box, text=st, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=st_cl, width=widths[6]).grid(
                row=idx + 1, column=6, padx=4, pady=3, sticky="w")
            ctk.CTkLabel(self.u_box, text=r["lan_cuoi_dang_nhap"] or "Chưa đăng nhập",
                         font=ctk.CTkFont(size=10), text_color=C_MUT,
                         width=widths[7]).grid(row=idx + 1, column=7, padx=4, pady=3, sticky="w")
            btns = ctk.CTkFrame(self.u_box, fg_color="transparent")
            btns.grid(row=idx + 1, column=8, padx=4, pady=3, sticky="w")
            ctk.CTkButton(btns, text=t("Sửa"), width=52, height=24,
                          font=ctk.CTkFont(size=10),
                          command=lambda rr=r: self._sua_user(rr)).pack(side="left", padx=2)
            ctk.CTkButton(btns, text=t("Đặt lại MK"), width=82, height=24,
                          font=ctk.CTkFont(size=10),
                          command=lambda rr=r: self._dat_lai_mk(rr)).pack(side="left", padx=2)
            ctk.CTkButton(btns, text=t("Khoá") if r["hoat_dong"] else t("Mở khoá"),
                          width=64, height=24, font=ctk.CTkFont(size=10),
                          fg_color=C_WARN if r["hoat_dong"] else C_OK,
                          hover_color="#a06300" if r["hoat_dong"] else "#157a46",
                          command=lambda rr=r: self._khoa_user(rr)).pack(side="left", padx=2)
            if not la_admin:
                ctk.CTkButton(btns, text=t("Xoá"), width=48, height=24,
                              font=ctk.CTkFont(size=10), fg_color=C_BAD,
                              hover_color="#a83826",
                              command=lambda rr=r: self._xoa_user(rr)).pack(side="left", padx=2)

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
        for e in (self.u_ten, self.u_mk, self.u_hien_thi, self.u_email, self.u_khoa):
            e.delete(0, "end")
        self._bao_user(tf("Đã tạo tài khoản '{}' với vai trò {}.", username, ten_vai_tro(vai)))
        self._load_users()

    def _sua_user(self, r):
        w = ctk.CTkToplevel(self)
        w.title(tf("Sửa tài khoản — {}", r['username']))
        w.geometry("420x380")
        w.configure(fg_color=C_BG)
        fr = ctk.CTkScrollableFrame(w, fg_color=C_BG)
        fr.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(fr, text=tf("Tên đăng nhập: {}", r['username']),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(fr, text=t("Tên hiển thị"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_ten = ctk.CTkEntry(fr, width=360, height=30)
        e_ten.insert(0, r["ten_hien_thi"])
        e_ten.pack(pady=(4, 8))
        ctk.CTkLabel(fr, text="Email", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_email = ctk.CTkEntry(fr, width=360, height=30)
        e_email.insert(0, r["email"] or "")
        e_email.pack(pady=(4, 8))
        ctk.CTkLabel(fr, text=t("Phòng ban"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_khoa = ctk.CTkEntry(fr, width=360, height=30)
        e_khoa.insert(0, r["khoa"] or "")
        e_khoa.pack(pady=(4, 8))
        ctk.CTkLabel(fr, text=t("Vai trò"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w")
        e_vai = ctk.CTkComboBox(fr, width=360, height=30,
                                values=[f"{k} — {ten_vai_tro(k)}" for k in core.VAI_TRO],
                                state="readonly")
        e_vai.set(f"{r['vai_tro']} — {ten_vai_tro(r['vai_tro'])}")
        e_vai.pack(pady=(4, 10))
        msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11))
        msg.pack(anchor="w", pady=(0, 6))

        def _ok():
            vai = e_vai.get().split(" — ")[0]
            try:
                core.sua_user(self.con, r["id"], ten_hien_thi=e_ten.get().strip(),
                              vai_tro=vai, email=e_email.get().strip(),
                              khoa=e_khoa.get().strip(), nguoi_thao_tac=self.user["username"])
            except ValueError as e:
                msg.configure(text=str(e), text_color=C_BAD)
                return
            msg.configure(text=t("Đã lưu."), text_color=C_OK)
            self.after(400, w.destroy)
            self._load_users()
        ctk.CTkButton(fr, text=t("Lưu"), height=34, fg_color=C_BRAND,
                      hover_color="#12a3af", command=_ok).pack(anchor="w")

    def _dat_lai_mk(self, r):
        if r["username"] == "admin" and self.user["username"] != "admin":
            messagebox.showerror(t("Lỗi"), t("Chỉ tài khoản admin được đặt lại mật khẩu admin."))
            return
        w = ctk.CTkToplevel(self)
        w.title(tf("Đặt lại mật khẩu — {}", r['username']))
        w.geometry("400x280")
        w.configure(fg_color=C_BG)
        fr = ctk.CTkFrame(w, fg_color=C_CARD, corner_radius=12)
        fr.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(fr, text=tf("Tài khoản: {}", r['username']),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(16, 10), anchor="w", padx=16)
        ctk.CTkLabel(fr, text=t("Mật khẩu mới"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w", padx=16)
        e1 = ctk.CTkEntry(fr, width=340, height=32, show="●")
        e1.pack(padx=16, pady=4)
        ctk.CTkLabel(fr, text=t("Nhập lại mật khẩu"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(anchor="w", padx=16)
        e2 = ctk.CTkEntry(fr, width=340, height=32, show="●")
        e2.pack(padx=16, pady=4)
        doi_lai = ctk.CTkCheckBox(fr, text=t("Buộc đổi lại mật khẩu ở lần đăng nhập kế"),
                                  font=ctk.CTkFont(size=11))
        doi_lai.select()
        doi_lai.pack(anchor="w", padx=16, pady=(10, 0))
        msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11))
        msg.pack(anchor="w", padx=16, pady=(6, 0))

        def _ok():
            if e1.get() != e2.get():
                msg.configure(text=t("Hai mật khẩu không khớp"), text_color=C_BAD)
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
                      hover_color="#12a3af", command=_ok).pack(padx=16, pady=(12, 16), anchor="w")

    def _khoa_user(self, r):
        if r["username"] == "admin":
            messagebox.showerror(t("Lỗi"), t("Không thể khoá tài khoản admin hệ thống."))
            return
        if r["hoat_dong"]:
            if not messagebox.askyesno("Khoá tài khoản",
                                       tf("Khoá tài khoản '{}'? Người này sẽ không đăng nhập được nữa.", r['username'])):
                return
            try:
                core.sua_user(self.con, r["id"], hoat_dong=0,
                              nguoi_thao_tac=self.user["username"])
                core.don_session(self.con, r["id"])
                self._bao_user(tf("Đã khoá tài khoản '{}'.", r['username']))
            except ValueError as e:
                self._bao_user(str(e), True)
        else:
            try:
                core.sua_user(self.con, r["id"], hoat_dong=1,
                              nguoi_thao_tac=self.user["username"])
                self._bao_user(tf("Đã mở khoá tài khoản '{}'.", r['username']))
            except ValueError as e:
                self._bao_user(str(e), True)
        self._load_users()

    def _xoa_user(self, r):
        if r["username"] == "admin":
            messagebox.showerror(t("Lỗi"), t("Không thể xoá tài khoản admin hệ thống."))
            return
        if not messagebox.askyesno("Xoá tài khoản",
                                   tf("Xoá vĩnh viễn tài khoản '{}'?\nLịch sử phiếu đã lập vẫn được giữ nguyên.", r['username'])):
            return
        try:
            core.xoa_user(self.con, r["id"], nguoi_thao_tac=self.user["username"])
        except ValueError as e:
            self._bao_user(str(e), True)
            return
        self._bao_user(tf("Đã xoá tài khoản '{}'.", r['username']))
        self._load_users()

    def _doi_mat_khau(self):
        """Đổi mật khẩu cho tài khoản đang đăng nhập."""
        if not self.user:
            return
        w = ctk.CTkToplevel(self)
        w.title(t("Đổi mật khẩu"))
        w.geometry("400x320")
        w.configure(fg_color=C_BG)
        fr = ctk.CTkFrame(w, fg_color=C_CARD, corner_radius=12)
        fr.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(fr, text=tf("Tài khoản: {}", self.user['username']),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(16, 10), padx=16, anchor="w")
        ctk.CTkLabel(fr, text=t("Mật khẩu hiện tại"), font=ctk.CTkFont(size=11, weight="bold"),
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
                msg.configure(text=t("Hai mật khẩu mới không khớp"), text_color=C_BAD)
                return
            loi = core.doi_mat_khau(self.con, self.user["id"], e0.get(), e1.get())
            if loi:
                msg.configure(text=loi, text_color=C_BAD)
                return
            # Đổi mật khẩu đá phiên khác → nâng cấp phiên hiện tại
            self.user["phai_doi_mk"] = False
            msg.configure(text=t("Đã đổi mật khẩu."), text_color=C_OK)
            self.after(600, w.destroy)
        ctk.CTkButton(fr, text=t("Đổi mật khẩu"), height=34, fg_color=C_BRAND,
                      hover_color="#12a3af", command=_ok).pack(padx=16, pady=(12, 16), anchor="w")
        e0.focus_set()

    def header(self, title, sub=""):
        f = ctk.CTkFrame(self.main, fg_color="transparent")
        f.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=C_INK).pack(anchor="w")
        if sub:
            ctk.CTkLabel(f, text=sub, font=ctk.CTkFont(size=11),
                         text_color=C_MUT).pack(anchor="w")

    def card(self, title=None, parent=None):
        # parent mặc định là self.main; khi render trong khung riêng (vd: báo cáo,
        # dialog) phải truyền parent để card gắn đúng nơi, không lẫn vào main.
        c = ctk.CTkFrame(parent or self.main, fg_color=C_CARD, corner_radius=12,
                         border_width=1, border_color="#e3e9ef")
        c.pack(fill="x", pady=6)
        if title:
            ctk.CTkLabel(c, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=C_INK).pack(anchor="w", padx=14, pady=(12, 4))
        return c

    # ==================== 1. TỔNG QUAN ====================
    def scr_home(self):
        self.header("Tổng quan", "Bức tranh kinh doanh & cảnh báo trong ngày")
        # Lấy ton_kho 1 lần dùng cho KPI + canh_bao
        tk_ = core.ton_kho(self.con)
        tong_gia_tri = sum(r["gia_tri_ton"] or 0 for r in tk_)
        tong_don_vi = sum(r["ton_kho"] or 0 for r in tk_)
        # canh_bao: truyền ton_kho để tránh query lại
        cb = core.canh_bao_v2(self.con, tk_)
        can_nhap = len(cb["can_nhap"])
        het_han = len(cb["het_han"])
        sap_het = len(cb["sap_het"])

        # Doanh số 24 tháng gần nhất → KPI tháng hiện tại + đồ thị biến động.
        ds24 = core.doanh_so_thang_gan_nhat(self.con, 24)
        cur = ds24[-1] if ds24 else {"nam": date.today().year,
                                    "thang": date.today().month, "doanh_so": 0}
        prev = ds24[-2] if len(ds24) > 1 else None
        chenh = (cur["doanh_so"] or 0) - (prev["doanh_so"] or 0) if prev else 0
        tang = chenh >= 0

        row = ctk.CTkFrame(self.main, fg_color="transparent")
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure((0, 1, 2, 3), weight=1)
        kpis = [
            (tf("Doanh số tháng {}/{}", int(cur['thang']), cur['nam']),
             money(cur["doanh_so"]),
             ("▲ +" if tang else "▼ -") + money(abs(chenh)) + " so với tháng trước",
             C_BRAND),
            ("Giá trị tồn kho", money(tong_gia_tri),
             tf("{} mã vật tư · {} đơn vị", len(tk_), fmt(tong_don_vi)), "#2f6fd1"),
            ("Cần nhập thêm", tf("{} mã", can_nhap),
             "Dưới mức tồn kho tối thiểu", C_WARN),
            ("Hàng sắp hết / đã hết hạn", fmt(sap_het + het_han),
             "Đơn vị cần ưu tiên xuất trước", C_BAD),
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

        # --- Biến động doanh số 24 tháng gần nhất ---
        c = self.card("Biến động doanh số 24 tháng gần nhất")
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(b, text=t("Nguồn: phiếu xuất · tự động tổng hợp"),
                     font=ctk.CTkFont(size=10), text_color=C_MUT).pack(anchor="w")
        if not ds24:
            ctk.CTkLabel(b, text=t("Chưa có dữ liệu bán hàng."),
                         text_color=C_MUT).pack(anchor="w", pady=(0, 8))
        else:
            self._chart_doanh_so(b, ds24)

        # --- Top sản phẩm (trái) | Cảnh báo (phải) ---
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
                         text_color=C_OK, font=ctk.CTkFont(size=13)).pack(anchor="w")
        for x in cb["can_nhap"][:6]:
            self._alert_row(body, "NHẬP THÊM", f"{x['ma_vt']} — {x['ten_vt']}",
                            tf("Thiếu {}", fmt(x['thieu'])), C_WARN)
        for x in cb["het_han"][:4]:
            self._alert_row(body, "HẾT HẠN", f"{x['ma_vt']} — {x['ten_vt']}",
                            tf("{} đơn vị", fmt(x['so_luong'])), C_BAD)
        for x in cb["sap_het"][:4]:
            self._alert_row(body, "<3 THÁNG", f"{x['ma_vt']} — {x['ten_vt']}",
                            tf("{} đơn vị", fmt(x['so_luong'])), C_WARN)

        # --- Top khách hàng ---
        c4 = self.card("Top khách hàng theo doanh số")
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
        c = self.card("Sao lưu dữ liệu")
        bf = ctk.CTkFrame(c, fg_color="transparent")
        bf.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(bf, text=t("Tạo bản backup trước khi cập nhật phần mềm hoặc định kỳ. Khôi phục từ file .db đã sao lưu."),
                     text_color=C_MUT, font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkButton(bf, text=t("📦 Sao lưu ngay"), width=150, height=32,
                      command=self._do_backup).pack(side="right")
        ctk.CTkButton(bf, text=t("♻️ Khôi phục"), width=130, height=32,
                      command=self._do_restore).pack(side="right", padx=(8, 0))

    def _ty_trong(self, parent, pct):
        """Thanh tỷ trọng ngang (6px) kiểu mockup — canvas để rộng chuẩn theo %."""
        pct = max(0.0, min(100.0, float(pct or 0)))
        cv = tk.Canvas(parent, width=300, height=6, bg="#edf1f5",
                       highlightthickness=0)
        cv.pack(fill="x", pady=(2, 0))
        if pct > 0:
            cv.create_rectangle(0, 0, 300 * pct / 100, 6, fill=C_BRAND, outline="")

    def _chart_doanh_so(self, parent, rows):
        """Đồ thị cột doanh số 24 tháng gần nhất — kiểu mockup.

        Gridline + nhãn trục Y (money), cột tháng (MM/YY), cột cuối tô đậm màu
        brand; trỏ chuột vào cột để xem doanh số chính xác.
        """
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
                               anchor="center", font=("Segoe UI", 9), fill=C_MUT)

        tip = ctk.CTkLabel(parent, text="", font=ctk.CTkFont(size=11, weight="bold"),
                           text_color=C_INK)
        tip.pack(anchor="w")

        def to_mau(goc):
            for i, (rect, _) in enumerate(bars):
                cv.itemconfigure(rect,
                                 fill=C_BRAND if i == len(bars) - 1 else "#9fd3d8")
            if goc:
                # Gốc màu (highlight cột cuối)
                cv.itemconfigure(bars[-1][0], fill=C_BRAND)

        def on_move(e):
            for rect, r in bars:
                x0, y0, x1, y1 = cv.coords(rect)
                if x0 <= e.x <= x1 and y0 <= e.y <= y1 + PB:
                    to_mau(False)
                    cv.itemconfigure(rect, fill="#12a3af")
                    tip.configure(text=tf("{:02d}/{} — doanh số {} ₫ · {} đơn vị", int(r['thang']), r['nam'], fmt(r['doanh_so']), fmt(r['so_luong'])))
                    return
            to_mau(False)
            tip.configure(text="")

        def on_leave(_):
            to_mau(False)
            tip.configure(text="")

        cv.bind("<Motion>", on_move)
        cv.bind("<Leave>", on_leave)
        return cv

    def _do_backup(self):
        """Sao lưu DB sang file backup có timestamp."""
        try:
            path, size_mb = core.backup_db(self.con)
            if path:
                messagebox.showinfo("Sao lưu thành công",
                                    tf("Đã lưu backup:\n{}\n\nDung lượng: {:.1f} MB", path, size_mb))
            else:
                messagebox.showerror(t("Lỗi"), t("Không thể tạo backup"))
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def _do_restore(self):
        """Khôi phục DB từ file người dùng chọn. Tự động backup DB hiện tại trước."""
        import tkinter.filedialog as fd
        import tkinter.messagebox as mb
        path = fd.askopenfilename(
            title=t("Chọn file backup để khôi phục"),
            filetypes=[("Backup QLVT", "qlvt_backup_*.db"), ("SQLite DB", "*.db"), ("Tất cả", "*.*")],
        )
        if not path:
            return
        if not mb.askyesno(
                t("Xác nhận khôi phục"),
                tf("Dữ liệu hiện tại sẽ bị THAY BẰNG nội dung file:\n{}\n\nPhần mềm tự động backup DB hiện tại trước khi khôi phục.\nTiếp tục?", os.path.basename(path))):
            return
        try:
            # Khôi phục = copy file nguồn đè DB hiện tại. Connection phải đóng trước.
            self.con.close()
            bak, loi = core.khoi_phuc_db(core.connect(DB_PATH, check_same_thread=False), path)
            if loi:
                mb.showerror(t("Lỗi"), tf("Không khôi phục được: {}", loi))
            else:
                mb.showinfo(t("Khôi phục thành công"),
                            tf("Đã khôi phục từ:\n{}\n\nBackup DB cũ: {}", path, os.path.basename(bak) if bak else '—'))
            # Mở lại connection mới (đã là file đã khôi phục)
            self.con = core.connect(DB_PATH, check_same_thread=False)
            # Reset user (khôi phục có thể xóa tài khoản)
            self.user = None
            self._nav_items = []
            self.nav = {}
            self._login_dlg = None
            self._token = None
            for w in self.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
            self._hien_man_hinh_dang_nhap()
        except Exception as e:
            try:
                self.con = core.connect(DB_PATH, check_same_thread=False)
            except Exception:
                pass
            mb.showerror("Lỗi", tf("Khôi phục thất bại: {}", e))

    def _alert_row(self, parent, tag, title, detail, color):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=3)
        ctk.CTkLabel(f, text=tag, font=ctk.CTkFont(size=9, weight="bold"),
                     text_color="#ffffff", fg_color=color, corner_radius=4,
                     width=76, height=20).pack(side="left")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_INK, width=300, anchor="w").pack(side="left", padx=8)
        ctk.CTkLabel(f, text=detail, font=ctk.CTkFont(size=10),
                     text_color=C_MUT).pack(side="right")

    def _count_today(self):
        d = date.today().isoformat()
        return self.con.execute(
            "SELECT COUNT(*) FROM phieu_giaodich WHERE substr(ngay_lap,1,10)=?", (d,)
        ).fetchone()[0]

    # ==================== 2. BÁN HÀNG ====================
    def scr_sale(self):
        self.header("Bán hàng", "Xuất hàng · lập biên bản giao hàng tự động")

        # --- form ---
        c = self.card("Thông tin giao hàng")
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Khách hàng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=0, column=0, sticky="w", pady=5)
        self.v_kh = ctk.CTkComboBox(f, values=[k["ten_kh"] for k in core.ds_khachhang(self.con)],
                                    width=380, height=32)
        self.v_kh.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Ngày giao"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=1, column=0, sticky="w", pady=5)
        # Date picker: nhập tay HOẶC chọn lịch
        self.v_ngay = ctk.CTkEntry(f, width=160, height=32)
        self.v_ngay.insert(0, date.today().isoformat())
        self.v_ngay.grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.v_ngay)).grid(
            row=1, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Số hợp đồng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=2, column=0, sticky="w", pady=5)
        # Dropdown hợp đồng: chỉ hiển thị hợp đồng CỦA KHÁCH HÀNG đã chọn VÀ CÒN HẠN.
        # Khi chưa chọn KH → trống. Khách lẻ/không HĐ → để trống (không bắt buộc chọn).
        self.v_hd = ctk.CTkComboBox(f, values=[], width=380, height=32)
        self.v_hd.grid(row=2, column=1, sticky="w", pady=5)
        self.v_kh.bind("<<ComboboxSelected>>", lambda _: self._cap_nhat_hop_dong())

        ctk.CTkLabel(f, text=t("Khoa nhận"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=3, column=0, sticky="w", pady=5)
        self.v_khoa = ctk.CTkEntry(f, width=240, height=32, placeholder_text=t("VD: Hồi sức ngoại"))
        self.v_khoa.grid(row=3, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Người gọi hàng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=4, column=0, sticky="w", pady=5)
        self.v_nguoi = ctk.CTkEntry(f, width=240, height=32, placeholder_text=t("VD: BS. Nguyễn Văn A"))
        self.v_nguoi.grid(row=4, column=1, sticky="w", pady=5)

        # --- thêm mặt hàng ---
        c2 = self.card("Thêm mặt hàng")
        f2 = ctk.CTkFrame(c2, fg_color="transparent")
        f2.pack(fill="x", padx=14, pady=(0, 12))
        f2.grid_columnconfigure(0, weight=1)

        r = ctk.CTkFrame(f2, fg_color="transparent")
        r.pack(fill="x")
        r.grid_columnconfigure(0, weight=1)
        self.v_ma = ctk.CTkEntry(r, placeholder_text=t("Nhập mã hoặc tên vật tư…"), height=34)
        self.v_ma.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.v_ma.bind("<KeyRelease>", self._on_ma_typed)
        self.v_sl = ctk.CTkEntry(r, placeholder_text="SL", width=70, height=34)
        self.v_sl.insert(0, "1")
        self.v_sl.grid(row=0, column=1, padx=(0, 6))
        self.v_hsd = ctk.CTkEntry(r, placeholder_text=t("Hạn dùng"), width=110, height=34)
        self.v_hsd.grid(row=0, column=2, padx=(0, 6))
        # Ô nhập giá: tự điền theo hợp đồng, người dùng có thể chỉnh
        ctk.CTkLabel(r, text=t("Giá"), font=ctk.CTkFont(size=9),
                     text_color=C_MUT).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.v_gia_nhap = ctk.CTkEntry(r, placeholder_text=t("Giá bán (tự điền)"), width=150, height=30)
        self.v_gia_nhap.grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))
        ctk.CTkButton(r, text=t("+ Thêm"), width=80, height=34, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._add_cart).grid(row=0, column=3)

        self.v_gia = ctk.CTkLabel(r, text="", font=ctk.CTkFont(size=11),
                                 text_color=C_MUT)
        self.v_gia.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # 5 gợi ý vật tư dưới ô nhập
        import tkinter as tk
        self.v_goi_y = tk.Listbox(r, height=5, font=("Segoe UI", 10),
                                   bg="#ffffff", fg=C_INK, selectbackground=C_BRAND,
                                   selectforeground="#ffffff", highlightthickness=0,
                                   activestyle="none")
        self.v_goi_y.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.v_goi_y.bind("<<ListboxSelect>>", self._chon_goi_y)

        # --- giỏ hàng ---
        c3 = self.card("Chi tiết phiếu xuất")
        self.cart_box = ctk.CTkFrame(c3, fg_color="transparent")
        self.cart_box.pack(fill="x", padx=14, pady=(0, 12))

        # --- nút hành động ---
        # QUAN TRỌNG: v_tong phải tạo TRƯỚC khi _render_cart() chạy, vì
        # _render_cart() gọi v_tong.configure() ngay khi phiếu trống.
        f3 = ctk.CTkFrame(self.main, fg_color="transparent")
        f3.pack(fill="x", pady=6)
        ctk.CTkButton(f3, text=t("🧾  Lập biên bản giao hàng"), height=42,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color=C_BRAND, hover_color="#12a3af",
                      command=self._lap_bien_ban).pack(side="left", padx=(0, 8))
        ctk.CTkButton(f3, text=t("Xóa phiếu"), height=42, fg_color="#eef2f6",
                      text_color=C_INK, hover_color="#e3e9ef",
                      command=self._clear_cart).pack(side="left")
        self.v_tong = ctk.CTkLabel(f3, text=t("Tổng: 0 ₫"),
                                   font=ctk.CTkFont(size=16, weight="bold"),
                                   text_color=C_INK)
        self.v_tong.pack(side="right")

        # giờ mới render giỏ (phiếu đang trống)
        self._render_cart()

    def _chon_ngay(self, entry):
        """Mở popup lịch tkcalendar, chọn ngày → ghi vào entry (định dạng YYYY-MM-DD)."""
        import tkcalendar
        import tkinter as tk
        top = ctk.CTkToplevel(self)
        top.title(t("Chọn ngày"))
        top.geometry("320x300")
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
        """Cập nhật dropdown số hợp đồng: chỉ HĐ của KH đã chọn VÀ CÒN HẠN."""
        kh = self.v_kh.get()
        ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                      if k["ten_kh"] == kh), None)
        if not ma_kh:
            self.v_hd.configure(values=[])
            self.v_hd.set("")
            return
        ds = core.ds_hop_dong_con_han(self.con, ma_kh)
        self.v_hd.configure(values=ds)
        if ds and not self.v_hd.get():
            self.v_hd.set(ds[0])

    def _on_ma_typed(self, _):
        q = self.v_ma.get().strip()
        self.v_goi_y.delete(0, "end")
        if not q:
            self.v_gia.configure(text="")
            return
        rows = core.ds_vattu(self.con, q)[:5]  # tối đa 5 gợi ý
        if rows:
            for v in rows:
                self.v_goi_y.insert("end",
                    f"{v['ma_vt']} — {v['ten_vt'][:44]} · {v['dvt']}")
            v = rows[0]
            kh = self.v_kh.get()
            ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                         if k["ten_kh"] == kh), None) if kh else None
            gia, nguon = core.gia_ban(self.con, v["ma_vt"], ma_kh)
            self.v_gia.configure(
                text=f"{v['ma_vt']} — {v['ten_vt'][:40]}  ·  ĐVT: {v['dvt']}  ·  "
                     f"Giá {nguon}: {fmt(gia)} ₫",
                text_color=C_BRAND if nguon == "theo hợp đồng" else C_MUT)
            # Tự điền giá vào ô nhập (người dùng có thể chỉnh)
            self.v_gia_nhap.delete(0, "end")
            self.v_gia_nhap.insert(0, fmt(gia))
        else:
            self.v_gia.configure(text=t("Không tìm thấy mã vật tư này."), text_color=C_BAD)

    def _chon_goi_y(self, _):
        """Click vào gợi ý → điền mã vật tư vào ô nhập."""
        sel = self.v_goi_y.curselection()
        if not sel:
            return
        text = self.v_goi_y.get(sel[0])
        ma = text.split(" — ")[0].strip()
        self.v_ma.delete(0, "end")
        self.v_ma.insert(0, ma)
        self._on_ma_typed(None)

    def _add_cart(self):
        q = self.v_ma.get().strip()
        if not q:
            return
        rows = core.ds_vattu(self.con, q)
        if not rows:
            self.v_gia.configure(text=t("Không tìm thấy mã vật tư."), text_color=C_BAD)
            return
        v = rows[0]
        try:
            sl = float(self.v_sl.get())
        except ValueError:
            sl = 1
        if sl <= 0:
            sl = 1
        # Cảnh báo nếu xuất nhiều hơn tồn kho
        tk_ = next((r["ton_kho"] or 0 for r in core.ton_kho(self.con)
                    if r["ma_vt"] == v["ma_vt"]), None)
        if tk_ is not None and sl > tk_:
            if not messagebox.askyesno(
                    "Cảnh báo tồn kho",
                    tf("Tồn kho hiện chỉ còn {} {}.\nBạn định xuất {} — vượt tồn kho {}.\n\nVẫn tiếp tục thêm vào giỏ?", fmt(tk_), v['dvt'], fmt(sl), fmt(sl - tk_))):
                return
        kh = self.v_kh.get()
        ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                     if k["ten_kh"] == kh), None)
        gia_auto, nguon = core.gia_ban(self.con, v["ma_vt"], ma_kh)
        # Ưu tiên giá người dùng nhập tay; để trống → dùng giá tự điền
        gia_nhap = to_float(self.v_gia_nhap.get())
        gia = gia_nhap if gia_nhap > 0 else gia_auto
        self.cart.append({"ma_vt": v["ma_vt"], "ten_vt": v["ten_vt"], "dvt": v["dvt"],
                          "so_luong": sl, "don_gia": gia, "nguon": nguon if gia == gia_nhap else "nhập tay",
                          "han_su_dung": self.v_hsd.get().strip() or None})
        self.v_ma.delete(0, "end")
        self.v_sl.delete(0, "end")
        self.v_sl.insert(0, "1")
        self.v_hsd.delete(0, "end")
        self.v_gia_nhap.delete(0, "end")
        self.v_gia.configure(text=tf("Đã thêm. Giá {} ₫ ({})", fmt(gia), nguon), text_color=C_OK)
        self._render_cart()

    def _render_cart(self):
        for w in self.cart_box.winfo_children():
            w.destroy()
        if not self.cart:
            ctk.CTkLabel(self.cart_box, text=t("Phiếu đang trống — thêm mặt hàng ở trên."),
                         text_color=C_MUT, font=ctk.CTkFont(size=12)).pack(anchor="w", pady=8)
            self.v_tong.configure(text=t("Tổng: 0 ₫"))
            return
        hd = ctk.CTkFrame(self.cart_box, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate(["#", "Mã VT", "Tên vật tư", "ĐVT", "SL", "Đơn giá", "Thành tiền", ""]):
            ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=[30, 90, 300, 50, 50, 110, 120, 30][i]).grid(
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
                             width=[30, 90, 300, 50, 50, 110, 120, 30][i]).grid(
                    row=idx, column=i, padx=4, pady=3, sticky="w")
        self.v_tong.configure(text=tf("Tổng: {} ₫", fmt(tong)))

    def _clear_cart(self):
        self.cart = []
        self._render_cart()

    def _lap_bien_ban(self):
        if not self.cart:
            self.v_gia.configure(text=t("Phiếu đang trống."), text_color=C_BAD)
            return
        kh = self.v_kh.get()
        ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                     if k["ten_kh"] == kh), None)
        ngay = self.v_ngay.get().strip() or date.today().isoformat()
        so_phieu = None
        try:
            for it in self.cart:
                so_phieu = core.ghi_phieu(
                    self.con, "XUAT", ngay, it["ma_vt"], it["so_luong"], it["don_gia"],
                    ma_kh=ma_kh, khoa_nhan=self.v_khoa.get().strip(),
                    nguoi_goi=self.v_nguoi.get().strip(),
                    so_hop_dong=self.v_hd.get().strip(),
                    han_su_dung=it.get("han_su_dung"), nguoi_lap=nguoi_lap_cua(self))
        except Exception as e:
            self.v_gia.configure(text=tf("Lỗi ghi phiếu: {}", e), text_color=C_BAD)
            return
        bb = core.bien_ban(self.con, so_phieu)
        self.cart = []
        self._render_cart()
        self._show_bien_ban(bb)

    def _show_bien_ban(self, bb):
        w = ctk.CTkToplevel(self)
        w.title(tf("Biên bản giao hàng {}", bb['so_phieu']))
        w.geometry("860x1000")
        w.configure(fg_color="#ffffff")
        fr = ctk.CTkScrollableFrame(w, fg_color="#ffffff")
        fr.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(fr, text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        ctk.CTkLabel(fr, text=t("Độc lập - Tự do - Hạnh phúc"),
                     font=ctk.CTkFont(size=13, weight="bold")).pack()
        ctk.CTkLabel(fr, text="———————————", text_color=C_MUT).pack()
        ctk.CTkLabel(fr, text="BIÊN BẢN GIAO HÀNG",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(8, 2))
        ctk.CTkLabel(fr, text=tf("Số: {} /BBGH", bb['so_phieu']),
                     font=ctk.CTkFont(size=11), text_color=C_MUT).pack()
        ctk.CTkLabel(fr, text=tf("Ngày {} tháng {} năm {}", bb['ngay'], bb['thang'], bb['nam']),
                     font=ctk.CTkFont(size=11)).pack(pady=(6, 0))
        ctk.CTkLabel(fr, text=tf("Số hợp đồng: {}", bb['so_hop_dong'] or '…………………'),
                     font=ctk.CTkFont(size=11)).pack()
        ctk.CTkLabel(fr, text=tf("Bên nhận: {}", bb['ten_kh']),
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(8, 0))
        if bb["dia_chi"]:
            ctk.CTkLabel(fr, text=tf("Địa chỉ: {}", bb['dia_chi']),
                         font=ctk.CTkFont(size=11)).pack()
        if bb["ma_so_thue"]:
            ctk.CTkLabel(fr, text=tf("Mã số thuế: {}", bb['ma_so_thue']),
                         font=ctk.CTkFont(size=11)).pack()
        if bb["khoa_nhan"]:
            ctk.CTkLabel(fr, text=tf("Khoa/Phòng nhận: {}", bb['khoa_nhan']),
                         font=ctk.CTkFont(size=11)).pack()
        if bb["nguoi_goi"]:
            ctk.CTkLabel(fr, text=tf("Người gọi hàng: {}", bb['nguoi_goi']),
                         font=ctk.CTkFont(size=11)).pack()

        ctk.CTkLabel(fr, text=t("Hai bên tiến hành kiểm tra và thống nhất giao nhân:"),
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(12, 4))

        # Gom các dòng cùng mã vật tư → hiển thị TỔNG SỐ LƯỢNG (không hiển thị hạn sử dụung)
        gom = {}
        for it in bb["items"]:
            k = it["ma_vt"]
            if k not in gom:
                gom[k] = {"ten_vt": it["ten_vt"], "dvt": it["dvt"], "so_luong": 0.0,
                          "don_gia": it["don_gia"]}
            gom[k]["so_luong"] += it["so_luong"] or 0

        tb = ctk.CTkFrame(fr, fg_color="#ffffff", border_width=1, border_color="#444444")
        tb.pack(fill="x")
        for i, col_name in enumerate(["STT", "Tên vật tư", "ĐVT", "Tổng SL", "Đơn giá", "Thành tiền"]):
            ctk.CTkLabel(tb, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#000000", width=[36, 300, 50, 60, 100, 110][i]).grid(
                row=0, column=i, padx=4, pady=6, sticky="w")
        for idx, (k, g) in enumerate(gom.items(), 1):
            tt = g["so_luong"] * g["don_gia"]
            vals = [str(idx), tf("{}\nMã: {}", g['ten_vt'], k), g["dvt"],
                    fmt(g["so_luong"]), fmt(g["don_gia"]), fmt(tt)]
            for i, v in enumerate(vals):
                ctk.CTkLabel(tb, text=v, font=ctk.CTkFont(size=10),
                             text_color="#000000", width=[36, 300, 50, 60, 100, 110][i]).grid(
                    row=idx, column=i, padx=4, pady=4, sticky="w")

        ctk.CTkLabel(fr, text=tf("Tổng cộng: {} ₫", fmt(bb['tong'])),
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="e", pady=(8, 0))
        ctk.CTkLabel(fr, text=tf("(Bằng chữ: {})", bb['bang_chu']),
                     font=ctk.CTkFont(size=11)).pack(anchor="e")
        ctk.CTkLabel(fr, text=tf("Thuế GTGT 8%: {} ₫   ·   Tổng thanh toán: {} ₫", fmt(bb['vat']), fmt(bb['tong_cong'])),
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="e")

        ctk.CTkLabel(fr, text=t("Chất lượng hàng mới 100%, còn hạn sử dụng, đúng quy cách đóng gói."),
                     font=ctk.CTkFont(size=10)).pack(anchor="w", pady=(12, 0))
        sg = ctk.CTkFrame(fr, fg_color="transparent")
        sg.pack(fill="x", pady=(16, 0))
        sg.grid_columnconfigure((0, 1), weight=1)
        for i, col_name in enumerate(["ĐẠI DIỆN BÊN NHẬN", "ĐẠI DIỆN BÊN GIAO"]):
            ctk.CTkLabel(sg, text=col_name, font=ctk.CTkFont(size=11, weight="bold")).grid(
                row=0, column=i, padx=20, sticky="w")
            ctk.CTkLabel(sg, text=t("(Ký, ghi rõ họ tên)"),
                         font=ctk.CTkFont(size=9), text_color=C_MUT).grid(
                row=1, column=i, padx=20, sticky="w")

        ctk.CTkButton(fr, text=t("In / Lưu PDF"), height=38, fg_color=C_BRAND,
                      hover_color="#12a3af",
                      command=lambda: self._in_bien_ban(w)).pack(pady=(18, 4))

    def _in_bien_ban(self, win):
        """In/lưu PDF bằng core.xuat_pdf — ưu tiên thư mục dist/bienban cạnh exe."""
        try:
            bb = core.bien_ban(self.con)
            if not bb:
                return
            path, loi = core.xuat_pdf(self.con, bb["so_phieu"])
            if loi or not path:
                self.v_gia.configure(text=tf("Không xuất được PDF: {}", loi), text_color=C_BAD)
                return
            self.v_gia.configure(text=tf("Đã xuất PDF: {}", path), text_color=C_OK)
        except Exception as e:
            self.v_gia.configure(text=tf("Lỗi xuất PDF: {}", e), text_color=C_BAD)

    # ==================== 3. NHẬP KHO ====================
    def scr_in(self):
        self.header("Nhập kho", "Nhập nhiều mã vật tư → tồn kho & cảnh báo hạn dùng tự cập nhật")
        c = self.card("Phiếu nhập kho")
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Ngày nhập"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=0, column=0, sticky="w", pady=5)
        self.n_ngay = ctk.CTkEntry(f, width=160, height=32)
        self.n_ngay.insert(0, date.today().isoformat())
        self.n_ngay.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Mã vật tư"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=1, column=0, sticky="w", pady=5)
        self.n_ma = ctk.CTkEntry(f, width=240, height=32, placeholder_text=t("Nhập mã…"))
        self.n_ma.grid(row=1, column=1, sticky="w", pady=5)
        self.n_ma.bind("<KeyRelease>", self._on_nhap_typed)

        ctk.CTkLabel(f, text=t("Số lượng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=2, column=0, sticky="w", pady=5)
        self.n_sl = ctk.CTkEntry(f, width=120, height=32)
        self.n_sl.insert(0, "1")
        self.n_sl.grid(row=2, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Hạn sử dụng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=3, column=0, sticky="w", pady=5)
        self.n_hsd = ctk.CTkEntry(f, width=160, height=32, placeholder_text="YYYY-MM-DD")
        self.n_hsd.grid(row=3, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.n_hsd)).grid(
            row=3, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Đơn giá nhập"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=4, column=0, sticky="w", pady=5)
        self.n_gia = ctk.CTkEntry(f, width=160, height=32)
        self.n_gia.grid(row=4, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Số lô"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=5, column=0, sticky="w", pady=5)
        self.n_lo = ctk.CTkEntry(f, width=200, height=32, placeholder_text="VD: LOT-2026-08")
        self.n_lo.grid(row=5, column=1, sticky="w", pady=5)

        self.n_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11), text_color=C_MUT)
        self.n_msg.grid(row=6, column=1, sticky="w", pady=(8, 0))

        # Thêm một mặt hàng vào phiếu (nhiều mã vật tư)
        ctk.CTkButton(f, text=t("➕ Thêm vào phiếu"), height=36, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._add_nhap).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # 5 gợi ý vật tư
        import tkinter as tk
        self.n_goi_y = tk.Listbox(f, height=5, font=("Segoe UI", 10),
                                   bg="#ffffff", fg=C_INK, selectbackground=C_BRAND,
                                   selectforeground="#ffffff", highlightthickness=0,
                                   activestyle="none")
        self.n_goi_y.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.n_goi_y.bind("<<ListboxSelect>>", self._chon_goi_y_nhap)

        # --- giỏ phiếu nhập ---
        c3 = self.card("Chi tiết phiếu nhập")
        self.cart_nhap_box = ctk.CTkFrame(c3, fg_color="transparent")
        self.cart_nhap_box.pack(fill="x", padx=14, pady=(0, 12))

        f3 = ctk.CTkFrame(self.main, fg_color="transparent")
        f3.pack(fill="x", pady=6)
        ctk.CTkButton(f3, text=t("💾 Lưu phiếu nhập"), height=42, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._luu_nhap).pack(side="left", padx=(0, 8))
        ctk.CTkButton(f3, text=t("Xóa phiếu"), height=42, fg_color="#eef2f6",
                      text_color=C_INK, hover_color="#e3e9ef", command=self._clear_nhap).pack(side="left")
        self.n_tong = ctk.CTkLabel(f3, text=t("Tổng SL: 0"), font=ctk.CTkFont(size=16, weight="bold"),
                                    text_color=C_INK)
        self.n_tong.pack(side="right")

        self._render_nhap_cart()

    def _add_nhap(self):
        """Thêm 1 dòng vật tư (mã đã kiểm tra) vào phiếu nhập."""
        q = self.n_ma.get().strip()
        if not q:
            self.n_msg.configure(text=t("Nhập mã vật tư trước."), text_color=C_BAD)
            return
        rows = core.ds_vattu(self.con, q)
        if not rows:
            self.n_msg.configure(text=t("Mã vật tư không tồn tại."), text_color=C_BAD)
            return
        v = rows[0]
        try:
            sl = float(self.n_sl.get() or 1)
        except ValueError:
            sl = 1
        if sl <= 0:
            sl = 1
        try:
            gia = to_float(self.n_gia.get() or v["don_gia"])
        except Exception:
            gia = v["don_gia"]
        if gia <= 0:
            gia = v["don_gia"]
        self.cart_nhap.append({
            "ma_vt": v["ma_vt"], "ten_vt": v["ten_vt"], "dvt": v["dvt"],
            "so_luong": sl, "don_gia": gia, "so_lo": self.n_lo.get().strip(),
            "han_su_dung": self.n_hsd.get().strip(),
            "nguoi_lap": nguoi_lap_cua(self),
        })
        self.n_ma.delete(0, "end")
        self.n_sl.delete(0, "end")
        self.n_sl.insert(0, "1")
        self.n_gia.delete(0, "end")
        self.n_lo.delete(0, "end")
        self.n_hsd.delete(0, "end")
        self.n_msg.configure(text=tf("Đã thêm {} x {}.", v['ma_vt'], fmt(sl)), text_color=C_OK)
        self._render_nhap_cart()

    def _render_nhap_cart(self):
        for w in self.cart_nhap_box.winfo_children():
            w.destroy()
        if not self.cart_nhap:
            ctk.CTkLabel(
                self.cart_nhap_box,
                text=t("Phiếu đang trống — thêm vật tư ở trên."),
                text_color=C_MUT, font=ctk.CTkFont(size=12),
            ).pack(anchor="w", pady=8)
            self.n_tong.configure(text=t("Tổng SL: 0"))
            return
        hd = ctk.CTkFrame(self.cart_nhap_box, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate(["#", "Mã VT", "Tên vật tư", "ĐVT", "SL", "Đơn giá",
                              "Số lô", "HSD", "Xóa"]):
            ctk.CTkLabel(
                hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                text_color=C_MUT, width=[30, 90, 300, 50, 50, 110, 110, 120, 40][i],
            ).grid(row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        tong_sl = 0.0
        for idx, it in enumerate(self.cart_nhap, 1):
            tt = it["so_luong"] * it["don_gia"]
            tong_sl += it["so_luong"]
            vals = [str(idx), it["ma_vt"], it["ten_vt"][:40], it["dvt"],
                    fmt(it["so_luong"]), fmt(it["don_gia"]),
                    fmt(it["so_lo"] or ""), it["han_su_dung"] or "", "✕"]
            for i, v in enumerate(vals):
                ctk.CTkLabel(
                    hd, text=v, font=ctk.CTkFont(size=11),
                    text_color=C_INK if i != 8 else C_BAD,
                    width=[30, 90, 300, 50, 50, 110, 110, 120, 40][i],
                ).grid(row=idx, column=i, padx=4, pady=3, sticky="w")
            ctk.CTkButton(
                hd, text="", width=40, height=22,
                command=lambda i=idx: self._xoa_dong_nhap(i),
            ).grid(row=idx, column=8, padx=4, pady=3)
        self.n_tong.configure(
            text=tf("Tổng SL: {} | Giá trị: {}", fmt(tong_sl), money(sum(it['so_luong'] * it['don_gia'] for it in self.cart_nhap)))
        )

    def _xoa_dong_nhap(self, idx):
        self.cart_nhap.pop(idx - 1)
        self._render_nhap_cart()

    def _clear_nhap(self):
        self.cart_nhap = []
        self._render_nhap_cart()

    def _on_nhap_typed(self, _):
        q = self.n_ma.get().strip()
        self.n_goi_y.delete(0, "end")
        rows = core.ds_vattu(self.con, q)[:5] if q else []  # tối đa 5 gợi ý
        if rows:
            for v in rows:
                self.n_goi_y.insert("end", f"{v['ma_vt']} — {v['ten_vt'][:44]} · {v['dvt']}")
            v = rows[0]
            self.n_gia.delete(0, "end")
            self.n_gia.insert(0, fmt(v["don_gia"]))
            self.n_msg.configure(text=f"{v['ma_vt']} — {v['ten_vt'][:44]}", text_color=C_OK)
        else:
            self.n_msg.configure(text=t("Không tìm thấy mã vật tư."), text_color=C_BAD)

    def _chon_goi_y_nhap(self, _):
        """Click vào gợi ý nhập kho → điền mã vật tư vào ô nhập."""
        sel = self.n_goi_y.curselection()
        if not sel:
            return
        text = self.n_goi_y.get(sel[0])
        ma = text.split(" — ")[0].strip()
        self.n_ma.delete(0, "end")
        self.n_ma.insert(0, ma)
        self._on_nhap_typed(None)

    def _luu_nhap(self):
        """Lưu phiếu nhập:
        - nếu có dòng trong giỏ phiếu → lưu tất cả.
        - nếu giỏ trống → lưu dòng đơn lẻ từ ô nhập (hỗ trợ cũ).
        """
        # Chế độ đơn lẻ (hỗ trợ cũ): khi người dùng điền trực tiếp rồi bấm Lưu.
        if not self.cart_nhap:
            q = self.n_ma.get().strip()
            rows = core.ds_vattu(self.con, q) if q else []
            if not rows:
                self.n_msg.configure(text=t("Chọn mã vật tư hợp lệ."), text_color=C_BAD)
                return
            v = rows[0]
            try:
                sl = float(self.n_sl.get() or 1)
            except ValueError:
                sl = 1
            try:
                sp = core.ghi_phieu(
                    self.con, "NHAP", self.n_ngay.get().strip() or date.today().isoformat(),
                    v["ma_vt"], sl, to_float(self.n_gia.get() or v["don_gia"] or 0),
                    so_lo=self.n_lo.get().strip(), han_su_dung=self.n_hsd.get().strip(),
                    nguoi_lap=nguoi_lap_cua(self),
                )
            except Exception as e:
                self.n_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)
                return
            self.n_msg.configure(text=tf("Đã lưu {} — tồn kho đã cập nhật.", sp), text_color=C_OK)
            self._clear_nhap()
            self.n_ngay.delete(0, "end")
            self.n_ngay.insert(0, date.today().isoformat())
            return
        # Chế độ nhiều dòng (giỏ phiếu)
        ngay = self.n_ngay.get().strip() or date.today().isoformat()
        ok = True
        for it in self.cart_nhap:
            try:
                sp = core.ghi_phieu(
                    self.con, "NHAP", ngay, it["ma_vt"], it["so_luong"], it["don_gia"],
                    so_lo=it["so_lo"], han_su_dung=it["han_su_dung"],
                    nguoi_lap=it["nguoi_lap"],
                )
            except Exception as e:
                self.n_msg.configure(text=tf("Lỗi {}: {}", it['ma_vt'], e), text_color=C_BAD)
                ok = False
                break
            self.n_msg.configure(text=tf("Đã lưu {} — tồn kho cập nhật.", sp), text_color=C_OK)
        if ok:
            self._clear_nhap()
            self.n_ngay.delete(0, "end")
            self.n_ngay.insert(0, date.today().isoformat())

    # ==================== 4. TỒN KHO ====================


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
        """Hộp thoại đăng nhập dạng MODAL (CTkToplevel) canh giữa cửa sổ chính."""
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

        W, H = 420, 410
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

        # Language selector at top-right of login card
        lang_top = ctk.CTkFrame(card, fg_color="transparent")
        lang_top.pack(fill="x", padx=30, pady=(10, 0))
        ctk.CTkLabel(lang_top, text=t("Ngôn ngữ"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT).pack(side="right", padx=(8, 0))
        login_lang_var = ctk.StringVar(value=get_lang())
        login_lang_combo = ctk.CTkComboBox(lang_top, values=["vi", "en"],
                                            variable=login_lang_var, width=60, height=26,
                                            font=ctk.CTkFont(size=10),
                                            command=lambda v: self._doi_ngon_ngu_login(v, dlg))
        login_lang_combo.pack(side="right")

        ctk.CTkLabel(card, text="QLVT Y TẾ", font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=C_BRAND).pack(pady=(30, 2), padx=30, anchor="w")
        ctk.CTkLabel(card, text=t("Quản lý vật tư y tế — đăng nhập để tiếp tục"),
                     font=ctk.CTkFont(size=11), text_color=C_MUT).pack(padx=30, anchor="w")

        ctk.CTkLabel(card, text=t("Tên đăng nhập"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(pady=(22, 4), padx=30, anchor="w")
        self.lg_user = ctk.CTkEntry(card, width=340, height=38, placeholder_text="VD: admin")
        self.lg_user.pack(padx=30, anchor="w")

        ctk.CTkLabel(card, text=t("Mật khẩu"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT).pack(pady=(10, 4), padx=30, anchor="w")
        self.lg_pass = ctk.CTkEntry(card, width=340, height=38, show="\u25cf",
                                    placeholder_text="\u2022\u2022\u2022\u2022\u2022\u2022")
        self.lg_pass.pack(padx=30, anchor="w")

        self.lg_msg = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=11),
                                   text_color=C_BAD)
        self.lg_msg.pack(pady=(8, 0), padx=30, anchor="w")

        ctk.CTkButton(card, text=t("Đăng nhập"), width=340, height=40, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._dang_nhap).pack(
            pady=(14, 8), padx=30)
        ctk.CTkLabel(card, text=t("Tài khoản mặc định: admin / admin123 (đổi ngay sau khi vào)"),
                     font=ctk.CTkFont(size=10), text_color=C_MUT).pack(
            pady=(0, 24), padx=30, anchor="w")

        for e in (self.lg_user, self.lg_pass):
            e.bind("<Return>", lambda _e: self._dang_nhap())

        dlg.bind("<Escape>", lambda _e: self._thoat_ung_dung())
        dlg.grab_set()
        dlg.after(150, dlg.lift)
        dlg.after(200, self.lg_user.focus_force)

    def _dang_nhap(self):
        """Xác thực tài khoản; đúng thì dựng giao diện chính và vào Tổng quan."""
        username = self.lg_user.get().strip()
        password = self.lg_pass.get()
        if not username or not password:
            self.lg_msg.configure(text=t("Nhập tên đăng nhập và mật khẩu"))
            return
        user = core.authenticate(self.con, username, password)
        if not user:
            self.lg_msg.configure(text=t("Sai tên đăng nhập hoặc mật khẩu"))
            self.lg_pass.delete(0, "end")
            return
        self.user = user
        self.lg_msg.configure(text="")
        self.lg_pass.delete(0, "end")
        # Huỷ heartbeat vì đã đăng nhập thành công
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
                "Đổi mật khẩu bắt buộc",
                "Tài khoản này đang dùng mật khẩu mặc định.\nVui lòng đổi mật khẩu ngay.")
            self._doi_mat_khau()


    def scr_stock(self):
        self.header("Tồn kho", "Theo dõi hạn sử dụng & đề xuất nhập thêm")
        c = self.card("Số lượng tồn kho")
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.ton_kho(con=self.con)
        if not rows:
            ctk.CTkLabel(b, text=t("Chưa có dữ liệu tồn kho."),
                         text_color=C_MUT).pack(anchor="w")
            return
        hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate(["Mã VT", "Tên vật tư", "ĐVT", "Tồn", "Tối thiểu", "Giá trị", "Trạng thái", ""]):
            ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=[90, 300, 50, 60, 70, 110, 130, 60][i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        for idx, r in enumerate(rows):
            tk_ = r["ton_kho"] or 0
            mn = r["ton_toi_thieu"] or 0
            if mn > 0 and tk_ < mn:
                st, cl = "Cần nhập", C_WARN
            else:
                st, cl = "Ổn định", C_OK
            vals = [r["ma_vt"], r["ten_vt"][:40], r["dvt"], fmt(tk_), fmt(mn),
                    money(r["gia_tri_ton"]), st]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=cl if i == 6 else C_INK,
                             width=[90, 300, 50, 60, 70, 110, 130][i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            btn = ctk.CTkButton(hd, text=t("Sửa"), width=50, height=22,
                                font=ctk.CTkFont(size=10),
                                command=lambda rr=r: self._sua_toi_thieu(rr))
            btn.grid(row=idx + 1, column=7, padx=4, pady=3)

    def _sua_toi_thieu(self, r):
        """Popup sửa tồn kho tối thiểu của 1 vật tư."""
        top = ctk.CTkToplevel(self)
        top.title(t("Sửa tồn kho tối thiểu"))
        top.geometry("320x160")
        ctk.CTkLabel(top, text=f"{r['ma_vt']} — {r['ten_vt'][:40]}",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(padx=14, pady=(14, 4))
        e = ctk.CTkEntry(top, width=140, height=30)
        e.insert(0, str(r["ton_toi_thieu"] or 0))
        e.pack(padx=14, pady=4)

        def _ok():
            try:
                mn = float(e.get())
            except ValueError:
                messagebox.showerror(t("Lỗi"), t("Số không hợp lệ"))
                return
            self.con.execute("UPDATE dm_vattu SET ton_toi_thieu=? WHERE ma_vt=?",
                             (mn, r["ma_vt"]))
            self.con.commit()
            top.destroy()
            self.scr_stock()
        ctk.CTkButton(top, text=t("Lưu"), command=_ok).pack(pady=(8, 12))

    # ==================== 5. KHÁCH HÀNG ====================
    def scr_cust(self):
        self.header("Khách hàng", "Thêm mới / cập nhật thông tin khách hàng")
        # Form thêm/sửa
        f = self.card("Thông tin khách hàng")
        fr = ctk.CTkFrame(f, fg_color="transparent")
        fr.pack(fill="x", padx=14, pady=(0, 6))
        self._kh_edit = {"ma": None}
        self._kh_widgets = {}
        fields = [("ma", "Mã KH (trống = tự tạo)", 120), ("ten", "Tên khách hàng *", 260),
                  ("dc", "Địa chỉ", 300), ("mst", "Mã số thuế", 140), ("kv", "Khu vực", 120)]
        for i, (k, lb, w) in enumerate(fields):
            ctk.CTkLabel(fr, text=lb, font=ctk.CTkFont(size=10),
                         text_color=C_MUT, width=w, anchor="w").grid(
                row=0, column=i, padx=3, sticky="w")
        for i, (k, lb, w) in enumerate(fields):
            e = ctk.CTkEntry(fr, width=w, height=28, font=ctk.CTkFont(size=11))
            e.grid(row=1, column=i, padx=3)
            self._kh_widgets[k] = e
        ctk.CTkButton(fr, text=t("💾 Lưu"), width=90, height=28,
                      command=self._save_kh).grid(row=1, column=5, padx=6)
        ctk.CTkButton(fr, text=t("🧹 Xóa form"), width=100, height=28,
                      command=self._clear_kh).grid(row=1, column=6, padx=3)
        self._kh_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11),
                                    text_color=C_OK)
        self._kh_msg.pack(padx=14, pady=(0, 10))

        # Bảng danh sách
        c = self.card("Danh sách khách hàng")
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.ds_khachhang(self.con)
        hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate(["Tên khách hàng", "Mã", "Khu vực", "Mã số thuế", "Địa chỉ"]):
            ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=[250, 60, 90, 130, 330][i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        for idx, r in enumerate(rows):
            vals = [r["ten_kh"], r["ma_kh"], r["khu_vuc"] or "—", r["ma_so_thue"] or "—",
                    (r["dia_chi"] or "—")[:46]]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=[250, 60, 90, 130, 330][i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            btn = ctk.CTkButton(hd, text=t("Sửa"), width=50, height=22,
                                font=ctk.CTkFont(size=10),
                                command=lambda rr=r: self._load_kh(rr))
            btn.grid(row=idx + 1, column=5, padx=4, pady=3)

    def _luu_hop_dong(self):
        """Lưu hợp đồng mới từ form."""
        kh = self.hd_kh.get()
        ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                      if k["ten_kh"] == kh), None)
        if not ma_kh:
            self._hd_msg.configure(text=t("Vui lòng chọn khách hàng."), text_color=C_BAD)
            return
        so_hd = self.hd_so.get().strip()
        if not so_hd:
            self._hd_msg.configure(text=t("Thiếu số hợp đồng."), text_color=C_BAD)
            return
        ma_vt = self.hd_ma.get().strip()
        if not ma_vt:
            self._hd_msg.configure(text=t("Thiếu mã vật tư."), text_color=C_BAD)
            return
        try:
            sl = float(self.hd_sl.get() or 0)
            gia = float(to_float(self.hd_gia.get() or 0))
        except ValueError:
            self._hd_msg.configure(text=t("SL/Đơn giá không hợp lệ."), text_color=C_BAD)
            return
        core.luu_hop_dong(self.con, so_hd, ma_kh, ma_vt, sl, gia,
                         ngay_ky=self.hd_ky.get().strip(),
                         ngay_het_han=self.hd_het.get().strip())
        self._hd_msg.configure(text=tf("✅ Đã lưu HĐ: {}", so_hd), text_color=C_OK)
        self.scr_contract()

    def _load_kh(self, r):
        """Load thông tin KH vào form (chế độ sửa)."""
        self._kh_edit["ma"] = r["ma_kh"]
        for k, w in self._kh_widgets.items():
            v = r.get(k) or ""
            w.delete(0, "end")
            w.insert(0, str(v))
        self._kh_msg.configure(text=tf("Đang sửa: {}", r['ma_kh']), text_color=C_WARN)

    def _clear_kh(self):
        """Xóa form (chế độ tạo mới)."""
        self._kh_edit["ma"] = None
        for w in self._kh_widgets.values():
            w.delete(0, "end")
        self._kh_msg.configure(text="", text_color=C_OK)

    def _save_kh(self):
        """Lưu KH: mã trống → tạo mới, có mã → cập nhật."""
        vals = {k: w.get().strip() for k, w in self._kh_widgets.items()}
        try:
            ma = core.luu_khachhang(self.con, ma_kh=vals["ma"] or None,
                                    ten_kh=vals["ten"], dia_chi=vals["dc"],
                                    ma_so_thue=vals["mst"], khu_vuc=vals["kv"])
            self._kh_msg.configure(text=tf("✅ Đã lưu: {}", ma), text_color=C_OK)
            self._clear_kh()
            self.scr_cust()  # render lại bảng
        except Exception as e:
            self._kh_msg.configure(text=f"❌ {e}", text_color=C_BAD)

    # ==================== 6. HỢP ĐỒNG ====================
    def scr_contract(self):
        self.header("Hợp đồng thầu", "Thêm hợp đồng & tiến độ thực hiện")
        # Form thêm hợp đồng
        f = self.card("Thêm hợp đồng mới")
        fr = ctk.CTkFrame(f, fg_color="transparent")
        fr.pack(fill="x", padx=14, pady=(0, 12))
        fr.grid_columnconfigure(1, weight=1)
        self._hd_msg = ctk.CTkLabel(fr, text="", font=ctk.CTkFont(size=11), text_color=C_OK)
        self._hd_msg.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 6))

        ctk.CTkLabel(fr, text=t("Khách hàng"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=110).grid(row=1, column=0, sticky="w")
        self.hd_kh = ctk.CTkComboBox(fr, values=[k["ten_kh"] for k in core.ds_khachhang(self.con)],
                                      width=200, height=28)
        self.hd_kh.grid(row=1, column=1, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Số HĐ"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=110).grid(row=1, column=2, sticky="w")
        self.hd_so = ctk.CTkEntry(fr, width=160, height=28)
        self.hd_so.grid(row=1, column=3, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Mã VT"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=110).grid(row=1, column=4, sticky="w")
        self.hd_ma = ctk.CTkEntry(fr, width=130, height=28)
        self.hd_ma.grid(row=1, column=5, sticky="w", padx=2)

        ctk.CTkLabel(fr, text="SL", font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=60).grid(row=2, column=0, sticky="w")
        self.hd_sl = ctk.CTkEntry(fr, width=90, height=28)
        self.hd_sl.insert(0, "1")
        self.hd_sl.grid(row=2, column=1, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Đơn giá"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=60).grid(row=2, column=2, sticky="w")
        self.hd_gia = ctk.CTkEntry(fr, width=130, height=28)
        self.hd_gia.grid(row=2, column=3, sticky="w", padx=2)
        ctk.CTkLabel(fr, text=t("Ngày ký"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=80).grid(row=2, column=4, sticky="w")
        self.hd_ky = ctk.CTkEntry(fr, width=130, height=28, placeholder_text="YYYY-MM-DD")
        self.hd_ky.insert(0, date.today().isoformat())
        self.hd_ky.grid(row=2, column=5, sticky="w", padx=2)
        ctk.CTkButton(fr, text="📅", width=32, height=28,
                      command=lambda: self._chon_ngay(self.hd_ky)).grid(row=2, column=6, padx=2)
        ctk.CTkLabel(fr, text=t("Hết hạn"), font=ctk.CTkFont(size=10),
                     text_color=C_MUT, width=80).grid(row=3, column=0, sticky="w")
        self.hd_het = ctk.CTkEntry(fr, width=130, height=28, placeholder_text="YYYY-MM-DD")
        self.hd_het.grid(row=3, column=1, sticky="w", padx=2)
        ctk.CTkButton(fr, text="📅", width=32, height=28,
                      command=lambda: self._chon_ngay(self.hd_het)).grid(row=3, column=2, padx=2)
        ctk.CTkButton(fr, text=t("💾 Lưu HĐ"), width=100, height=28, fg_color=C_BRAND,
                      command=self._luu_hop_dong).grid(row=3, column=3, padx=2)

        c = self.card("Tiến độ hợp đồng")
        b = ctk.CTkFrame(c, fg_color="transparent")
        b.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.tien_do_hop_dong(self.con)
        if not rows:
            ctk.CTkLabel(b, text=t("Chưa có hợp đồng nào."),
                         text_color=C_MUT).pack(anchor="w")
            return
        hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate(["Số HĐ", "Khách hàng", "Mã VT", "Tổng SL", "Đã TH", "Còn lại", "Tiến độ"]):
            ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=[110, 200, 90, 60, 60, 60, 130][i]).grid(
                row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        for idx, r in enumerate(rows):
            sl = r["so_luong"] or 0
            done = r["da_thuc_hien"] or 0
            pc = (done / sl * 100) if sl else 0
            vals = [r["so_hd"], (r["ma_kh"] or "")[:24], r["ma_vt"], fmt(sl), fmt(done),
                    fmt(r["con_lai"]), f"{pc:.0f}%"]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=[110, 200, 90, 60, 60, 60, 130][i]).grid(
                    row=idx + 1, column=i, padx=4, pady=3, sticky="w")
            pb = ctk.CTkProgressBar(hd, width=110, height=8, corner_radius=4)
            pb.set(pc / 100)
            pb.grid(row=idx + 1, column=6, padx=(0, 4), sticky="w")

    # ==================== 7. BÁO CÁO ====================
    def scr_report(self):
        self.header("Báo cáo", "Tháng · Quý · Thị phần — chọn năm, xuất PDF")
        # hàng chọn năm + nút xuất PDF
        f0 = ctk.CTkFrame(self.main, fg_color="transparent")
        f0.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(f0, text=t("Năm"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=50).pack(side="left")
        cac_nam = self._ds_nam_co_du_lieu()
        self.r_nam = ctk.CTkComboBox(f0, values=cac_nam or [str(date.today().year)],
                                     width=120, height=30,
                                     command=lambda _: self._draw_report(self.r_tab.get()))
        self.r_nam.set(str(date.today().year))
        self.r_nam.pack(side="left")
        ctk.CTkButton(f0, text=t("📄 Xuất PDF"), width=130, height=30,
                      command=self._xuat_baocao_pdf).pack(side="right")

        self.r_tab = ctk.CTkSegmentedButton(self.main, values=[t("Tháng"), t("Quý"), t("Thị phần")],
                                            font=ctk.CTkFont(size=12, weight="bold"),
                                            fg_color="#e3e9ef", selected_color=C_BRAND,
                                            selected_hover_color="#12a3af",
                                            command=lambda v: self._draw_report(v))
        self.r_tab.pack(anchor="w", pady=(0, 10))
        self.r_tab.set("Tháng")
        self.r_box = ctk.CTkFrame(self.main, fg_color="transparent")
        self.r_box.pack(fill="x")
        self._draw_report("Tháng")

    def _ds_nam_co_du_lieu(self):
        """Các năm có dữ liệu bán hàng (từ phiếu xuất)."""
        rows = self.con.execute(
            "SELECT DISTINCT substr(ngay_phieu,1,4) FROM phieu_giaodich WHERE ngay_phieu IS NOT NULL AND ngay_phieu != '' ORDER BY 1 DESC"
        ).fetchall()
        return [r[0] for r in rows if r[0]]

    def _xuat_baocao_pdf(self):
        import tkinter.filedialog as fd
        try:
            loai = {"Tháng": "m", "Quý": "q", "Thị phần": "s"}.get(self.r_tab.get(), "m")
            nam = int(self.r_nam.get())
            # Người dùng chọn vị trí lưu file PDF
            path = fd.asksaveasfilename(
                title=t("Lưu báo cáo PDF"),
                defaultextension=".pdf",
                initialfile=f"BaoCao_{loai}_{nam}.pdf",
                filetypes=[("PDF", "*.pdf")],
            )
            if not path:
                return
            path, loi = core.xuat_baocao_pdf(self.con, loai, nam, path)
            if loi or not path:
                messagebox.showerror("Lỗi", tf("Không xuất được PDF: {}", loi))
                return
            messagebox.showinfo("Xuất PDF", tf("Đã lưu:\n{}", path))
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def _draw_report(self, tab):
        for w in self.r_box.winfo_children():
            w.destroy()
        nam = int(self.r_nam.get()) if self.r_nam.get().isdigit() else date.today().year
        if tab == "Tháng":
            rows = core.doanh_so_thang(self.con, nam)
            c = self.card(tf("Doanh số theo tháng — {}", nam), parent=self.r_box)
            b = ctk.CTkFrame(c, fg_color="transparent")
            b.pack(fill="x", padx=14, pady=(0, 12))
            if not rows:
                ctk.CTkLabel(b, text=t("Chưa có dữ liệu bán hàng trong năm."),
                             text_color=C_MUT).pack(anchor="w")
                return
            mx = max((r["doanh_so"] or 0) for r in rows) or 1
            # Đồ thị bar chart bằng canvas
            import tkinter as tk
            cv = tk.Canvas(b, height=180, bg="#ffffff", highlightthickness=0)
            cv.pack(fill="x", pady=(0, 10))
            bw, gap, base = 60, 18, 150
            for i, r in enumerate(rows):
                h = int((r["doanh_so"] or 0) / mx * 120)
                x0 = 20 + i * (bw + gap)
                cv.create_rectangle(x0, base - h, x0 + bw, base, fill=C_BRAND, outline="")
                cv.create_text(x0 + bw // 2, base - h - 8, text=f"{int(r['thang'])}",
                               font=("Segoe UI", 9, "bold"), fill=C_INK)
                cv.create_text(x0 + bw // 2, base + 12, text=money(r["doanh_so"]),
                               font=("Segoe UI", 8), fill=C_MUT)
            # Bảng chi tiết
            hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
            hd.pack(fill="x")
            for i, col_name in enumerate(["Tháng", "Số lượng", "Doanh số"]):
                ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=C_MUT, width=[80, 100, 150][i]).grid(
                    row=0, column=i, padx=4, pady=(6, 2), sticky="w")
            for idx, r in enumerate(rows):
                vals = [tf("Tháng {}", int(r['thang'])), fmt(r["so_luong"]), money(r["doanh_so"]) + " ₫"]
                for i, v in enumerate(vals):
                    ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                                 text_color=C_INK, width=[80, 100, 150][i]).grid(
                        row=idx + 1, column=i, padx=4, pady=2, sticky="w")
        elif tab == "Quý":
            # Tính quý từ dữ liệu tháng (tránh query lại)
            thang_rows = core.doanh_so_thang(self.con, nam)
            q = {}
            for r in thang_rows:
                q_idx = (int(r["thang"]) - 1) // 3 + 1
                q.setdefault(q_idx, {"so_luong": 0, "doanh_so": 0})
                q[q_idx]["so_luong"] += r["so_luong"] or 0
                q[q_idx]["doanh_so"] += r["doanh_so"] or 0
            rows = [{"quy": k, "so_luong": v["so_luong"], "doanh_so": v["doanh_so"]}
                    for k, v in sorted(q.items())]
            c = self.card(tf("Doanh số theo quý — {}", nam), parent=self.r_box)
            b = ctk.CTkFrame(c, fg_color="transparent")
            b.pack(fill="x", padx=14, pady=(0, 12))
            if not rows:
                ctk.CTkLabel(b, text=t("Chưa có dữ liệu bán hàng trong năm."),
                             text_color=C_MUT).pack(anchor="w")
                return
            mx = max((r["doanh_so"] or 0) for r in rows) or 1
            import tkinter as tk
            cv = tk.Canvas(b, height=180, bg="#ffffff", highlightthickness=0)
            cv.pack(fill="x", pady=(0, 10))
            bw, gap, base = 60, 18, 150
            for i, r in enumerate(rows):
                h = int((r["doanh_so"] or 0) / mx * 120)
                x0 = 20 + i * (bw + gap)
                cv.create_rectangle(x0, base - h, x0 + bw, base, fill=C_BRAND, outline="")
                cv.create_text(x0 + bw // 2, base - h - 8, text=tf("Quý {}", r['quy']),
                               font=("Segoe UI", 9, "bold"), fill=C_INK)
                cv.create_text(x0 + bw // 2, base + 12, text=money(r["doanh_so"]),
                               font=("Segoe UI", 8), fill=C_MUT)
            hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
            hd.pack(fill="x")
            for i, col_name in enumerate(["Quý", "Số lượng", "Doanh số"]):
                ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=C_MUT, width=[80, 100, 150][i]).grid(
                    row=0, column=i, padx=4, pady=(6, 2), sticky="w")
            for idx, r in enumerate(rows):
                vals = [tf("Quý {}", r['quy']), fmt(r["so_luong"]), money(r["doanh_so"]) + " ₫"]
                for i, v in enumerate(vals):
                    ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                                 text_color=C_INK, width=[80, 100, 150][i]).grid(
                        row=idx + 1, column=i, padx=4, pady=2, sticky="w")
        else:
            rows = core.thi_phan(self.con, nam)
            c = self.card(tf("Thị phần nội bộ — {}", nam), parent=self.r_box)
            b = ctk.CTkFrame(c, fg_color="transparent")
            b.pack(fill="x", padx=14, pady=(0, 12))
            if not rows:
                ctk.CTkLabel(b, text=t("Chưa có dữ liệu."), text_color=C_MUT).pack(anchor="w")
                return
            # Bảng chi tiết thị phần
            hd = ctk.CTkFrame(b, fg_color="#fafcfd", corner_radius=8)
            hd.pack(fill="x")
            for i, col_name in enumerate(["Khách hàng", "Thị phần", "Doanh số"]):
                ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=C_MUT, width=[250, 80, 150][i]).grid(
                    row=0, column=i, padx=4, pady=(6, 2), sticky="w")
            tong = sum((r.get("doanh_so") or 0) for r in rows) or 1
            for idx, r in enumerate(rows[:10]):
                vals = [r["ten_kh"][:30], f"{r['ti_le']:.1f}%",
                        money(r.get("doanh_so") or 0) + " ₫"]
                for i, v in enumerate(vals):
                    ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                                 text_color=C_INK, width=[250, 80, 150][i]).grid(
                        row=idx + 1, column=i, padx=4, pady=2, sticky="w")


    # ==================== 9. KÝ GỬI ====================
    def scr_kygui(self):
        """Màn hình Ký gửi: lập phiếu ký gửi / xuất ký gửi, xem tồn kho ký gửi & lịch sử."""
        self.header("Ký gửi", "Quản lý hàng ký gửi — xuất ký gửi cho khách hàng")

        # --- form ---
        c = self.card("Phiếu ký gửi")
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Khách hàng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=0, column=0, sticky="w", pady=5)
        self.kg_kh = ctk.CTkComboBox(f, values=[k["ten_kh"] for k in core.ds_khachhang(self.con)],
                                     width=380, height=32)
        self.kg_kh.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Loại phiếu"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=1, column=0, sticky="w", pady=5)
        self.kg_loai = ctk.CTkComboBox(f, values=["KYGUI", "XUAT_KYGUI"],
                                       width=200, height=32)
        self.kg_loai.set("KYGUI")
        self.kg_loai.grid(row=1, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Mã vật tư"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=2, column=0, sticky="w", pady=5)
        self.kg_ma = ctk.CTkEntry(f, width=240, height=32, placeholder_text=t("Nhập mã VT…"))
        self.kg_ma.grid(row=2, column=1, sticky="w", pady=5)
        self.kg_ma.bind("<KeyRelease>", self._on_kygui_typed)

        ctk.CTkLabel(f, text=t("Số lượng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=3, column=0, sticky="w", pady=5)
        self.kg_sl = ctk.CTkEntry(f, width=120, height=32)
        self.kg_sl.insert(0, "1")
        self.kg_sl.grid(row=3, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Khoa nhận"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=4, column=0, sticky="w", pady=5)
        self.kg_khoa = ctk.CTkEntry(f, width=240, height=32, placeholder_text=t("VD: Hồi sức ngoại"))
        self.kg_khoa.grid(row=4, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Ghi chú"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=5, column=0, sticky="w", pady=5)
        self.kg_gc = ctk.CTkEntry(f, width=380, height=32, placeholder_text=t("VD: Ký gửi theo HĐ số …"))
        self.kg_gc.grid(row=5, column=1, sticky="w", pady=5)

        self.kg_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11), text_color=C_MUT)
        self.kg_msg.grid(row=6, column=1, sticky="w", pady=(8, 0))

        ctk.CTkButton(f, text=t("Lưu phiếu ký gửi"), height=36, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._luu_kygui).grid(
            row=7, column=1, sticky="w", pady=(10, 0))

        # --- tồn kho ký gửi ---
        c2 = self.card("Tồn kho ký gửi")
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        rows_ton = core.ton_kho_kygui(self.con)
        if not rows_ton:
            ctk.CTkLabel(b2, text=t("Chưa có hàng ký gửi."),
                         text_color=C_MUT).pack(anchor="w")
        else:
            hd = ctk.CTkFrame(b2, fg_color="#fafcfd", corner_radius=8)
            hd.pack(fill="x")
            for i, col_name in enumerate(["Khách hàng", "Mã VT", "Tên vật tư", "ĐVT", "Tồn ký gửi"]):
                ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=C_MUT, width=[200, 90, 300, 50, 90][i]).grid(
                    row=0, column=i, padx=4, pady=(8, 2), sticky="w")
            for idx, r in enumerate(rows_ton):
                vals = [r["ten_kh"], r["ma_vt"], r["ten_vt"][:40], r["dvt"],
                        fmt(r["ton_kygui"])]
                for i, v in enumerate(vals):
                    ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                                 text_color=C_INK, width=[200, 90, 300, 50, 90][i]).grid(
                        row=idx + 1, column=i, padx=4, pady=3, sticky="w")

        # --- lịch sử phiếu ký gửi ---
        c3 = self.card("Lịch sử phiếu ký gửi")
        b3 = ctk.CTkFrame(c3, fg_color="transparent")
        b3.pack(fill="x", padx=14, pady=(0, 12))
        rows_kygui = core.ds_phieu(self.con, loai="KYGUI", limit=10)
        rows_xuat = core.ds_phieu(self.con, loai="XUAT_KYGUI", limit=10)
        if not rows_kygui and not rows_xuat:
            ctk.CTkLabel(b3, text=t("Chưa có phiếu ký gửi nào."),
                         text_color=C_MUT).pack(anchor="w")
        else:
            hd2 = ctk.CTkFrame(b3, fg_color="#fafcfd", corner_radius=8)
            hd2.pack(fill="x")
            for i, col_name in enumerate(["Số phiếu", "Loại", "Ngày", "Mã VT", "Tên VT", "SL"]):
                ctk.CTkLabel(hd2, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=C_MUT, width=[110, 110, 90, 90, 280, 50][i]).grid(
                    row=0, column=i, padx=4, pady=(8, 2), sticky="w")
            all_rows = [(r, "Ký gửi") for r in rows_kygui] + [(r, "Xuất ký gửi") for r in rows_xuat]
            for idx, (r, loai) in enumerate(all_rows):
                vals = [r["so_phieu"], loai, r["ngay_phieu"], r["ma_vt"],
                        (r["ten_vt"] or "")[:38], fmt(r["so_luong"])]
                for i, v in enumerate(vals):
                    ctk.CTkLabel(hd2, text=v, font=ctk.CTkFont(size=11),
                                 text_color=C_INK, width=[110, 110, 90, 90, 280, 50][i]).grid(
                        row=idx + 1, column=i, padx=4, pady=3, sticky="w")

    def _on_kygui_typed(self, _):
        q = self.kg_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if rows:
            v = rows[0]
            self.kg_msg.configure(text=f"{v['ma_vt']} — {v['ten_vt'][:44]}", text_color=C_OK)
        else:
            self.kg_msg.configure(text=t("Không tìm thấy mã vật tư."), text_color=C_BAD)

    def _luu_kygui(self):
        kh = self.kg_kh.get()
        ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                      if k["ten_kh"] == kh), None)
        q = self.kg_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if not rows:
            self.kg_msg.configure(text=t("Chọn mã vật tư hợp lệ."), text_color=C_BAD)
            return
        v = rows[0]
        try:
            sl = float(self.kg_sl.get() or 1)
        except ValueError:
            sl = 1
        loai = self.kg_loai.get()
        try:
            sp = core.ghi_phieu_kygui(
                self.con, loai, date.today().isoformat(), v["ma_vt"], sl,
                ma_kh=ma_kh, khoa_nhan=self.kg_khoa.get().strip(),
                nguoi_lap=nguoi_lap_cua(self), ghi_chu=self.kg_gc.get().strip())
            self.kg_msg.configure(text=tf("Đã lưu {} — tồn kho ký gửi đã cập nhật.", sp), text_color=C_OK)
            self.kg_ma.delete(0, "end")
            self.kg_gc.delete(0, "end")
        except Exception as e:
            self.kg_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)

    # ==================== 10. HÓA ĐƠN TRƯỚC ====================
    def scr_hoadontruoc(self):
        """Màn hình Hóa đơn trước: xuất hàng trước, hóa đơn sau — theo dõi tiến độ giao hàng."""
        self.header("Hóa đơn trước", "Xuất hàng trước, xuất hóa đơn sau — theo dõi tiến độ giao")

        # --- form ---
        c = self.card("Phiếu xuất hóa đơn trước")
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Ngày xuất"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=0, column=0, sticky="w", pady=5)
        self.hd_ngay = ctk.CTkEntry(f, width=160, height=32)
        self.hd_ngay.insert(0, date.today().isoformat())
        self.hd_ngay.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Mã vật tư"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=1, column=0, sticky="w", pady=5)
        self.hd_ma = ctk.CTkEntry(f, width=240, height=32, placeholder_text=t("Nhập mã VT…"))
        self.hd_ma.grid(row=1, column=1, sticky="w", pady=5)
        self.hd_ma.bind("<KeyRelease>", self._on_hoadon_typed)

        ctk.CTkLabel(f, text=t("Số lượng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=2, column=0, sticky="w", pady=5)
        self.hd_sl = ctk.CTkEntry(f, width=120, height=32)
        self.hd_sl.insert(0, "1")
        self.hd_sl.grid(row=2, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Khách hàng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=3, column=0, sticky="w", pady=5)
        self.hd_kh = ctk.CTkComboBox(f, values=[k["ten_kh"] for k in core.ds_khachhang(self.con)],
                                     width=380, height=32)
        self.hd_kh.grid(row=3, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Số hóa đơn *"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=4, column=0, sticky="w", pady=5)
        self.hd_so = ctk.CTkEntry(f, width=240, height=32, placeholder_text="VD: 001/2026/HD")
        self.hd_so.grid(row=4, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Số hợp đồng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=5, column=0, sticky="w", pady=5)
        self.hd_hd = ctk.CTkEntry(f, width=240, height=32, placeholder_text="VD: 04-21/BVLKTW-CV")
        self.hd_hd.grid(row=5, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Ghi chú"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=6, column=0, sticky="w", pady=5)
        self.hd_gc = ctk.CTkEntry(f, width=380, height=32, placeholder_text=t("VD: Xuất trước theo yêu cầu…"))
        self.hd_gc.grid(row=6, column=1, sticky="w", pady=5)

        self.hd_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11), text_color=C_MUT)
        self.hd_msg.grid(row=7, column=1, sticky="w", pady=(8, 0))

        ctk.CTkButton(f, text=t("Lưu"), height=36, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._luu_hoadon).grid(
            row=8, column=1, sticky="w", pady=(10, 0))

        # --- bảng tiến độ ---
        c2 = self.card("Tiến độ hóa đơn trước")
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        rows = core.tien_do_hoadon_truoc(self.con)
        if not rows:
            ctk.CTkLabel(b2, text=t("Chưa có dữ liệu hóa đơn trước."),
                         text_color=C_MUT).pack(anchor="w")
        else:
            hd = ctk.CTkFrame(b2, fg_color="#fafcfd", corner_radius=8)
            hd.pack(fill="x")
            for i, col_name in enumerate(["Số HĐ", "Khách hàng", "Mã VT", "Tên VT",
                                   "SL đã xuất", "SL đã giao", "Còn lại"]):
                ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=C_MUT, width=[110, 200, 90, 280, 80, 80, 60][i]).grid(
                    row=0, column=i, padx=4, pady=(8, 2), sticky="w")
            for idx, r in enumerate(rows):
                vals = [r["so_hoa_don"], r["ten_kh"], r["ma_vt"],
                        (r["ten_vt"] or "")[:38], fmt(r["sl_da_xuat_hd"]),
                        fmt(r["sl_da_giao"]), fmt(r["sl_con_lai"])]
                for i, v in enumerate(vals):
                    ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                                 text_color=C_INK, width=[110, 200, 90, 280, 80, 80, 60][i]).grid(
                        row=idx + 1, column=i, padx=4, pady=3, sticky="w")

    def _on_hoadon_typed(self, _):
        q = self.hd_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if rows:
            v = rows[0]
            self.hd_msg.configure(text=f"{v['ma_vt']} — {v['ten_vt'][:44]}", text_color=C_OK)
        else:
            self.hd_msg.configure(text=t("Không tìm thấy mã vật tư."), text_color=C_BAD)

    def _luu_hoadon(self):
        kh = self.hd_kh.get()
        ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                      if k["ten_kh"] == kh), None)
        q = self.hd_ma.get().strip()
        rows = core.ds_vattu(self.con, q) if q else []
        if not rows:
            self.hd_msg.configure(text=t("Chọn mã vật tư hợp lệ."), text_color=C_BAD)
            return
        v = rows[0]
        so_hd = self.hd_so.get().strip()
        if not so_hd:
            self.hd_msg.configure(text=t("Số hóa đơn là bắt buộc."), text_color=C_BAD)
            return
        try:
            sl = float(self.hd_sl.get() or 1)
        except ValueError:
            sl = 1
        try:
            sp = core.xuat_hoadon_truoc(
                self.con, self.hd_ngay.get().strip() or date.today().isoformat(),
                v["ma_vt"], sl, ma_kh=ma_kh, so_hoa_don=so_hd,
                so_hop_dong=self.hd_hd.get().strip(), nguoi_lap=nguoi_lap_cua(self),
                ghi_chu=self.hd_gc.get().strip())
            self.hd_msg.configure(text=tf("Đã lưu {} — tiến độ hóa đơn đã cập nhật.", sp), text_color=C_OK)
            self.hd_ma.delete(0, "end")
            self.hd_so.delete(0, "end")
            self.hd_hd.delete(0, "end")
            self.hd_gc.delete(0, "end")
        except Exception as e:
            self.hd_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)

    # ==================== 11. LỊCH SỬ KHÁCH HÀNG ====================
    def scr_lichsu(self):
        """Màn hình Lịch sử khách hàng: tra cứu giao dịch theo khách hàng & khoảng thời gian."""
        self.header("Lịch sử khách hàng", "Tra cứu giao dịch theo khách hàng & khoảng thời gian")

        # --- form tìm kiếm ---
        c = self.card("Tìm kiếm")
        f = ctk.CTkFrame(c, fg_color="transparent")
        f.pack(fill="x", padx=14, pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text=t("Khách hàng"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=0, column=0, sticky="w", pady=5)
        self.ls_kh = ctk.CTkComboBox(f, values=[k["ten_kh"] for k in core.ds_khachhang(self.con)],
                                     width=380, height=32)
        self.ls_kh.grid(row=0, column=1, sticky="w", pady=5)

        ctk.CTkLabel(f, text=t("Từ ngày"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=1, column=0, sticky="w", pady=5)
        self.ls_tu = ctk.CTkEntry(f, width=160, height=32, placeholder_text="YYYY-MM-DD")
        self.ls_tu.grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.ls_tu)).grid(
            row=1, column=2, sticky="w", padx=(4, 0))

        ctk.CTkLabel(f, text=t("Đến ngày"), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUT, width=110).grid(row=2, column=0, sticky="w", pady=5)
        self.ls_den = ctk.CTkEntry(f, width=160, height=32, placeholder_text="YYYY-MM-DD")
        self.ls_den.grid(row=2, column=1, sticky="w", pady=5)
        ctk.CTkButton(f, text="📅", width=36, height=32,
                      command=lambda: self._chon_ngay(self.ls_den)).grid(
            row=2, column=2, sticky="w", padx=(4, 0))

        self.ls_msg = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11), text_color=C_MUT)
        self.ls_msg.grid(row=3, column=1, sticky="w", pady=(8, 0))

        ctk.CTkButton(f, text=t("Tìm"), height=36, fg_color=C_BRAND,
                      hover_color="#12a3af", command=self._tim_lichsu).grid(
            row=4, column=1, sticky="w", pady=(10, 0))

        # --- bảng kết quả ---
        c2 = self.card("Kết quả")
        b2 = ctk.CTkFrame(c2, fg_color="transparent")
        b2.pack(fill="x", padx=14, pady=(0, 12))
        self.ls_box = b2  # lưu để _tim_lichsu render vào

    def _tim_lichsu(self):
        kh = self.ls_kh.get()
        ma_kh = next((k["ma_kh"] for k in core.ds_khachhang(self.con)
                      if k["ten_kh"] == kh), None)
        if not ma_kh:
            self.ls_msg.configure(text=t("Vui lòng chọn khách hàng."), text_color=C_BAD)
            return
        tu = self.ls_tu.get().strip()
        den = self.ls_den.get().strip()
        try:
            rows = core.lich_su_khachhang(self.con, ma_kh, tu, den)
        except Exception as e:
            self.ls_msg.configure(text=tf("Lỗi: {}", e), text_color=C_BAD)
            return
        # render kết quả
        for w in self.ls_box.winfo_children():
            w.destroy()
        if not rows:
            ctk.CTkLabel(self.ls_box, text=t("Không tìm thấy giao dịch nào."),
                         text_color=C_MUT).pack(anchor="w")
            return
        hd = ctk.CTkFrame(self.ls_box, fg_color="#fafcfd", corner_radius=8)
        hd.pack(fill="x")
        for i, col_name in enumerate(["Số phiếu", "Loại", "Ngày", "Mã VT", "Tên VT",
                               "SL", "Đơn giá", "Thành tiền"]):
            ctk.CTkLabel(hd, text=col_name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_MUT, width=[110, 100, 90, 90, 250, 50, 100, 110][i]).grid(
                    row=0, column=i, padx=4, pady=(8, 2), sticky="w")
        for idx, r in enumerate(rows):
            vals = [r["so_phieu"], r["loai"], r["ngay"], r["ma_vt"],
                    (r["ten_vt"] or "")[:36], fmt(r["so_luong"]),
                    fmt(r["don_gia"]), fmt(r["thanh_tien"])]
            for i, v in enumerate(vals):
                ctk.CTkLabel(hd, text=v, font=ctk.CTkFont(size=11),
                             text_color=C_INK, width=[110, 100, 90, 90, 250, 50, 100, 110][i]).grid(
                        row=idx + 1, column=i, padx=4, pady=3, sticky="w")


if __name__ == "__main__":
    import sys, os, traceback
    LOG_FILE = os.path.join(os.path.dirname(sys.executable), "app.log")
    def log(msg):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    import time
    log("=== MAIN START ===")
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc(file=open(LOG_FILE, "a"))
    log("=== MAIN END ===")
