"""Goalies in-season: should recent starts count more than early ones when updating a goalie's start share?
Seasons 2015-16..2025-26. Prior = the production preseason share (glab2 ridge, out of sample). For every team-season
and checkpoint T (6, 8, 11, 15, 20, 25, 30, 41 team games), predict each goalie's share of the team's remaining starts.
  flat   (live.py before 2026-10-27): (K*prior + starts) / (K + T)
  decay  (now):                       (K*prior + sum d^k x_k) / (K + sum d^k), x_k = 1 if he started the game k games ago
Fit by weighted squared error (weight = games left); leave-one-season-out for the comparison.
Needs data/gl_all.pkl and data/team_all.pkl (assemble2.py) and fetches per-game goalie logs into data/raw/glogs/."""
import json, math, os, sys, time, collections, urllib.parse
import numpy as np, pandas as pd, requests
from scipy.optimize import minimize
sys.path.insert(0, "build")
import glab2 as G2
OUT = "data/raw/glogs"; os.makedirs(OUT, exist_ok=True)
SEASONS = [f"{y}{y+1}" for y in range(2015, 2026)]
CH = (6, 8, 11, 15, 20, 25, 30, 41)

def logs(s):
    fn = f"{OUT}/g_{s}.json"
    if not os.path.exists(fn):
        exp = urllib.parse.quote(f"seasonId={s} and gameTypeId=2")
        r = requests.get(f"https://api.nhle.com/stats/rest/en/goalie/summary?isAggregate=false&isGame=true&start=0&limit=-1&cayenneExp={exp}", timeout=120)
        r.raise_for_status(); json.dump(r.json()["data"], open(fn, "w")); time.sleep(2.5)
    d = json.load(open(fn))
    return d["data"] if isinstance(d, dict) else d

def samples():
    frames = {T: G2.frame(T) for T in range(2012, 2027)}
    res = G2.run(frames, list(range(2016, 2027)), "ridge", "ridge", 30)
    S = []
    for TT, d in res.items():
        s = f"{TT-1}{TT}"; rows = logs(s)
        games, teams_of = collections.defaultdict(dict), collections.defaultdict(set)
        for r in rows:
            t = r.get("teamAbbrev"); teams_of[r["playerId"]].add(t)
            if r["gamesStarted"]: games[t][r["gameId"]] = (r["gameDate"], r["playerId"])
        prior, team_T = d.share_p.to_dict(), d.team_T.to_dict()
        for t, g in games.items():
            order = [v for k, v in sorted(g.items(), key=lambda kv: (kv[1][0], kv[0]))]; L = len(order)
            gl = [x for x in set(o[1] for o in order) if len(teams_of[x]) == 1 and x in prior and team_T[x] == t]
            for T in CH:
                if L - T < 15: continue
                for x in gl:
                    seq = np.array([1 if order[k][1] == x else 0 for k in range(T)])
                    S.append((s, T, prior[x], seq, sum(1 for k in range(T, L) if order[k][1] == x) / (L - T), L - T))
    return S

def flat(sm, K): return (K * sm[2] + sm[3].sum()) / (K + sm[1])
def decay(sm, K, dd): w = dd ** np.arange(sm[1] - 1, -1, -1); return (K * sm[2] + (w * sm[3]).sum()) / (K + w.sum())
F = {"flat": (lambda sm, x: flat(sm, x[0]), [22]), "decay": (lambda sm, x: decay(sm, x[0], min(0.999, x[1])), [11, 0.9])}
def rmse(S, f): return math.sqrt(sum((f(x) - x[4]) ** 2 * x[5] for x in S) / sum(x[5] for x in S))
def fit(S, k):
    f, x0 = F[k]; r = minimize(lambda x: rmse(S, lambda sm: f(sm, np.abs(x))), x0, method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-8, maxiter=800))
    return np.abs(r.x)

if __name__ == "__main__":
    S = samples(); full = {k: fit(S, k) for k in F}
    cv = {k: [] for k in F}
    for s in SEASONS:
        tr = [x for x in S if x[0] != s]; te = [x for x in S if x[0] == s]
        for k in F:
            x = fit(tr, k); cv[k] += [(F[k][0](sm, x), sm) for sm in te]
    def m(rows): return math.sqrt(sum((p - sm[4]) ** 2 * sm[5] for p, sm in rows) / sum(sm[5] for p, sm in rows))
    out = {"n": len(S), "fit": {k: [round(float(v), 3) for v in full[k]] for k in F}, "loso_rmse": {k: round(m(v), 5) for k, v in cv.items()},
           "by_T": {T: {k: round(m([r for r in v if r[1][1] == T]), 4) for k, v in cv.items()} for T in CH}}
    print(json.dumps(out, indent=1)); json.dump(out, open("data/inseason_goalie_recency.json", "w"), indent=1)
