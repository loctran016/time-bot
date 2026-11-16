"""Kiểm tra dữ liệu sau khi parse: tuần liên tục, không chồng giờ học trong cùng một khối K."""
import json, datetime as dt, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = json.load(open(f"{R}/data/schedule.json", encoding="utf-8"))
prev = None
for w in W:
    s = dt.date.fromisoformat(w["start"])
    if s.weekday() != 0: print("! tuần", w["week"], "không bắt đầu thứ 2")
    if prev and (s - prev).days != 7: print("i khoảng nghỉ", (s - prev).days, "ngày trước tuần", w["week"])
    prev = s
bad = 0
for k in (1, 2, 3, 4):
    for w in W:
        for d in w["days"]:
            its = [i for i in d["items"] if (i["k"] is None or k in i["k"]) and not i["lines"][0].lower().startswith("tự học")]
            for a in range(len(its)):
                for b in range(a + 1, len(its)):
                    A, B = its[a], its[b]
                    if A["start"] < B["end"] and B["start"] < A["end"]:
                        bad += 1; print(f"! K{k} tuần {w['week']} {d['date']}: {A['lines'][0][:30]} | {B['lines'][0][:30]}")
print("OK" if not bad else f"{bad} chồng giờ cần xem tay (có thể do nguồn)")
