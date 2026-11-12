"""Playing time in-season: how fast should games played so far move the share of games a skater will play from here?
Seasons 2021-22..2025-26, checkpoints 21/35/49/70 days in. For every skater with an NHL row last season or games this
season: prior a0 = share of the schedule played over the last three seasons (weights 1 / 0.5 / 0.25), shrunk 0.3 seasons
toward 0.80 (the build's availability rule, approximated); target = share of his team's remaining games he played.
Only players who played in the last 10 days before the checkpoint are fitted (the injury report covers the rest).
  share = (K*a0 + games played) / (K + team games), K = K_up if he's played more than expected, else K_down,
  and never raised past `cap` unless a0 was already higher.
Result (weighted RMSE on the remaining share): prior only 0.2557; one K (11.2, cap 0.887) 0.2125; two speeds
(K_up 6.5, K_down 30.7, cap 0.846) 0.2090. Leave-one-season-out, every season: 0.250-0.265 -> 0.202-0.218.
Needs data/raw/glogs/g_<season>.json (per-game goalie logs, fetched by inseason_goalie_recency.py) for team game counts.
Writes data/inseason_games.json; live.py uses the numbers as KA."""
import collections, datetime as dt, json, math, os, time, urllib.parse
import numpy as np, requests
from scipy.optimize import minimize
RAW = "data/raw/games"; os.makedirs(RAW, exist_ok=True)
SLEN = {2019: 70, 2020: 56}
START = {2021: "2021-10-12", 2022: "2022-10-07", 2023: "2023-10-10", 2024: "2024-10-08", 2025: "2025-10-07"}
DAYS = (21, 35, 49, 70)

def pull(fn, exp, agg):
    fn = f"{RAW}/{fn}"
    if not os.path.exists(fn):
        url = f"https://api.nhle.com/stats/rest/en/skater/summary?isAggregate={'true' if agg else 'false'}&isGame=false&start=0&limit=-1&cayenneExp=" + urllib.parse.quote(exp)
        r = requests.get(url, timeout=120); r.raise_for_status()
        json.dump([{k: x.get(k) for k in ("playerId", "gamesPlayed", "teamAbbrevs")} for x in r.json()["data"]], open(fn, "w")); time.sleep(2.5)
    return json.load(open(fn))

def team_games(y, date):
    g = collections.defaultdict(set)
    d = json.load(open(f"data/raw/glogs/g_{y}{y+1}.json")); d = d["data"] if isinstance(d, dict) else d
    for r in d:
        if r["gameDate"] <= date: g[r["teamAbbrev"]].add(r["gameId"])
    return {t: len(v) for t, v in g.items()}

def samples():
    tot = {y: {r["playerId"]: r for r in pull(f"tot_{y}{y+1}.json", f"seasonId={y}{y+1} and gameTypeId=2", False)} for y in range(2018, 2026)}
    S = []
    for y, d0 in START.items():
        for days in DAYS:
            hi = dt.date.fromisoformat(d0) + dt.timedelta(days=days); lo = hi - dt.timedelta(days=9)
            to = {r["playerId"]: r["gamesPlayed"] for r in pull(f"to_{y}{y+1}_{days}.json", f'seasonId={y}{y+1} and gameTypeId=2 and gameDate<="{hi}"', True)}
            act = {r["playerId"] for r in pull(f"last10_{y}{y+1}_{days}.json", f'seasonId={y}{y+1} and gameTypeId=2 and gameDate>="{lo}" and gameDate<="{hi}"', True)}
            tg = team_games(y, hi.isoformat())
            for pid in set(tot[y - 1]) | set(to):
                num = den = 0.0
                for k, w in ((1, 1.0), (2, 0.5), (3, 0.25)):
                    r = tot.get(y - k, {}).get(pid)
                    if r: num += w * min(1.0, r["gamesPlayed"] / SLEN.get(y - k, 82)); den += w
                if not den or pid not in act: continue
                cur = tot[y].get(pid)
                t = tg.get(((cur or tot[y - 1][pid]).get("teamAbbrevs") or "").split(",")[0])
                if not t or t >= 80: continue
                gp = min(to.get(pid, 0), t)
                S.append(dict(y=y, a0=(num + 0.24) / (den + 0.3), t=t, gp=gp, w=82 - t, rest=min(1.0, max(0, (cur["gamesPlayed"] if cur else 0) - gp) / (82 - t))))
    return S

def model(s, x):
    k = x[0] if s["gp"] / s["t"] >= s["a0"] else x[1]
    return min((k * s["a0"] + s["gp"]) / (k + s["t"]), max(x[2], s["a0"]))
def rmse(L, f): return math.sqrt(sum((f(s) - s["rest"]) ** 2 * s["w"] for s in L) / sum(s["w"] for s in L))
def fit(L): return np.abs(minimize(lambda x: rmse(L, lambda s: model(s, np.abs(x))), [11, 11, 0.89], method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-8)).x)

if __name__ == "__main__":
    S = samples(); x = fit(S)
    out = {"n": len(S), "k_up": round(float(x[0]), 1), "k_down": round(float(x[1]), 1), "cap": round(float(x[2]), 3),
           "rmse_prior": round(rmse(S, lambda s: s["a0"]), 4), "rmse": round(rmse(S, lambda s: model(s, x)), 4), "loso": {}}
    for y in START:
        xx = fit([s for s in S if s["y"] != y]); te = [s for s in S if s["y"] == y]
        out["loso"][y] = [round(rmse(te, lambda s: s["a0"]), 4), round(rmse(te, lambda s: model(s, xx)), 4)]
    print(json.dumps(out, indent=1)); json.dump(out, open("data/inseason_games.json", "w"), indent=1)
