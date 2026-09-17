"""Pull 2010-11 .. 2025-26 NHL season stats (more history for testing)."""
import json, time, urllib.parse, requests, os, sys
S = requests.Session()
BASE = "https://api.nhle.com/stats/rest/en"
REPORTS = {"skater": ["summary", "realtime", "faceoffwins", "timeonice", "bios", "goalsForAgainst", "scoringpergame", "percentages"],
           "goalie": ["summary", "bios"]}
SEASONS = [f"{y}{y+1}" for y in range(2010, 2026)]
out = "data/raw/nhl"; os.makedirs(out, exist_ok=True)
def pull(kind, rep, season):
    fn = f"{out}/{kind}_{rep}_{season}.json"
    if os.path.exists(fn): return
    exp = urllib.parse.quote(f"seasonId={season} and gameTypeId=2")
    sort = urllib.parse.quote(json.dumps([{"property": "playerId", "direction": "ASC"}]))
    url = f"{BASE}/{kind}/{rep}?isAggregate=false&isGame=false&sort={sort}&start=0&limit=-1&cayenneExp={exp}"
    for a in range(10):
        try:
            r = S.get(url, timeout=120)
        except Exception as e:
            time.sleep(10); continue
        if r.status_code == 429: time.sleep(20 * (a + 1)); continue
        r.raise_for_status(); break
    rows = r.json()["data"]
    json.dump(rows, open(fn, "w")); print(kind, rep, season, len(rows), flush=True); time.sleep(2.5)
for season in SEASONS[::-1]:
    for kind, reps in REPORTS.items():
        for rep in reps:
            try: pull(kind, rep, season)
            except Exception as e: print("FAIL", kind, rep, season, e, flush=True)
print("DONE", flush=True)
