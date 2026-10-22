-- Schema QLVT Y te — 6 bảng (đúng theo đề xuất)
-- SQLite 3.x, chạy local, không cần server

PRAGMA journal_mode = WAL;      -- cho phép đọc song song khi ghi
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;     -- tránh 'database is locked' khi 2 cửa sổ cùng ghi

-- 1. Danh mục vật tư
CREATE TABLE IF NOT EXISTS dm_vattu (
  ma_vt        TEXT PRIMARY KEY,
  ten_vt       TEXT NOT NULL,
  dvt          TEXT,
  hang_sx      TEXT,
  nuoc_sx      TEXT,
  nhom_vt      TEXT,
  so_dk        TEXT,
  don_gia      REAL DEFAULT 0,
  ton_toi_thieu REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_vattu_ten ON dm_vattu(ten_vt);

-- 2. Danh mục khách hàng
CREATE TABLE IF NOT EXISTS dm_khachhang (
  ma_kh     TEXT PRIMARY KEY,
  ten_kh    TEXT NOT NULL,
  dia_chi   TEXT,
  ma_so_thue TEXT,
  khu_vuc   TEXT
);

-- 3. Bảng giá theo khách hàng (thay sheet PrDetail)
CREATE TABLE IF NOT EXISTS bang_gia (
  ma_vt    TEXT NOT NULL REFERENCES dm_vattu(ma_vt),
  ma_kh    TEXT NOT NULL REFERENCES dm_khachhang(ma_kh),
  don_gia  REAL NOT NULL,
  PRIMARY KEY (ma_vt, ma_kh)
);

-- 4. Sổ giao dịch — NGUỒN DUY NHẤT. Nhập/xuất/ký gửi chỉ là loại phiếu
CREATE TABLE IF NOT EXISTS phieu_giaodich (
  so_phieu     TEXT PRIMARY KEY,
  loai_phieu   TEXT NOT NULL CHECK (loai_phieu IN
                 ('NHAP','XUAT','KYGUI','XUAT_KYGUI','XUAT_HOADON_TRUOC')),
  ngay_phieu   TEXT NOT NULL,
  ma_vt        TEXT NOT NULL REFERENCES dm_vattu(ma_vt),
  so_lo        TEXT,
  han_su_dung  TEXT,
  so_luong     REAL NOT NULL CHECK (so_luong <> 0),
  don_gia      REAL NOT NULL DEFAULT 0,
  thanh_tien   REAL GENERATED ALWAYS AS (so_luong * don_gia) STORED,
  ma_kh        TEXT REFERENCES dm_khachhang(ma_kh),
  khoa_nhan    TEXT,
  nguoi_goi    TEXT,
  so_hop_dong  TEXT,
  so_hoa_don   TEXT,
  nguoi_lap    TEXT,
  ngay_lap     TEXT,
  ghi_chu      TEXT
);
CREATE INDEX IF NOT EXISTS ix_pgd_vattu ON phieu_giaodich(ma_vt, ngay_phieu);
CREATE INDEX IF NOT EXISTS ix_pgd_kh    ON phieu_giaodich(ma_kh, ngay_phieu);
CREATE INDEX IF NOT EXISTS ix_pgd_loai  ON phieu_giaodich(loai_phieu, ngay_phieu);

-- 5. Hợp đồng thầu
CREATE TABLE IF NOT EXISTS hop_dong (
  so_hd          TEXT NOT NULL,
  ma_kh          TEXT NOT NULL REFERENCES dm_khachhang(ma_kh),
  ma_vt          TEXT NOT NULL REFERENCES dm_vattu(ma_vt),
  so_luong       REAL NOT NULL,
  don_gia        REAL DEFAULT 0,
  ngay_ky        TEXT,
  ngay_hieu_luc  TEXT,
  ngay_het_han   TEXT,
  ngay_giao_lan_dau TEXT,
  PRIMARY KEY (so_hd, ma_vt)
);

-- 6. Công việc
CREATE TABLE IF NOT EXISTS cong_viec (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  noi_dung     TEXT NOT NULL,
  ma_kh        TEXT REFERENCES dm_khachhang(ma_kh),
  khoa         TEXT,
  nguoi_lien_he TEXT,
  nguoi_giao   TEXT,
  deadline     TEXT,
  muc_do       TEXT,
  trang_thai   TEXT DEFAULT 'Đang làm',
  ghi_chu      TEXT
);

-- Nhật ký thao tác — truy vết ai sửa gì
CREATE TABLE IF NOT EXISTS audit_log (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  thoi_gian TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  nguoi     TEXT,
  hanh_dong TEXT,
  doi_tuong TEXT,
  chi_tiet  TEXT
);

-- 7. Users — đăng nhập & phân quyền (dùng chung cho Desktop và Web)
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  username   TEXT UNIQUE NOT NULL,
  password   TEXT NOT NULL,               -- bcrypt hash (fallback: pbkdf2_sha256)
  ten_hien_thi TEXT NOT NULL,
  email      TEXT,
  vai_tro    TEXT NOT NULL DEFAULT 'nhanvien'
             CHECK (vai_tro IN ('admin','kinhdoanh','ketoan','kho','nhanvien')),
  hoat_dong  INTEGER NOT NULL DEFAULT 1,
  khoa       TEXT,                        -- phòng ban: KD / KT / KHO / IT
  lan_cuoi_dang_nhap TEXT,
  lan_doi_mk TEXT,                        -- bắt buộc đổi mật khẩu ở lần đăng nhập kế
  tao_luc    TEXT DEFAULT (datetime('now','localtime'))
);

-- 8. Phiên đăng nhập — token có chữ ký HMAC, lưu hash token trong DB
--    (không lưu token gốc) → server khởi động lại vẫn nhận phiên cũ, và
--    một token bị lọt không đọc được nội dung từ DB.
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tao_luc    TEXT DEFAULT (datetime('now','localtime')),
  het_han    TEXT NOT NULL,
  ip         TEXT,
  user_agent TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);

-- ===== VIEWS: tồn kho & báo cáo tính tự động, không lưu trữ =====

-- Tồn kho công ty (thay hoàn toàn VBA TonKhoCty)
CREATE VIEW IF NOT EXISTS v_tonkho AS
SELECT v.ma_vt, v.ten_vt, v.dvt, v.don_gia, v.ton_toi_thieu,
       SUM(CASE WHEN p.loai_phieu='NHAP' THEN p.so_luong ELSE -p.so_luong END) AS ton_kho,
       SUM(CASE WHEN p.loai_phieu='NHAP' THEN p.so_luong ELSE -p.so_luong END)
         * v.don_gia AS gia_tri_ton
FROM dm_vattu v
LEFT JOIN phieu_giaodich p ON p.ma_vt = v.ma_vt
  AND p.loai_phieu IN ('NHAP','XUAT')
GROUP BY v.ma_vt;

-- Tồn kho phân nhóm hạn sử dụng
CREATE VIEW IF NOT EXISTS v_tonkho_hansudung AS
SELECT ma_vt,
  SUM(so_luong_rong) FILTER (WHERE hs_group = '>10th')  AS nhom_tren_10th,
  SUM(so_luong_rong) FILTER (WHERE hs_group = '8-10th') AS nhom_8_10th,
  SUM(so_luong_rong) FILTER (WHERE hs_group = '3-8th')  AS nhom_3_8th,
  SUM(so_luong_rong) FILTER (WHERE hs_group = '<3th')   AS nhom_duoi_3th,
  SUM(so_luong_rong) FILTER (WHERE hs_group = 'het_han') AS het_han
FROM (
  SELECT ma_vt,
    CASE WHEN han_su_dung IS NULL THEN 'khong_hsd'
         WHEN han_su_dung < date('now') THEN 'het_han'
         WHEN han_su_dung < date('now','+3 month') THEN '<3th'
         WHEN han_su_dung < date('now','+8 month') THEN '3-8th'
         WHEN han_su_dung < date('now','+10 month') THEN '8-10th'
         ELSE '>10th' END AS hs_group,
    CASE WHEN loai_phieu='NHAP' THEN so_luong ELSE -so_luong END AS so_luong_rong
  FROM phieu_giaodich WHERE loai_phieu IN ('NHAP','XUAT')
)
GROUP BY ma_vt;

-- Doanh số theo tháng
CREATE VIEW IF NOT EXISTS v_doanhso_thang AS
SELECT substr(ngay_phieu,1,7) AS thang,
       ma_kh, ma_vt,
       SUM(so_luong) AS so_luong,
       SUM(thanh_tien) AS doanh_so
FROM phieu_giaodich
WHERE loai_phieu IN ('XUAT','XUAT_KYGUI')
GROUP BY thang, ma_kh, ma_vt;

-- Tiến độ hợp đồng (đã thực hiện / còn lại)
CREATE VIEW IF NOT EXISTS v_tiendo_hopdong AS
SELECT h.so_hd, h.ma_kh, h.ma_vt, h.so_luong, h.don_gia,
       COALESCE(t.da_thuc_hien,0) AS da_thuc_hien,
       h.so_luong - COALESCE(t.da_thuc_hien,0) AS con_lai
FROM hop_dong h
LEFT JOIN (
  SELECT so_hop_dong, ma_vt, SUM(so_luong) AS da_thuc_hien
  FROM phieu_giaodich WHERE loai_phieu='XUAT' AND so_hop_dong IS NOT NULL
  GROUP BY so_hop_dong, ma_vt
) t ON t.so_hop_dong = h.so_hd AND t.ma_vt = h.ma_vt;

-- Tồn kho ký gửi theo bệnh viện (thay sheet CsStock)
CREATE VIEW IF NOT EXISTS v_ton_kho_kygui AS
SELECT k.ma_kh, k.ten_kh, v.ma_vt, v.ten_vt, v.dvt,
       SUM(CASE WHEN p.loai_phieu='KYGUI' THEN p.so_luong
                WHEN p.loai_phieu='XUAT_KYGUI' THEN -p.so_luong
                ELSE 0 END) AS ton_kygui
FROM phieu_giaodich p
JOIN dm_vattu v ON v.ma_vt = p.ma_vt
JOIN dm_khachhang k ON k.ma_kh = p.ma_kh
WHERE p.loai_phieu IN ('KYGUI','XUAT_KYGUI')
GROUP BY k.ma_kh, k.ten_kh, v.ma_vt, v.ten_vt, v.dvt
HAVING SUM(CASE WHEN p.loai_phieu='KYGUI' THEN p.so_luong
              WHEN p.loai_phieu='XUAT_KYGUI' THEN -p.so_luong ELSE 0 END) <> 0;

-- Xuất hóa đơn trước: số lượng đã xuất hóa đơn / chưa xuất (thay sheet Invoice in advance)
CREATE VIEW IF NOT EXISTS v_xuat_hoadon_truoc AS
SELECT p.ma_kh, k.ten_kh, p.so_hop_dong, p.so_hoa_don, p.ngay_phieu AS ngay_xuat_hd,
       p.ma_vt, v.ten_vt, v.dvt, p.so_luong AS sl_da_xuat_hd,
       COALESCE(t.sl_da_giao,0) AS sl_da_giao,
       p.so_luong - COALESCE(t.sl_da_giao,0) AS sl_con_lai
FROM phieu_giaodich p
JOIN dm_khachhang k ON k.ma_kh = p.ma_kh
JOIN dm_vattu v ON v.ma_vt = p.ma_vt
LEFT JOIN (
  SELECT so_hoa_don, ma_vt, SUM(so_luong) AS sl_da_giao
  FROM phieu_giaodich WHERE loai_phieu='XUAT' AND so_hoa_don IS NOT NULL
  GROUP BY so_hoa_don, ma_vt
) t ON t.so_hoa_don = p.so_hoa_don AND t.ma_vt = p.ma_vt
WHERE p.loai_phieu='XUAT_HOADON_TRUOC';

-- Lịch sử giao dịch của 1 khách hàng (tra cứu nhanh)
CREATE VIEW IF NOT EXISTS v_lich_su_khachhang AS
SELECT k.ma_kh, k.ten_kh, p.so_phieu, p.loai_phieu, p.ngay_phieu,
       p.ma_vt, v.ten_vt, v.dvt, p.so_luong, p.don_gia, p.thanh_tien,
       p.khoa_nhan, p.nguoi_goi, p.so_hop_dong, p.so_hoa_don, p.nguoi_lap, p.ngay_lap
FROM phieu_giaodich p
JOIN dm_khachhang k ON k.ma_kh = p.ma_kh
JOIN dm_vattu v ON v.ma_vt = p.ma_vt
WHERE p.ma_kh IS NOT NULL
ORDER BY p.ngay_phieu DESC, p.ngay_lap DESC;
