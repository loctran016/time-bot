"""Điểm vào duy nhất. Dùng: python scripts/notify.py <cmd> [YYYY-MM-DD]
cmd: weekly | lich-hoc | lich-thi | pretest | tick | khdt
  weekly   : lịch tuần SAU (chạy sáng Chủ nhật)
  lich-hoc : lịch tuần này (T2-T6) hoặc tuần sau (T7/CN), hoặc tuần chứa ngày chỉ định
  lich-thi : in TẤT CẢ kỳ thi còn lại
  pretest  : các pretest sắp tới
  tick     : kiểm tra & gửi nhắc pretest 1 ngày/1 giờ/15 phút (chạy mỗi 5-15 phút)
  khdt     : gửi ảnh Kế hoạch đào tạo"""
import os, sys, json, glob, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

SENT = os.path.join(lib.ROOT, "data", "sent.json")

def week_msg(day, now):
    w = lib.week_of(day)
    if not w:
        return f"📅 Không có lịch học trong tuần chứa ngày {day:%d/%m/%Y} (nghỉ lễ/Tết/hè)."
    return lib.format_week(w)

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    now = lib.now_vn(); today = now.date()
    if cmd == "weekly":
        nxt = today + dt.timedelta(days=7 - today.weekday())       # thứ 2 tuần sau
        lib.send(week_msg(nxt, now) + lib.exam_footer(today))
    elif cmd == "lich-hoc":
        if len(sys.argv) > 2: day = dt.date.fromisoformat(sys.argv[2])
        else: day, _ = lib.week_for_command(today)
        lib.send(week_msg(day, now) + lib.exam_footer(today))
    elif cmd == "lich-thi":
        lib.send(lib.format_exams(today))                            # tất cả kỳ thi còn lại
    elif cmd == "pretest":
        lib.send(lib.format_pretest(now) + lib.exam_footer(today))
    elif cmd == "tick":
        sent = json.load(open(SENT)) if os.path.exists(SENT) else {}
        due, skipped = lib.due_pretests(now, sent)
        for key, msg in due:
            lib.send(msg + lib.exam_footer(today)); sent[key] = now.isoformat()
        for key in skipped: sent[key] = "skipped"
        if due or skipped:
            json.dump(sent, open(SENT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"tick {now:%Y-%m-%d %H:%M}: gửi {len(due)} nhắc")
    elif cmd == "khdt":
        lib.send("🗂 <b>Kế hoạch đào tạo năm thứ 3 – Y2024 (2026-2027)</b>")
        lib.send_photos(sorted(glob.glob(os.path.join(lib.ROOT, "assets", "khdt-*.png"))))
    else:
        sys.exit(__doc__)

if __name__ == "__main__":
    main()
