---
name: evidence-based-code-review
description: >
  Skill review code có bằng chứng: không kết luận gì nếu chưa chạy. Dùng khi
  được yêu cầu đánh giá/review một repo, một PR, một file code, hoặc nghiệm
  thu bản vá do agent khác viết. Bao gồm quy trình 7 bước, phân loại P0/P1/P2,
  mẫu báo cáo, và các anti-pattern cần tránh.
---

# SKILL: CODE REVIEW CÓ BẰNG CHỨNG (EVIDENCE-BASED CODE REVIEW)

## 5 ĐIỀU LUẬT (không có ngoại lệ)

1. **CHẠY TRƯỚC KHI KẾT LUẬN.** "Đọc code thấy có vẻ sai" chưa phải phát hiện.
   Phát hiện = tái hiện được bằng lệnh và dán output vào báo cáo. Không chạy
   được (thiếu môi trường) → nói rõ "chưa kiểm chứng bằng thực thi", không
   được khẳng định.
2. **MỌI TUYÊN BỐ LÀ GIẢ THUYẾT CẦN BÁC BỎ.** Commit message, README,
   docstring, mô tả PR, chữ "Tests PASS" — tất cả đều là *lời khai*, không phải
   *sự thật*. Đối chiếu từng lời khai với diff (`git show <hash>`) và với hành
   vi chạy thật. Lời khai sai lệch phải được nêu đích danh kèm bằng chứng.
3. **CHỈ TRÍCH CODE, KHÔNG CHỈ TRÍCH NGƯỜI.** Mỗi nhận định gắn `file:dòng`
   hoặc output lệnh. Giọng có thể thẳng và gay gắt khi được yêu cầu, nhưng
   không suy đoán động cơ, không miệt thị.
4. **TEST THEO CONTRACT, KHÔNG THEO VÍ DỤ.** Đừng chỉ chạy các ví dụ đẹp mà
   tài liệu liệt kê (code thường được "overfit" cho đúng những ví dụ đó).
   Hãy sinh input đối kháng: biên, null, rỗng, sai định dạng, số âm, unicode,
   định dạng vùng miền (dấu phẩy/chấm), giá trị khổng lồ, injection.
5. **XẾP HẠNG THEO TÁC ĐỘNG LÊN NGƯỜI DÙNG**, không theo số dòng hay độ khó
   nhìn. Một chứng từ in thiếu hàng nặng hơn mười dòng dài quá 88 ký tự.

---

## QUY TRÌNH 7 BƯỚC

### Bước 1 — Trinh sát (5 phút, không kết luận)
```bash
git clone <repo> && cd <repo>
git log --oneline --stat | head -60      # lịch sử: commit dump nguyên khối? message có khớp diff?
find . -type f -name "*.py" | xargs wc -l | sort -n | tail   # file khổng lồ?
cat README* docs/* 2>/dev/null           # ghi ra DANH SÁCH CLAIM cần kiểm chứng
```
- Lập **bảng claim**: mỗi câu README/commit message hứa một tính năng → 1 dòng
  để đối chiếu về sau ("có bản Web", "PDF có chữ ký số", "Tests 45/45 PASS"...).
- Xác định **entry point** (main/exe/server/CLI) và **luồng tiền-tính-mạng**
  của sản phẩm (với app bán hàng: ghi phiếu → tính tiền → in chứng từ).

### Bước 2 — Cổng tĩnh (static gates)
```bash
python3 -m py_compile <mọi file>         # hoặc build/compile của ngôn ngữ khác
ruff check src/ --select F,E7,E9,B,W6    # (Python) nhóm rule bắt lỗi THẬT, bỏ qua style ồn ào
ruff check src/ --statistics             # đếm, để đưa con số khách quan vào báo cáo
grep -rn "except:\s*$\|except: pass" src/            # nuốt lỗi
grep -rn "C:\\\\Users\|/home/\|/Users/" src/         # đường dẫn cá nhân bị commit
grep -rn "TODO\|FIXME\|HACK" src/
grep -rniE "password\s*=\s*['\"]|secret\s*=\s*['\"]|api_key" src/   # secret hardcode
```
Ghi nhận: số lỗi theo nhóm, file:dòng. **Chưa kết luận gì.**

### Bước 3 — Cổng động (dynamic gates) — QUAN TRỌNG NHẤT
Thứ tự bắt buộc:
1. **Chạy test suite của chính repo** → ghi output thật (kể cả khi PASS: PASS
   của repo chỉ chứng minh những gì repo *chọn* kiểm tra).
2. **Đọc test để biết vùng mù**: test render những màn nào? có bấm nút xuất/in
   không? có test luồng đóng gói (exe/docker) không? có assert hành vi SAI
   thành đúng không (test đóng băng bug)?
3. **Viết script tái hiện nghi ngờ** — mỗi bug một script nhỏ, chạy, dán output:
```python
# prove_bug.py — gọi ĐÚNG cách app gọi (qua GUI handler, không chỉ qua core)
```
4. **Smoke test sản phẩm THẬT, không phải dev-mode**: nếu có spec đóng gói →
   build → chạy binary → kiểm tra log/DB/port. Nếu là web → khởi động server →
   curl endpoint. GUI → Xvfb/headless. **Đây là bước phát hiện nhiều P0 nhất**
   (app "chạy tốt" trong dev nhưng DOA khi đóng gói là bệnh kinh điển).
5. **Test hàm parse/format tiền-số-ngày** bằng bảng input đối kháng (điều luật 4).

### Bước 4 — Đối chiếu claim ↔ thực tế
- `git show <commit>` cho từng tuyên bố trong message: diff có chứa việc đó không?
- README hứa file/thư mục/tính năng nào → `ls`, `grep` chứng minh có/không.
- Docstring mô tả hành vi → chạy hàm với đúng input trong docstring → so kết quả.
- **Phân biệt 3 mức**: claim đúng, claim phóng đại, claim mô tả thứ không tồn
  tại. Mức 3 là red flag về *quy trình* (thường là AI sinh text không ai soát).

### Bước 5 — Kiến trúc & nghiệp vụ (đọc sâu, sau khi đã có bằng chứng động)
Checklist tối thiểu:
- **Tầng**: nghiệp vụ có nằm ở 1 nơi? GUI có tự viết SQL/business rule không?
- **Atomicity**: thao tác nhiều dòng có transaction không? lỗi giữa chừng để
  lại trạng thái gì? lưu lại lần nữa có nhân bản không?
- **Tiền & ngày**: float cho tiền? ngày là chuỗi tự do không validate?
  so sánh chuỗi với `date('now')`?
- **Error handling**: `except Exception: pass` ở đâu? lỗi có đến được người dùng?
- **Dead code**: hàm/bảng/cơ chế nào không ai gọi? (grep tên hàm trên toàn repo)
- **Trùng lặp logic**: 2 nơi tính cùng một con số có ra cùng kết quả không?
- **Mô hình dữ liệu**: khóa chính có diễn đạt đúng thực thể không (VD "phiếu"
  1 dòng trong khi nghiệp vụ là phiếu nhiều mặt hàng)?

### Bước 6 — Bảo mật
- Quyền được kiểm tra ở đâu: UI (ẩn nút) / API / DB? UI-only = sân khấu.
- Dữ liệu tại chỗ (SQLite/file) có trần không? hash mật khẩu? đường downgrade
  (hash legacy, salt cứng)? mật khẩu mặc định công khai?
- Injection: SQL ghép bằng f-string/%? `eval`/`exec`? đường dẫn người dùng nhập?
- Secret trong repo, trong log, trong tên file (đường dẫn cá nhân cũng là leak).

### Bước 7 — Báo cáo (mẫu bên dưới) + lộ trình sửa
- Viết xong báo cáo: **tự kiểm báo cáo bằng chính điều luật 1** — mọi câu
  "code sẽ X" trong báo cáo phải có output đi kèm.
- Nếu được yêu cầu sửa: sửa → thêm test tái hiện → chạy toàn bộ gate → chỉ
  giao khi xanh. Không giao "bản vá chưa chạy".

---

## PHÂN LOẠI MỨC ĐỘ

| Mức | Định nghĩa | Ví dụ |
|---|---|---|
| **P0** | Sản phẩm hỏng ở luồng chính / mất dữ liệu / chứng từ sai / không khởi động được ở dạng phân phối | exe crash khi mở; giỏ 2 mặt in biên bản 1 mặt; parse tiền ×100; DB trong thư mục tạm bị xóa |
| **P1** | Sai trong điều kiện thường gặp nhưng không chết ngay; bảo mật yếu có hệ thống; test đóng băng bug | âm kho không chặn; thiếu commit; phân quyền UI-only; font PDF thiếu glyph |
| **P2** | Chất lượng dài hạn | god-class, dead code, lint, i18n key hỏng, README sai, thiếu requirements/CI |

Mỗi phát hiện trong báo cáo **bắt buộc** có: `file:dòng` + bằng chứng chạy
được (hoặc ghi rõ "chưa thực thi được vì X") + mức P + cách sửa đề xuất.

---

## MẪU BÁO CÁO

```markdown
# Review <repo> @ <commit hash> — <ngày>
## Phán quyết: <X/10 từng hạng mục + tổng> — 1 câu tóm tắt bệnh gốc
## 1. Lỗi P0 (bảng: # | phát hiện | file:dòng | bằng chứng đã chạy | cách sửa)
## 2. P1, P2 (tương tự)
## 3. Claim vs thực tế (bảng: tuyên bố | nguồn tuyên bố | kết quả đối chiếu)
## 4. Bệnh quy trình (nguyên nhân gốc — phần này giá trị hơn danh sách bug)
## 5. Điểm tốt thật sự (công bằng, có kiểm chứng)
## 6. Lộ trình sửa P0 → P1 → P2 (kèm lệnh kiểm chứng cho từng mục)
## Phụ lục: script tái hiện + output nguyên văn
```

---

## ANTI-PATTERN CỦA NGƯỜI REVIEW (tự soi trước khi nộp báo cáo)

1. Review bằng mắt, kết luận bằng niềm tin → vi phạm điều luật 1.
2. Chỉ test đúng ví dụ trong docstring của code → bị overfit qua mặt.
3. Nitpick style (đặt tên, độ dài dòng) trong khi luồng tiền/tính mạng đang sai.
4. Kết tội không kèm `file:dòng` → không ai sửa được, không ai tin được.
5. "Gay gắt" = lăng mạ người viết. Gay gắt đúng = không nương tay với *code*
   và *quy trình*, kèm đường sửa cụ thể.
6. Đề xuất bản vá mà chưa chạy bản vá (bệnh hay gặp ở agent: sinh patch "trông
   đúng"). Patch giao cho người dùng phải qua cổng: compile → lint → test cũ →
   test tái hiện mới → smoke sản phẩm thật.
7. Bỏ qua "test assert hành vi sai" — test xanh không có nghĩa là đúng; test
   có thể đang đóng băng bug thành đặc tả.
8. Quên kiểm tra dạng PHÂN PHỐI (exe/docker/build) — nơi dev-mode không cứu được.

---

## CHECKLIST CHO AGENT VIẾT/SỬA CODE (gate trước khi commit)

```
[ ] compile/import được toàn bộ file đã sửa
[ ] lint sạch (nhóm rule bắt lỗi thật: F,E7,E9,B...)
[ ] test suite cũ của repo: XẠCH (nếu đỏ: sửa code hoặc chỉ rõ test sai + sửa test có lý do)
[ ] có test MỚI tái hiện đúng bug vừa sửa (red → green)
[ ] chạy sản phẩm thật ≥ 1 lần theo đường người dùng đi (không phải chỉ chạy test)
[ ] nếu có đóng gói: build + smoke-run binary (log, DB, tài nguyên)
[ ] docstring/comment mô tả ĐÚNG hành vi sau sửa (đọc lại từng câu)
[ ] commit message = những gì diff THẬT SỰ làm (dán diff vào mà đối chiếu)
[ ] không đường dẫn cá nhân / secret / dữ liệu thật trong diff
```

---

## VÍ DỤ THỰC CHIẾN (từ review qlvt-yte, 10/2026)

Các phát hiện P0 đều đến từ Bước 3 (chạy thật), không phải từ đọc:
- `xuat_pdf() takes 2 positional arguments but 3 were given` — GUI và core lệch
  chữ ký 3 commit mà "Tests 45/45 PASS" vẫn xanh, vì test không bấm nút PDF.
- Docstring tuyên bố `"147000.00" → 147000.0` nhưng thân hàm trả `14700000.0`
  — chạy 1 lệnh `python -c` là lật đổ cả docstring.
- Exe build từ spec thiếu `neutral_theme.json` → chết im lặng (console=False);
  chỉ phát hiện bằng cách build + chạy binary.
- Test GUI assert `tồn kho == -25` sau khi bán hàng chưa từng nhập → bug âm
  kho được đóng băng thành "hành vi đúng".
- Commit message "Thêm lang param cho xuat_pdf" nhưng `git show` chứng minh
  file core không hề được sửa trong commit đó.

Bài học: **nguồn sự thật duy nhất là code chạy được + diff trên remote.**
Mọi thứ khác (message, doc, lời hứa) đều phải kiểm chứng chéo.
