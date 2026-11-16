"""Logic dùng chung: đọc dữ liệu, lọc theo khối (K), định dạng tin nhắn, gửi Telegram."""
import os, re, json, html, datetime as dt, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
USER_K = int(os.environ.get("USER_K", "2"))
KTAG = re.compile(r"\bK\s*([1-4](?:\s*[+&,]\s*K?\s*[1-4])*)", re.I)
KBARE = re.compile(r"(?<![\dhH:/])\b[1-4]\s*\+\s*[1-4]\b")
DOW_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
KIND_VI = {"midterm": "Giữa kỳ", "final": "Cuối kỳ", "qa": "Giải đáp thắc mắc"}
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
def _title(line):
    t = re.sub(r"\s*\(.*?\)", "", line)
    t = KTAG.sub("", t); t = KBARE.sub("", t)
    t = re.sub(r"\bB\d+\b", "", t)
    return re.sub(r"\s+", " ", t).strip(" :-–")

def render_item(it):
    L = it["lines"]
    first = L[0]
    if first.lower().startswith("tự học"):
        return dict(kind="selfstudy")
    loc = None
    for l in L:
        m = re.search(r"GĐ\s*:\s*(.+)$", l)
        if m: loc = m.group(1).strip()
    if first.lower().startswith("thực hành lâm sàng") and len(L) > 1:
        sub = _title(L[-1].split("(")[0]) or ""
        tail = re.search(r"\((.*?)\)", L[-1])
        title = f"{first}: {sub}" + (f" ({tail.group(1)})" if tail else "")
        details = ""
    else:
        title = _title(first)
        d = []
        for l in L[1:]:
            l = re.sub(r"(TBL\s*[–-]\s*)?GĐ\s*:.*$", "", l).strip()
            l = KTAG.sub("", l).strip(" -–")
            if l and not re.fullmatch(r"[\W\d+K]*", l): d.append(l.lstrip("- ").strip())
        details = ", ".join(d)
    return dict(kind="class", title=title, details=details, loc=loc,
                start=it["start"], end=it["end"])

def day_lines(day, k=None):
    rs = [render_item(i) for i in day["items"] if k_ok(i["k"], k)]
    cls = [r for r in rs if r["kind"] == "class"]
    cls.sort(key=lambda r: (r["start"], r["end"]))
    merged = []
    for r in cls:  # gộp các buổi liền nhau cùng bài (B3+B4 -> 13h00-16h35)
        p = merged[-1] if merged else None
        if p and (p["title"], p["details"], p["loc"]) == (r["title"], r["details"], r["loc"]) \
                and p["end"] == r["start"]:
            p["end"] = r["end"]
        else:
            merged.append(dict(r))
    return merged

def fmt_class(r):
    s = f"<b>{esc(r['title'])}</b>"
    if r["details"]: s += f": {esc(r['details'])}"
    if r["loc"]: s += f" (GĐ: {esc(r['loc'])})"
    return f"• {s} từ {hm(r['start'])} đến {hm(r['end'])}"

def format_week(week, k=None):
    s, e = dt.date.fromisoformat(week["start"]), dt.date.fromisoformat(week["end"])
    out = [f"📅 <b>Lịch học tuần {week['week']}</b> ({s:%d/%m/%Y} – {e:%d/%m/%Y}) · K{k or USER_K}"]
    for day in week["days"]:
        d = dt.date.fromisoformat(day["date"])
        rows = day_lines(day, k)
        if not rows:
            out.append(f"\n<b>{dow(d)} ({d:%d/%m})</b>: tự học")
        else:
            out.append(f"\n<b>{dow(d)} ({d:%d/%m})</b>")
            out += [fmt_class(r) for r in rows]
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
def fmt_exam(e, today, k=None):
    k = k or USER_K
    d = dt.date.fromisoformat(e["date"]); de = dt.date.fromisoformat(e["date_end"])
    when = f"{dow(d)} {d:%d/%m/%Y}" + (f" → {dow(de)} {de:%d/%m/%Y}" if de != d else "")
    t = e["time"]
    room = e["room"]
    m = re.search(r"K1\+2\s*\(([^)]+)\)\s*/?\s*K3\+4\s*\(([^)]+)\)", room)
    if m:
        t = m.group(1 if k in (1, 2) else 2).split("-")[0].strip().replace("h", ":").zfill(5)
        room = room.split("/")[-1].strip()
    left = (d - today).days
    near = "hôm nay" if left == 0 else f"còn {left} ngày"
    return (f"• <b>{KIND_VI[e['kind']]}</b> · {esc(e['name'])}\n"
            f"   {when}" + (f" · {hm(t)}" if t else "") +
            (f" · {esc(room)}" if room else "") + f" ({near})")

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
    head = f"📝 <b>Lịch thi{' trong ' + str(days) + ' ngày tới' if days else ' còn lại'}</b>"
    if not ex: return head + "\nKhông có kỳ thi nào."
    return head + "\n" + "\n".join(fmt_exam(e, today, k) for e in ex)

def exam_footer(today):
    if os.environ.get("FOOTER", "1") != "1": return ""
    ex = upcoming_exams(today, EXAM_WINDOW_DAYS)
    if not ex: return f"\n\n📝 Thi trong {EXAM_WINDOW_DAYS} ngày tới: không có."
    return f"\n\n📝 <b>Thi trong {EXAM_WINDOW_DAYS} ngày tới</b>\n" + \
        "\n".join(fmt_exam(e, today) for e in ex)

# ---------- pretest ----------
def pt_dt(p, key="open"):
    d = dt.date.fromisoformat(p["date"]); h, m = map(int, p[key].split(":"))
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)

def fmt_pt(p, now=None):
    d = dt.date.fromisoformat(p["date"])
    dn = "Chủ nhật" if d.weekday() == 6 else f"Thứ {d.weekday() + 2}"
    rng = hm(p["open"]) + (f"–{hm(p['close'])}" if p["close"] else "")
    return f"<b>{esc(p['module'])}</b> – {esc(p['name'])}\n   {dn} · {d:%d/%m/%Y} · mở {rng}"

def format_pretest(now, n=6):
    up = [p for p in load("pretest.json") if pt_dt(p, "close" if p["close"] else "open") >= now]
    if not up: return "🧪 <b>Pretest</b>\nKhông còn pretest nào sắp tới."
    return "🧪 <b>Pretest sắp tới</b>\n" + "\n".join("• " + fmt_pt(p) for p in up[:n])

REMIND = [("1d", dt.timedelta(days=1), "ngày mai"), ("1h", dt.timedelta(hours=1), "1 giờ nữa"),
          ("15m", dt.timedelta(minutes=15), "15 phút nữa")]

def due_pretests(now, sent):
    """Trả về [(key, tin)] cho các mốc đã đến hạn, chưa gửi, và pretest chưa mở."""
    out = []
    for p in load("pretest.json"):
        t0 = pt_dt(p)
        for tag, delta, label in REMIND:
            key = f"{p['date']}|{p['open']}|{p['name']}|{tag}"
            if key in sent or now < t0 - delta or now >= t0: continue
            out.append((key, f"⏰ <b>Pretest {label}</b>\n• " + fmt_pt(p)))
    # chỉ giữ mốc gần nhất cho mỗi bài (nếu chạy trễ, tránh gửi dồn 3 tin)
    best = {}
    for key, msg in out:
        base = key.rsplit("|", 1)[0]
        order = {"1d": 0, "1h": 1, "15m": 2}[key.rsplit("|", 1)[1]]
        if base not in best or order > best[base][0]: best[base] = (order, key, msg)
    skipped = [k for k, _ in out if k not in {v[1] for v in best.values()}]
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
