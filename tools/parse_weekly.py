"""Parse KẾ HOẠCH THEO TUẦN (.docx) -> data/schedule.json (một lần mỗi năm học).
Đọc đúng cột bằng gridSpan/vMerge nên không bị lệch ô gộp. Giữ NGUYÊN mọi khối (K1-K4),
việc lọc theo K2 làm lúc chạy."""
import re, sys, json, datetime as dt
import docx
from docx.oxml.ns import qn

SLOTS = {"M1": ("07:00", "08:40"), "M2": ("08:40", "10:35"),
         "A1": ("13:00", "14:40"), "A2": ("14:40", "16:35")}
ORDER = ["M1", "M2", "A1", "A2"]
DATE_RE = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})")
KTAG = re.compile(r"\bK\s*([1-4](?:\s*[+&,]\s*K?\s*[1-4])*)", re.I)
KBARE = re.compile(r"(?<![\dhH:/])\b([1-4])\s*\+\s*([1-4])\b(?!\s*(?:LT|TH|T\b|tiết))")

def clean(s):
    return re.sub(r"[ \t\u00a0]+", " ", s).strip()

def ks_of(line):
    m = KTAG.search(line)
    if m:
        return sorted({int(x) for x in re.findall(r"[1-4]", m.group(1))})
    m = KBARE.search(line)
    if m:
        return sorted({int(m.group(1)), int(m.group(2))})
    return None

def cells_of(t):
    rows = []
    for ri, tr in enumerate(t._tbl.tr_lst):
        col, out, x = 0, [], 0
        for tc in tr.tc_lst:
            pr = tc.tcPr
            span = 1; vm = None; w = 0
            if pr is not None:
                tw = pr.find(qn("w:tcW"))
                if tw is not None and tw.get(qn("w:w")): w = int(tw.get(qn("w:w")))
                gs = pr.find(qn("w:gridSpan"))
                if gs is not None: span = int(gs.get(qn("w:val")))
                v = pr.find(qn("w:vMerge"))
                if v is not None: vm = v.get(qn("w:val")) or "continue"
            text = "\n".join(clean(p.text) for p in docx.table._Cell(tc, t).paragraphs)
            text = "\n".join(l for l in text.split("\n") if l.strip())
            out.append(dict(r=ri, c=col, span=span, vm=vm, text=text, x0=x, x1=x + w))
            col += span; x += w
        rows.append(out)
    return rows

def parse_table(t):
    rows = cells_of(t)
    # --- cột ngày từ hàng tiêu đề
    days = []
    for c in rows[0]:
        m = DATE_RE.search(c["text"])
        if m and "TH" in c["text"].upper():
            d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            days.append(dict(date=d, lo=c["c"], hi=c["c"] + c["span"], x0=c["x0"], x1=c["x1"]))
    if len(days) < 3: return None
    # --- rowspan của từng ô
    for ri, row in enumerate(rows):
        for c in row:
            c["rs"] = 1
            if c["vm"] == "restart":
                k = ri + 1
                while k < len(rows) and any(abs(x["x0"] - c["x0"]) < 30 and x["vm"] == "continue" for x in rows[k]):
                    c["rs"] += 1; k += 1
    # --- ranh giới slot từ nhãn giờ ở cột 1
    starts = {}
    for ri, row in enumerate(rows):
        for c in row:
            if c["c"] == 1 and re.search(r"\d\s*h\s*\d", c["text"]):
                t0 = re.findall(r"(\d{1,2})\s*h\s*(\d{2})", c["text"])[0]
                key = f"{int(t0[0]):02d}:{t0[1]}"
                for s, (a, _) in SLOTS.items():
                    if a == key: starts[s] = ri
    if set(starts) != set(ORDER):
        raise RuntimeError(f"nhãn giờ thiếu: {starts}")
    bounds = [(s, starts[s], (starts[ORDER[i + 1]] if i + 1 < 4 else len(rows)))
              for i, s in enumerate(ORDER)]
    def slots_of(r0, r1):
        return [s for s, a, b in bounds if r0 < b and r1 > a]
    items = {d["date"]: [] for d in days}
    for row in rows[1:]:
        for c in row:
            if c["c"] < 2 or not c["text"] or c["vm"] == "continue": continue
            sl = slots_of(c["r"], c["r"] + c["rs"])
            if not sl: continue
            lines = c["text"].split("\n")
            kidx = [i for i, l in enumerate(lines) if ks_of(l)]
            if len(kidx) >= 2:      # ô nhiều khối (vd thực hành lâm sàng)
                head = [l for i, l in enumerate(lines) if i not in kidx]
                parts = [(ks_of(lines[i]), head + [lines[i]]) for i in kidx]
            elif len(kidx) == 1:
                parts = [(ks_of(lines[kidx[0]]), lines)]
            else:   # không có thẻ K: thử "khối 3 / khối 4" trong ghi chú
                kh = sorted({int(x) for x in re.findall(r"kh[ốo]i\s*([1-4])", c["text"], re.I)})
                parts = [(kh or None, lines)]
            for d in days:
                ov = min(c["x1"], d["x1"]) - max(c["x0"], d["x0"])
                if ov > 0.5 * min(c["x1"] - c["x0"], d["x1"] - d["x0"]):
                    for ks, ls in parts:
                        items[d["date"]].append(dict(
                            start=SLOTS[sl[0]][0], end=SLOTS[sl[-1]][1],
                            k=ks, lines=ls))
    out = []
    for d in days:
        its = sorted(items[d["date"]], key=lambda x: (x["start"], x["end"]))
        out.append(dict(date=d["date"].isoformat(), items=its))
    return out

def main(src, dst):
    D = docx.Document(src)
    weeks = []
    for t in D.tables:
        r = parse_table(t)
        if r: weeks.append(dict(start=r[0]["date"], end=r[-1]["date"], days=r))
    # Vá dữ liệu: ô thi cuối kỳ TH "Ngoại khoa 2&3 đợt 1" chia theo Tổ, không ghi K;
    # file lịch thi ghi rõ là K3+4 (02-04/11/2026) -> gán K3+4 để K1/K2 không thấy nhầm.
    for w in weeks:
        for d in w["days"]:
            for it in d["items"]:
                if it["k"] is None and it["lines"][0].startswith("QUAY VỀ ATCS THI") \
                        and any("NGOẠI KHOA 2" in l for l in it["lines"]):
                    it["k"] = [3, 4]
    weeks.sort(key=lambda w: w["start"])
    for i, w in enumerate(weeks, 1): w["week"] = i
    json.dump(weeks, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("số tuần:", len(weeks), weeks[0]["start"], "->", weeks[-1]["end"])

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
