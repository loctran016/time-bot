"""Logic dùng chung: đọc dữ liệu, lọc theo khối (K), định dạng tin nhắn, gửi Telegram."""
import os, re, json, html, datetime as dt, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
USER_K = int(os.environ.get("USER_K", "2"))
KTAG = re.compile(r"\bK\s*([1-4](?:\s*[+&,]\s*K?\s*[1-4])*)", re.I)
KBARE = re.compile(r"(?<![\dhH:/])\b[1-4]\s*\+\s*[1-4]\b")
DOW_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
KIND_VI = {"midterm": "Giữa kỳ", "final": "Cuối kỳ", "qa": "Giải đáp"}
EXAM_WINDOW_DAYS = 30

def load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)

def now_vn():
    v = os.environ.get("NOW")  # để test: NOW=2026-11-15T07:00
    return dt.datetime.fromisoformat(v).replace(tzinfo=TZ) if v else dt.datetime.now(TZ)

esc = html.escape
def hm(t): return t.replace(":", "h")                      # 13:00 -> 13h00
def dmy(d): return d.strftime("%d/%m/%Y")
def dow(d): return DOW_VI[d.weekday()]
def k_ok(ks, k=None): return ks is None or (k or USER_K) in ks

# ---------- lịch học ----------
SEP = "━━━━━━━━━━━━━━━━━━"

def _title(line):
    t = re.sub(r"\s*\(.*?\)", "", line)
    t = KTAG.sub("", t); t = KBARE.sub("", t)
    t = re.sub(r"\bB\d+\b", "", t)
    return re.sub(r"\s+", " ", t).strip(" :-–")

def _ls_name(s):
    s = re.sub(r"(KHOA)\s*(\d)", r"\1 \2", s.strip(" :-–"), flags=re.I)
    s = re.sub(r"NGOẠ(?!I)", "NGOẠI", s)          # lỗi chính tả trong nguồn
    return s.lower().capitalize()

def render_item(it):
    L = it["lines"]
    first = L[0]
    if first.lower().startswith("tự học"):
        return dict(kind="selfstudy")
    loc = None
    for l in L:
        m = re.search(r"GĐ\s*:\s*(.+)$", l)
        if m: loc = m.group(1).strip()
    note = ""
    if first.lower().startswith("thực hành lâm sàng") and len(L) > 1:
        title = "LS " + _ls_name(_title(L[-1].split("(")[0]))
        tail = re.search(r"\((.*?)\)", L[-1])
        note = tail.group(1) if tail else ""
        details = ""
    else:
        title = _title(first)
        d = []
        for l in L[1:]:
            l = re.sub(r"(TBL\s*[–-]\s*)?GĐ\s*:.*$", "", l).strip()
            l = KTAG.sub("", l).strip(" -–")
            if l and not re.fullmatch(r"[\W\dK+]*", l): d.append(l.lstrip("- ").strip())
        details = ", ".join(d)
    return dict(kind="class", title=title, details=details, note=note, loc=loc,
                start=it["start"], end=it["end"])

def day_lines(day, k=None):
    rs = [render_item(i) for i in day["items"] if k_ok(i["k"], k)]
    cls = [r for r in rs if r["kind"] == "class"]
    cls.sort(key=lambda r: (r["start"], r["end"]))
    merged = []
    for r in cls:  # gộp các buổi liền nhau cùng bài (B3+B4 -> 13:00-16:35)
        p = merged[-1] if merged else None
        if p and (p["title"], p["details"], p["loc"]) == (r["title"], r["details"], r["loc"]) \
                and p["end"] == r["start"]:
            p["end"] = r["end"]
        else:
            merged.append(dict(r))
    return merged

def icon_of(title):
    t = title.lower()
    if t.startswith("ls "): return "🏥"
    if t.startswith("thi") or "thi kết thúc" in t or "thi giữa" in t: return "🚨"
    if t.startswith("nghỉ"): return "🏖"
    if t.startswith("giải đáp"): return "💬"
    return "📚"

def fmt_class(r):
    ic = icon_of(r["title"])
    time = r["start"] if (ic == "🚨" and r["end"] == "14:40") else f"{r['start']} - {r['end']}"
    if ic == "🚨":
        body = f"<b>{esc(r['title'])}</b>" + (f" <i>({esc(r['details'])})</i>" if r["details"] else "")
    else:
        body = f"<b>{esc(r['title'])}{':' if r['details'] else ''}</b>"
        if r["details"]: body += f" {esc(r['details'])}"
        if r["note"]: body += f" ({esc(r['note'])})"
    if r["loc"]: body += f" <i>(GĐ: {esc(r['loc'])})</i>"
    return f"{ic} <code>{time}</code> | {body}"

def format_week(week, k=None):
    s, e = dt.date.fromisoformat(week["start"]), dt.date.fromisoformat(week["end"])
    out = [f"📅 <b>LỊCH HỌC TUẦN {week['week']} ({s:%d/%m} – {e:%d/%m}) • K{k or USER_K}</b>", SEP]
    for day in week["days"]:
        d = dt.date.fromisoformat(day["date"])
        out.append(f"\n<b>{dow(d)} ({d:%d/%m})</b>")
        rows = day_lines(day, k)
        out += [fmt_class(r) for r in rows] if rows else ["📖 <i>Tự học</i>"]
    return "\n".join(out)

def week_of(d, weeks=None):
    """Tuần chứa ngày d. CN -> tuần sau; T7 không có trong tuần -> tuần của thứ 2 cùng tuần."""
    weeks = weeks or load("schedule.json")
    cands = [d + dt.timedelta(days=1)] if d.weekday() == 6 else [d, d - dt.timedelta(days=d.weekday())]
    for c in cands:
        for w in weeks:
            if dt.date.fromisoformat(w["start"]) <= c <= dt.date.fromisoformat(w["end"]): return w
    return None

def week_for_command(today):
    """Thứ 7/CN -> tuần sau; còn lại -> tuần này."""
    d = today + dt.timedelta(days=(7 - today.weekday())) if today.weekday() >= 5 else today
    return d, week_of(d)

# ---------- lịch thi ----------
def exam_name(e):
    n = KTAG.sub("", e["name"]); n = KBARE.sub("", n)
    return f"{KIND_VI[e['kind']]} {re.sub(r'[ ]+', ' ', n).strip(' -–')}"

def _dm(d, today):
    return f"{dow(d)}, {d:%d/%m}" + (f"/{d.year}" if d.year != today.year else "")

def fmt_exam(e, today, k=None):
    k = k or USER_K
    d = dt.date.fromisoformat(e["date"]); de = dt.date.fromisoformat(e["date_end"])
    t, room = e["time"], e["room"]
    m = re.search(r"K1\+2\s*\(([^)]+)\)\s*/?\s*K3\+4\s*\(([^)]+)\)", room)
    if m:
        t = m.group(1 if k in (1, 2) else 2).split("-")[0].strip().replace("h", ":").zfill(5)
        room = room.split("/")[-1].strip()
    left = (d - today).days
    if left < 0: badge = "🔥 <b>Đang diễn ra</b>"
    elif left == 0: badge = "💥 <b>HÔM NAY</b>"
    elif left == 1: badge = "🔥 <b>Ngày mai</b>"
    elif left <= 7: badge = f"🔥 <b>Còn {left} ngày</b>"
    else: badge = f"⏳ <b>Còn {left} ngày</b>"
    when = _dm(d, today) + (f" → {_dm(de, today)}" if de != d else "")
    parts = [when] + ([t] if t else []) + ([room] if room else [])
    return f"{badge} • {esc(exam_name(e))}\n└ <i>{esc(' • '.join(parts))}</i>"

def upcoming_exams(today, days=None, k=None):
    ex = load("exams.json")
    lim = today + dt.timedelta(days=days) if days else None
    out = []
    for e in ex:
        if not k_ok(e["k"], k): continue
        end = dt.date.fromisoformat(e["date_end"])
        if end < today: continue
        if lim and dt.date.fromisoformat(e["date"]) > lim: continue
        out.append(e)
    return out

def format_exams(today, days=None, k=None):
    ex = upcoming_exams(today, days, k)
    head = "📝 <b>LỊCH THI CÒN LẠI</b>" if not days else f"📝 <b>LỊCH THI {days} NGÀY TỚI</b>"
    if not ex: return f"{head}\n{SEP}\nKhông có kỳ thi nào 🎉"
    return f"{head}\n{SEP}\n" + "\n\n".join(fmt_exam(e, today, k) for e in ex)

def exam_footer(today):
    if os.environ.get("FOOTER", "1") != "1": return ""
    ex = upcoming_exams(today, EXAM_WINDOW_DAYS)
    if not ex: return f"\n\n{SEP}\n🎯 <b>Không có kỳ thi nào trong {EXAM_WINDOW_DAYS} ngày tới</b> 🎉"
    return (f"\n\n{SEP}\n🎯 <b>SẮP THI ({EXAM_WINDOW_DAYS} NGÀY TỚI)</b>\n"
            + "\n\n".join(fmt_exam(e, today) for e in ex))

# ---------- pretest ----------
def pt_dt(p, key="open"):
    d = dt.date.fromisoformat(p["date"]); h, m = map(int, p[key].split(":"))
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)

def fmt_pt(p):
    d = dt.date.fromisoformat(p["date"])
    rng = p["open"] + (f" – {p['close']}" if p["close"] else "")
    return f"🧪 <b>{esc(p['module'])}</b> – {esc(p['name'])}\n└ <i>{dow(d)}, {d:%d/%m} • mở {rng}</i>"

def format_pretest(now, n=6):
    up = [p for p in load("pretest.json") if pt_dt(p, "close" if p["close"] else "open") >= now]
    if not up: return f"🧪 <b>PRETEST</b>\n{SEP}\nKhông còn pretest nào sắp tới 🎉"
    return f"🧪 <b>PRETEST SẮP TỚI</b>\n{SEP}\n" + "\n\n".join(fmt_pt(p) for p in up[:n])

REMIND = [("1d", dt.timedelta(days=1), "NGÀY MAI", "📆", "Nhớ sắp xếp thời gian ôn nhé!"),
          ("1h", dt.timedelta(hours=1), "1 GIỜ NỮA", "⏰", "Ôn nhanh lại nào, còn kịp! 💪"),
          ("15m", dt.timedelta(minutes=15), "15 PHÚT NỮA", "🚨", "Mở máy, vào làm bài thôi! 🔥")]

def due_pretests(now, sent):
    """Trả về ([(key, tin)], [key bỏ qua]) cho các mốc đã đến hạn, chưa gửi, và pretest chưa mở."""
    out = []
    for p in load("pretest.json"):
        t0 = pt_dt(p)
        for tag, delta, label, ic, cheer in REMIND:
            key = f"{p['date']}|{p['open']}|{p['name']}|{tag}"
            if key in sent or now < t0 - delta or now >= t0: continue
            out.append((key, f"{ic} <b>PRETEST • {label}</b>\n{SEP}\n{fmt_pt(p)}\n\n{cheer}"))
    # chỉ giữ mốc gần nhất cho mỗi bài (nếu chạy trễ, tránh gửi dồn 3 tin)
    best = {}
    for key, msg in out:
        base, tag = key.rsplit("|", 1)
        order = {"1d": 0, "1h": 1, "15m": 2}[tag]
        if base not in best or order > best[base][0]: best[base] = (order, key, msg)
    keep = {v[1] for v in best.values()}
    skipped = [k for k, _ in out if k not in keep]
    return [(v[1], v[2]) for v in best.values()], skipped

# ---------- Telegram ----------
def _post(method, data=None, files=None):
    token = os.environ["TG_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        import uuid
        b = uuid.uuid4().hex; body = b""
        for k, v in (data or {}).items():
            body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (fn, blob) in files.items():
            body += (f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                     f'Content-Type: application/octet-stream\r\n\r\n').encode() + blob + b"\r\n"
        body += f"--{b}--\r\n".encode()
        req = urllib.request.Request(url, body, {"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(url, urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def send(text):
    chats = [c.strip() for c in os.environ.get("TG_CHAT_ID", "").split(",") if c.strip()]
    if os.environ.get("DRY_RUN") or not chats:
        print("----- (DRY RUN) -----\n" + text + "\n"); return
    for c in chats:
        for i in range(0, len(text), 4000):
            _post("sendMessage", dict(chat_id=c, text=text[i:i+4000], parse_mode="HTML",
                                      disable_web_page_preview="true"))

def send_photos(paths):
    chats = [c.strip() for c in os.environ.get("TG_CHAT_ID", "").split(",") if c.strip()]
    for p in paths:
        if os.environ.get("DRY_RUN") or not chats:
            print("(DRY RUN) gửi ảnh", p); continue
        for c in chats:
            with open(p, "rb") as f:
                _post("sendPhoto", dict(chat_id=c), files=dict(photo=(os.path.basename(p), f.read())))
