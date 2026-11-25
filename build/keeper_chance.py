"""Keeper chance (2026-11-25): who becomes keeper-level next season, and how early can you tell?

Bort: "I would like the website to really prioritize players that could become keepers ... It hit on a few but seems
to notify way too late."

1. fetch: NHL stats (summary, realtime, faceoffwins, timeonice, bios) for full regular seasons 2013-14..2025-26 and
   early cuts at opener+23 days (~10 team games) and opener+50 days (~22) for 2016-17..2025-26 -> lab/raw/.
2. frame: for each season T (2016-17..2024-25) and skater: three prior seasons, the two early cuts, season T, and the
   truth, season T+1. League scoring at his NHL position (C, W for L/R, D). Waiver level per season = the value of
   the player at the rank that gives the site's 2026-27 waiver level in 2025-26 (C 57th, W 74th, D 94th).
   Keeper-level next season = top 80 skaters by next season's points above waiver level (12 teams x 6 skaters,
   plus flex picks). A preseason projection is rebuilt from the prior seasons (per-game rates weighted 5/3/2 by
   games, 20 games of a fringe-level player mixed in, the site's age curve, games share since his debut).
3. test: players below that line both before the season and the season before (about 500 a season, 24 of whom
   become keeper-level next season). Leave-one-season-out logistic regression on: next season's value now
   (preseason projection x the site's in-season update) and before the season, each vs the line; per-game scoring
   vs projection, shrunk n/(n+10); the site's ice-time and power-play changes; age; under 24; new to the NHL (<30
   games in 3 seasons) and its interactions with scoring; share of team games played; position; log draft pick.

Results (out of sample, nine seasons):
                         ~10 games: AUC  top-20 caught   ~22 games: AUC  top-20 caught
  preseason projection          0.723   21%                     0.737   20%
  hot start (pts a game)        0.731   16%                     0.803   23%
  site's next-season value      0.754   24%                     0.781   24%
  keeper chance                 0.829   27%                     0.855   29%
  Flag at 25%+: ~16 a season at 10 games (34% became keeper-level), ~18 at 22 games (37%); base rate 4.7%.
The coefficients printed at the end go into FKM in docs/app.js (g10 = ~10 games, g22 = ~22 games).
Run: python3 build/keeper_chance.py fetch|frame|fit   (needs pandas, scikit-learn; writes to ./lab)."""
import json, os, sys, time, urllib.parse, urllib.request, datetime as dt
LAB = os.environ.get("KC_LAB", "lab"); RAW = os.path.join(LAB, "raw")
OPEN = {2013: "2013-10-01", 2014: "2014-10-08", 2015: "2015-10-07", 2016: "2016-10-12", 2017: "2017-10-04", 2018: "2018-10-03",
        2019: "2019-10-02", 2020: "2021-01-13", 2021: "2021-10-12", 2022: "2022-10-07", 2023: "2023-10-10", 2024: "2024-10-04", 2025: "2025-10-07"}
REPORTS = ["summary", "realtime", "faceoffwins", "timeonice"]
SK = {"C": dict(g=3.0, a=2.0, fow=0.25), "W": dict(g=3.5, a=2.5, fow=0.0), "D": dict(g=4.0, a=4.0, fow=0.25)}
CATS = ["g", "a", "pm", "pim", "hit", "blk", "fow"]
TG = {y: 82 for y in range(2013, 2027)}; TG[2019] = 70; TG[2020] = 56
AGEC = [-0.0012091503372653012, 0.04755596460617058, 0.5774994168045451]  # META.keeperAge.coef
SITE_REPL = {"C": 272.1, "W": 180.1, "D": 158.7}
KS = {"g": 81.5, "a": 69.7, "pm": 105.8, "pim": 133.5, "hit": 17.5, "blk": 34.7, "fow": 8.2}  # build/live.py K
TOPN = 80

def get(url):
    for i in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "zamboniboyz-research/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 + 3 * i)
    raise RuntimeError("failed " + url)

def stats(path, exp, flags="isAggregate=true&isGame=false"):
    rows, seen, start = [], set(), 0
    srt = urllib.parse.quote(json.dumps([{"property": "playerId", "direction": "ASC"}]))
    while True:
        d = get(f"https://api.nhle.com/stats/rest/en/{path}?{flags}&sort={srt}&limit=100&start={start}&cayenneExp={urllib.parse.quote(exp)}")
        page, total = d.get("data", []), d.get("total") or 0
        for r in page:
            if r["playerId"] not in seen:
                seen.add(r["playerId"]); rows.append(r)
        start += 100; time.sleep(0.4)
        if not page or start >= total:
            break
    if total and len(rows) < total:
        raise RuntimeError(f"{path}: {len(rows)} of {total}")
    return rows

def fetch():
    os.makedirs(RAW, exist_ok=True)
    jobs = [(y, "full", r) for y in range(2013, 2026) for r in REPORTS + ["bios"]]
    jobs += [(y, t, r) for y in range(2016, 2026) for t in ("d23", "d50") for r in REPORTS]
    for y, tag, rep in jobs:
        f = f"{RAW}/{y}_{tag}_{rep}.json"
        if os.path.exists(f):
            continue
        sid = f"{y}{y + 1}"; exp = f"seasonId={sid} and gameTypeId=2"
        if tag != "full":
            exp += f' and gameDate<="{(dt.date.fromisoformat(OPEN[y]) + dt.timedelta(days=int(tag[1:]))).isoformat()} 23:59:59"'
        rows = stats("skater/bios", exp, "isAggregate=false&isGame=false") if rep == "bios" else stats(f"skater/{rep}", exp)
        json.dump(rows, open(f, "w")); print(f)

def frame():
    import numpy as np, pandas as pd
    def load(y, tag):
        rd = lambda r: pd.DataFrame(json.load(open(f"{RAW}/{y}_{tag}_{r}.json"))).set_index("playerId")
        S, Rt, F, T = rd("summary"), rd("realtime"), rd("faceoffwins"), rd("timeonice")
        d = S[["skaterFullName", "positionCode", "gamesPlayed", "goals", "assists", "plusMinus", "penaltyMinutes", "shots", "timeOnIcePerGame"]].copy()
        d.columns = ["n", "pos", "gp", "g", "a", "pm", "pim", "sog", "toi"]
        d = d.join(Rt[["hits", "blockedShots"]].rename(columns={"hits": "hit", "blockedShots": "blk"})).join(F[["totalFaceoffWins"]].rename(columns={"totalFaceoffWins": "fow"}))
        d = d.join(T[["ppTimeOnIcePerGame"]].rename(columns={"ppTimeOnIcePerGame": "pp"})).fillna(0)
        d["toi"] /= 60; d["pp"] /= 60; d["slot"] = d.pos.map({"C": "C", "L": "W", "R": "W", "D": "D"})
        d["fp"] = sum(d.slot.map(lambda s: SK[s].get(c, {"pm": 1, "pim": .5, "hit": .25, "blk": .25}.get(c, 0))) * d[c] for c in CATS)
        return d
    FULL = {y: load(y, "full") for y in range(2013, 2026)}
    bios = {}
    for y in range(2013, 2026):
        for r in json.load(open(f"{RAW}/{y}_full_bios.json")):
            bios.setdefault(r["playerId"], (r.get("birthDate"), r.get("draftOverall")))
    f25 = FULL[2025].assign(v=lambda d: d.fp / TG[2025] * 82)
    rank = {s: int((f25[f25.slot == s].v >= SITE_REPL[s]).sum()) for s in SITE_REPL}
    REPL = {y: {s: float(FULL[y].assign(v=lambda d: d.fp / TG[y] * 82).query("slot == @s").v.sort_values(ascending=False).iloc[rank[s] - 1]) for s in SITE_REPL} for y in FULL}
    rows = []
    for T in range(2016, 2025):
        cur = {t: load(T, t) for t in ("d23", "d50")}; cur["full"] = FULL[T]; nxt = FULL[T + 1]
        for pid, f in cur["full"].iterrows():
            if f.slot not in SK: continue
            b = bios.get(pid, (None, None))
            r = dict(pid=pid, T=T, name=f["n"], slot=f.slot, dov=b[1], age=(pd.Timestamp(f"{T}-10-01") - pd.Timestamp(b[0])).days / 365.25 if b[0] else np.nan)
            for k in (1, 2, 3):
                p = FULL.get(T - k); q = p.loc[pid] if p is not None and pid in p.index else None
                r[f"gp_L{k}"] = q.gp if q is not None else 0; r[f"tg_L{k}"] = TG[T - k]
                for c in CATS + ["toi", "pp", "sog"]: r[f"{c}_L{k}"] = q[c] if q is not None else np.nan
            for t in ("d23", "d50", "full"):
                q = cur[t].loc[pid] if pid in cur[t].index else None
                r[f"gp_{t}"] = q.gp if q is not None else 0
                for c in CATS + ["toi", "pp", "sog"]: r[f"{c}_{t}"] = q[c] if q is not None else np.nan
            r["tg_d23"], r["tg_d50"] = cur["d23"].gp.quantile(0.97), cur["d50"].gp.quantile(0.97)
            q = nxt.loc[pid] if pid in nxt.index else None
            fpN = 0.0 if q is None else sum(SK[f.slot].get(c, {"pm": 1, "pim": .5, "hit": .25, "blk": .25}.get(c, 0)) * q[c] for c in CATS)
            r["vorp_N"] = fpN / TG[T + 1] * 82 - REPL[T + 1][f.slot]; r["repl_T"] = REPL[T][f.slot]; r["repl_L1"] = REPL[T - 1][f.slot]
            rows.append(r)
    pd.DataFrame(rows).to_pickle(os.path.join(LAB, "kc_frame.pkl")); print(len(rows), "rows")

def fit():
    import numpy as np, pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    D = pd.read_pickle(os.path.join(LAB, "kc_frame.pkl"))
    wv = lambda s, c: SK[s].get(c, {"pm": 1, "pim": .5, "hit": .25, "blk": .25}.get(c, 0))
    agef = lambda a: np.clip(AGEC[0] * np.clip(a, 19, 37) ** 2 + AGEC[1] * np.clip(a, 19, 37) + AGEC[2], 0.6, 1.1)
    D["age"] = D.age.fillna(D.age.median())
    wk = {1: 5, 2: 3, 3: 2}; den = sum(wk[k] * D[f"gp_L{k}"] for k in wk)
    inl = {k: sum(D[f"gp_L{j}"] for j in range(k, 4)) > 0 for k in wk}
    base = {s: {c: float((D[(D.slot == s) & (D.gp_L1 >= 40)][f"{c}_L1"] / D[(D.slot == s) & (D.gp_L1 >= 40)].gp_L1).quantile(0.3)) for c in CATS} for s in SK}
    for c in CATS:
        D[f"pr_{c}"] = (sum(wk[k] * D[f"{c}_L{k}"].fillna(0) for k in wk) + 20 * D.slot.map(lambda s: base[s][c])) / (den + 20)
    D["prior_pg"] = sum(D.slot.map(lambda s: wv(s, c)) * D[f"pr_{c}"] for c in CATS)
    D["prior_sh"] = ((den + 6) / (sum(wk[k] * D[f"tg_L{k}"] * inl[k] for k in wk) + 10)).clip(0.1, 1)
    D["vorp_prior"] = D.prior_pg * agef(D.age) * 82 * D.prior_sh - D.repl_T
    D["vorp_L1"] = sum(D.slot.map(lambda s: wv(s, c)) * D[f"{c}_L1"].fillna(0) for c in CATS) / D.tg_L1 * 82 - D.repl_L1
    D["LN"] = D.groupby("T").vorp_N.transform(lambda v: v.sort_values(ascending=False).iloc[TOPN - 1])
    D["PL"] = D.groupby("T").vorp_prior.transform(lambda v: v.sort_values(ascending=False).iloc[TOPN - 1])
    D["K_N"] = (D.vorp_N >= D.LN).astype(int)
    FE = ["gap", "pre_gap", "dev", "dtoi", "dpp", "agec", "young", "rookie", "y_dev", "r_dev", "share", "sC", "sD", "ldov"]
    for t, key in (("d23", "g10"), ("d50", "g22")):
        X = D.copy(); n = X[f"gp_{t}"]; X["n"] = n
        early = sum(X.slot.map(lambda s: wv(s, c)) * X[f"{c}_{t}"].fillna(0) for c in CATS) / n
        X["dtoi"] = ((X[f"toi_{t}"] - X.toi_L1.where(X.gp_L1 >= 10)).clip(-6, 6) * n / (n + 5)).fillna(0)
        X["dpp"] = ((X[f"pp_{t}"] - X.pp_L1.where(X.gp_L1 >= 10)).clip(-3, 3) * n / (n + 5)).fillna(0)
        po = sum(X.slot.map(lambda s: wv(s, c)) * (KS[c] * X[f"pr_{c}"] + X[f"{c}_{t}"].fillna(0)) / (KS[c] + n) for c in CATS) + 0.043 * X.dtoi + 0.033 * X.dpp
        X["gap"] = X.prior_pg * (po / X.prior_pg).clip(0.5, 1.8) * agef(X.age) * 82 * X.prior_sh - X.repl_T - X.PL
        X["pre_gap"] = X.vorp_prior - X.PL
        X["dev"] = (early - X.prior_pg) * n / (n + 10)
        X["agec"] = X.age - 26; X["young"] = (X.age < 24).astype(float)
        X["rookie"] = ((X.gp_L1 + X.gp_L2 + X.gp_L3) < 30).astype(float)
        X["y_dev"] = X.young * X.dev; X["r_dev"] = X.rookie * X.dev
        X["share"] = (n / X[f"tg_{t}"]).clip(0, 1); X["sC"] = (X.slot == "C") * 1.0; X["sD"] = (X.slot == "D") * 1.0
        X["ldov"] = np.log(X.dov.fillna(250).clip(1, 250))
        P = X[(X.vorp_prior < X.PL) & (X.vorp_L1 < X.PL) & (n >= 3)].copy(); P["p"] = np.nan
        for T in sorted(P["T"].unique()):
            m = LogisticRegression(C=1.0, max_iter=5000).fit(P[P["T"] != T][FE], P[P["T"] != T].K_N)
            P.loc[P["T"] == T, "p"] = m.predict_proba(P[P["T"] == T][FE])[:, 1]
        top = P.sort_values("p", ascending=False).groupby("T").head(20); fl = P[P.p >= 0.25]
        print(key, "AUC", round(roc_auc_score(P.K_N, P.p), 3), "top20 caught", round(top.K_N.sum() / P.K_N.sum(), 3),
              "flag25", round(len(fl) / P["T"].nunique(), 1), "a season, hit", round(fl.K_N.mean(), 3))
        m = LogisticRegression(C=1.0, max_iter=5000).fit(P[FE], P.K_N)
        print(key, json.dumps(dict(b=round(float(m.intercept_[0]), 4), **{k: round(float(v), 5) for k, v in zip(FE, m.coef_[0])})))

if __name__ == "__main__":
    {"fetch": fetch, "frame": frame, "fit": fit}[sys.argv[1] if len(sys.argv) > 1 else "fit"]()
