# Bot nhắc lịch học – Y3 Y2024 (K2), năm học 2026-2027

Chạy hoàn toàn trên GitHub Actions + Telegram (miễn phí, không cần server).

## Bot làm gì
| Khi nào | Gì |
|---|---|
| 07:00 sáng Chủ nhật | Lịch học tuần sau (chỉ mục có K2 / K1+2; không có lớp = "tự học") |
| 1 ngày, 1 giờ, 15 phút trước giờ mở pretest | Nhắc pretest: `MODULE – TÊN BÀI`, `Thứ · ngày · giờ mở` |
| Cuối MỌI tin bot gửi | Các kỳ thi trong 30 ngày tới |
| Bấm tay (Actions → Run workflow) | `lich-hoc` (+ ngày tuỳ chọn), `lich-thi` (tất cả kỳ thi còn lại), `pretest`, `khdt` (ảnh Kế hoạch đào tạo) |

## Cài đặt (làm 1 lần)
1. Telegram: nhắn `@BotFather` → `/newbot` → lấy **token**.
2. Nhắn bot của bạn 1 tin bất kỳ, mở `https://api.telegram.org/bot<TOKEN>/getUpdates` → lấy `chat.id` (số). Có thể điền nhiều id, cách nhau dấu phẩy.
3. Tạo repo GitHub (public), đẩy toàn bộ thư mục này lên.
4. Repo → Settings → Secrets and variables → Actions → thêm `TG_BOT_TOKEN`, `TG_CHAT_ID`.
5. Actions → bot-lich-hoc → Run workflow → `lich-hoc` để thử. Thử thêm `khdt`.
6. Đổi khối: sửa `USER_K: "2"` trong `.github/workflows/bot.yml`.

## Nhắc pretest đúng giờ (khuyên dùng cron-job.org)
GitHub cron có thể trễ vài phút đến hơn chục phút. Để đúng giờ hơn: tạo job trên cron-job.org chạy mỗi 5 phút, 15:00–18:59 giờ VN (múi giờ Asia/Ho_Chi_Minh):
- URL: `https://api.github.com/repos/<USER>/<REPO>/actions/workflows/bot.yml/dispatches`
- Method POST, Headers: `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`
- Body: `{"ref":"main","inputs":{"cmd":"tick"}}`
- PAT: fine-grained token, chỉ repo này, quyền Actions: Read and write.

`tick` chạy nhiều lần không bị gửi trùng (trạng thái lưu ở `data/sent.json`). Nếu chạy trễ, bot chỉ gửi mốc gần nhất còn hợp lệ và bỏ qua mốc đã quá.

## Cập nhật năm học sau
1. Chuyển file mới sang `.docx` / `.xlsx` (Word/Excel "Lưu thành", hoặc `soffice --headless --convert-to docx`).
2. `pip install python-docx openpyxl`
3. `python tools/parse_weekly.py <lịch tuần>.docx data/schedule.json`
4. `python tools/parse_exams.py <lịch thi>.xlsx data` (tự bắt lỗi thứ-ngày, in ra những chỗ đã sửa năm)
5. `python tools/check.py` (kiểm tra tuần liên tục, không chồng giờ)
6. KHDT → PDF → `pdftoppm -r 130 -png KHDT.pdf assets/khdt`
7. Thử: `DRY_RUN=1 NOW=2026-11-15T07:00 python scripts/notify.py weekly`

## Lưu ý
- Repo public: GitHub tắt cron sau 60 ngày không có hoạt động; mỗi lần gửi lịch tuần bot ghi `data/heartbeat.txt` để giữ hoạt động.
- Biến thử nghiệm: `DRY_RUN=1` (in ra, không gửi), `NOW=YYYY-MM-DDTHH:MM` (giả lập thời gian), `FOOTER=0` (tắt phần kỳ thi cuối tin).
