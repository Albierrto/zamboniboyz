"""Early-season vs rest-of-season splits for past seasons, to tune in-season updating."""
import json, os, subprocess, time, urllib.parse, datetime as dt
OUT = "data/raw/splits"
SEASONS = {2022: "2021-10-12", 2023: "2022-10-07", 2024: "2023-10-10", 2025: "2024-10-04", 2026: "2025-10-07"}
CHECK = [14, 28, 42, 70]
REPORTS = [("skater", "summary"), ("skater", "realtime"), ("skater", "faceoffwins"), ("skater", "timeonice"), ("goalie", "summary")]
def get(kind, report, sid, d0, d1):
    exp = f'gameTypeId=2 and seasonId<={sid} and seasonId>={sid} and gameDate<="{d1}" and gameDate>="{d0}"'
    url = f"https://api.nhle.com/stats/rest/en/{kind}/{report}?isAggregate=true&isGame=false&limit=-1&start=0&cayenneExp={urllib.parse.quote(exp)}"
    for a in range(6):
        r = subprocess.run(["curl", "-sS", "-m", "90", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if "data" in d: return d["data"]
        except Exception:
            pass
        time.sleep(10 * (a + 1))
    raise RuntimeError(url)
for T, start in SEASONS.items():
    sid = f"{T-1}{T}"
    s0 = dt.date.fromisoformat(start)
    for c in CHECK:
        mid = s0 + dt.timedelta(days=c - 1)
        for win, (d0, d1) in {"to": (start, mid.isoformat()), "rest": ((mid + dt.timedelta(days=1)).isoformat(), f"{T}-06-30")}.items():
            for kind, rep in REPORTS:
                fn = f"{OUT}/{T}_{c}_{win}_{kind}_{rep}.json"
                if os.path.exists(fn): continue
                data = get(kind, rep, sid, d0, d1)
                json.dump(data, open(fn, "w"))
                print(fn, len(data), flush=True)
                time.sleep(2.5)
print("done")
