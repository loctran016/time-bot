"""Parse LICH_THI_Y3 (.xlsx, đã chuyển từ .xls) -> data/exams.json + data/pretest.json.
Dùng sheet THEO TÊN ('Lịch thi Y24', 'Lịch pretest'), không theo vị trí.
Tự kiểm tra thứ-ngày để bắt lỗi đánh máy năm/ngày trong nguồn."""
import re, sys, json, datetime as dt
import openpyxl

DOW = {"T2": 0, "T3": 1, "T4": 2, "T5": 3, "T6": 4, "T7": 5, "CN": 6, "CHỦ NHẬT": 6}
KTAG = re.compile(r"\bK\s*([1-4](?:\s*[+&,]\s*K?\s*[1-4])*)", re.I)

def sheet_filled(ws):
    """Điền giá trị ô gộp vào mọi ô trong vùng gộp."""
    g = {}
    for row in ws.iter_rows():
        for c in row: g[(c.row, c.column)] = c.value
    for mr in ws.merged_cells.ranges:
        v = g[(mr.min_row, mr.min_col)]
        for r in range(mr.min_row, mr.max_row + 1):
            for c in range(mr.min_col, mr.max_col + 1): g[(r, c)] = v
    rows = []
    for r in range(1, ws.max_row + 1):
        rows.append([g.get((r, c)) for c in range(1, ws.max_column + 1)])
    return rows

def s(v): return re.sub(r"\s+", " ", str(v)).strip() if v not in (None, "") else ""

def dow_of(x):
    x = s(x).upper().replace("Ủ", "Ủ")
    return DOW.get(x)

def parse_dates(v, guess_year=None):
    """datetime -> [d]; 'dd/mm/yyyy - dd/mm/yyyy' -> [d1, d2]."""
    if isinstance(v, (dt.datetime, dt.date)):
        return [v.date() if isinstance(v, dt.datetime) else v]
    out = []
    for m in re.finditer(r"(\d{1,2})/(\d{1,2})/(\d{4})", s(v)):
        out.append(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
    return out

def times(v):
    ts = [f"{int(h):02d}:{m}" for h, m in re.findall(r"(\d{1,2})\s*h\s*(\d{2})", s(v))]
    return ts

def ks(name):
    m = KTAG.search(name)
    return sorted({int(x) for x in re.findall(r"[1-4]", m.group(1))}) if m else None

def fix_year(dates, dows, notes, label):
    """Nếu thứ không khớp ngày -> thử năm +1 (lỗi 2026 thay vì 2027)."""
    if not dates or dows is None: return dates
    first = dates[0]
    ok = (first.weekday() == dows[0]) if isinstance(dows, list) else (first.weekday() == dows)
    if ok: return dates
    for dy in (1, -1):
        try: alt = [d.replace(year=d.year + dy) for d in dates]
        except ValueError: continue
        if alt[0].weekday() == (dows[0] if isinstance(dows, list) else dows):
            notes.append(f"SỬA NĂM {label}: {dates[0]} -> {alt[0]} (thứ không khớp)")
            return alt
    notes.append(f"CẢNH BÁO thứ-ngày không khớp, giữ nguyên: {label} {dates[0]} thứ {dows}")
    return dates

def parse_exams(ws, notes):
    rows = sheet_filled(ws)
    section = None; out = []
    names = {"GIỮA KỲ": "midterm", "GIẢI ĐÁP": "qa", "CUỐI KỲ": "final"}
    for r in rows:
        cells = [s(x) for x in r if s(x)]
        if not cells: continue
        txt = " ".join(cells).upper()
        for key, sec in names.items():
            if "LỊCH" in txt and key in txt and len(set(cells)) <= 3 and "KHỐI" not in txt:
                section = sec
        if section and re.fullmatch(r"\d+", cells[0]) and len(cells) >= 5:
            tt, name, thu, ngay, gio = cells[0], cells[1], cells[2], None, None
            # lấy lại giá trị gốc (ngày có thể là datetime)
            raw = [x for x in r if s(x)]
            ngay, gio = raw[3], raw[4]
            room = s(raw[5]) if len(raw) > 5 else ""
            dow = [DOW[p.strip().upper()] for p in re.split(r"->|→|-", thu) if p.strip().upper() in DOW]
            dates = parse_dates(ngay)
            dates = fix_year(dates, dow, notes, name)
            if len(dates) == 2 and dow and len(dow) == 2 and dates[1].weekday() != dow[1]:
                notes.append(f"CẢNH BÁO ngày kết thúc lệch thứ: {name} {dates}")
            t = times(gio)
            out.append(dict(kind=section, name=s(name).replace("Hệ Hệ", "Hệ"), k=ks(s(name)),
                            date=dates[0].isoformat(), date_end=dates[-1].isoformat(),
                            time=t[0] if t else None, time_raw=s(gio), room=room))
    return sorted(out, key=lambda e: (e["date"], e["time"] or ""))

def parse_pretest(ws, notes):
    rows = sheet_filled(ws)
    out = []; hdr = False
    for r in rows:
        cells = [s(x) for x in r[:8]]
        if cells[:3] and cells[1].upper().startswith("MODULE"):
            hdr = True; continue
        if not hdr: continue
        module, bai, thu = cells[1], cells[2], cells[3]
        d = r[4]; gio = cells[5]
        if not (module and bai and thu and gio): continue
        if not isinstance(d, (dt.datetime, dt.date)):
            continue
        d = d.date() if isinstance(d, dt.datetime) else d
        dw = dow_of(thu)
        if dw is None: continue
        fixed = fix_year([d], dw, notes, bai)[0]
        t = times(gio)
        if not t: continue
        out.append(dict(module=module.replace(" ,", ",").replace("\n", " "), name=bai,
                        dow=thu, date=fixed.isoformat(), open=t[0],
                        close=t[1] if len(t) > 1 else None, time_raw=gio))
    return sorted(out, key=lambda e: (e["date"], e["open"]))

if __name__ == "__main__":
    src, outdir = sys.argv[1], sys.argv[2]
    wb = openpyxl.load_workbook(src, data_only=True)
    notes = []
    ex = parse_exams(wb["Lịch thi Y24"], notes)
    pt = parse_pretest(wb["Lịch pretest"], notes)
    json.dump(ex, open(f"{outdir}/exams.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(pt, open(f"{outdir}/pretest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("exams:", len(ex), "pretest:", len(pt))
    for n in notes: print(n)
