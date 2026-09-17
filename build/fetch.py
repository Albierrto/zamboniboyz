import json, time, urllib.parse, requests, os, sys
S = requests.Session()
BASE = "https://api.nhle.com/stats/rest/en"
REPORTS = {
  "skater": ["summary", "realtime", "faceoffwins", "powerplay", "bios", "timeonice"],
  "goalie": ["summary", "bios"],
}
SEASONS = ["20212022", "20222023", "20232024", "20242025", "20252026"]
out = "data/raw/nhl"; os.makedirs(out, exist_ok=True)

def pull(kind, rep, season):
    fn = f"{out}/{kind}_{rep}_{season}.json"
    if os.path.exists(fn): return
    rows, start = [], 0
    sort = urllib.parse.quote(json.dumps([{"property": "playerId", "direction": "ASC"}]))
    while True:
        exp = urllib.parse.quote(f"seasonId={season} and gameTypeId=2")
        url = f"{BASE}/{kind}/{rep}?isAggregate=false&isGame=false&sort={sort}&start={start}&limit=100&cayenneExp={exp}"
        url = url.replace("limit=100", "limit=-1")
        for a in range(8):
            r = S.get(url, timeout=90)
            if r.status_code == 429:
                time.sleep(15 * (a + 1)); continue
            r.raise_for_status(); break
        j = r.json()
        rows += j["data"]
        break
    json.dump(rows, open(fn, "w"))
    print(kind, rep, season, len(rows), flush=True); time.sleep(2)

for season in SEASONS:
    for kind, reps in REPORTS.items():
        for rep in reps:
            pull(kind, rep, season)

