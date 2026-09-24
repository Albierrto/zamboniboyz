"""How fast should early-season numbers move a projection? Tuned on 2021-22..2025-26.
For each season and checkpoint (14/28/42/70 days in), posterior rate = (k*prior + n*observed)/(k+n) per stat,
scored against the rest-of-season rate. Also tests ice-time / power-play-time changes as extra signals."""
import json, glob, numpy as np, pandas as pd
from scipy.optimize import minimize_scalar
SK = {"C": dict(g=3.0, a=2.0, fow=0.25), "W": dict(g=3.5, a=2.5, fow=0.0), "D": dict(g=4.0, a=4.0, fow=0.25)}
COM = dict(pm=1.0, pim=0.5, hit=0.25, blk=0.25)
CATS = ["g", "a", "pm", "pim", "hit", "blk", "fow"]
def w(pg, c): return SK[pg].get(c, COM.get(c, 0))

def load_split(T, c, win):
    f = lambda rep: pd.DataFrame(json.load(open(f"data/raw/splits/{T}_{c}_{win}_skater_{rep}.json"))).set_index("playerId")
    s, r, fo, t = f("summary"), f("realtime"), f("faceoffwins"), f("timeonice")
    d = pd.DataFrame({"gp": s.gamesPlayed, "g": s.goals, "a": s.assists, "pm": s.plusMinus, "pim": s.penaltyMinutes})
    d["hit"] = r.hits.reindex(d.index); d["blk"] = r.blockedShots.reindex(d.index)
    d["fow"] = fo.totalFaceoffWins.reindex(d.index).fillna(0)
    d["toi"] = t.timeOnIcePerGame.reindex(d.index) / 60; d["pptoi"] = t.ppTimeOnIcePerGame.reindex(d.index) / 60
    return d

def rows():
    frames = pd.read_pickle("data/lab_v2_frames.pkl")
    out = []
    for T in (2022, 2023, 2024, 2025, 2026):
        fr = frames[T]
        for c in (14, 28, 42, 70):
            to, rest = load_split(T, c, "to"), load_split(T, c, "rest")
            d = fr[["pg", "pred_ppg", "toi_L1", "pptoi_L1", "age"] + [f"rate_{x}" for x in CATS]].join(to.add_prefix("o_"), how="inner").join(rest.add_prefix("r_"), how="inner")
            d = d[(d.o_gp >= 1) & (d.r_gp >= 10)].copy()
            d["T"], d["c"] = T, c
            out.append(d)
    D = pd.concat(out)
    # prior per-game rates, scaled so the prior's points match the model's projection
    base = sum(D[f"rate_{x}"] * [w(p, x) for p in D.pg] for x in CATS)
    s = (D.pred_ppg / base.replace(0, np.nan)).clip(0.5, 1.6).fillna(1.0)
    for x in CATS:
        D[f"pr_{x}"] = D[f"rate_{x}"] * s
        D[f"ob_{x}"] = D[f"o_{x}"] / D.o_gp
        D[f"rr_{x}"] = D[f"r_{x}"] / D.r_gp
    return D

def ppg(D, pref):
    return sum(D[f"{pref}{x}"] * np.array([w(p, x) for p in D.pg]) for x in CATS)

if __name__ == "__main__":
    D = rows()
    print("rows", len(D), D.groupby(["c"]).size().to_dict())
    K = {}
    for x in CATS:
        def loss(k, x=x):
            post = (k * D[f"pr_{x}"] + D.o_gp * D[f"ob_{x}"]) / (k + D.o_gp)
            return float(np.average((post - D[f"rr_{x}"]) ** 2, weights=D.r_gp))
        r = minimize_scalar(loss, bounds=(0.5, 400), method="bounded")
        K[x] = round(float(r.x), 1)
    print("tuned k (games of prior weight) per stat:", K)
    for x in CATS:
        D[f"po_{x}"] = (K[x] * D[f"pr_{x}"] + D.o_gp * D[f"ob_{x}"]) / (K[x] + D.o_gp)
    D["prior_ppg"], D["obs_ppg"], D["post_ppg"], D["ros_ppg"] = ppg(D, "pr_"), ppg(D, "ob_"), ppg(D, "po_"), ppg(D, "rr_")
    for c, g in D.groupby("c"):
        e = lambda col: np.average((g[col] - g.ros_ppg).abs(), weights=g.r_gp)
        print(f"day {c:2d}: miss per game  prior {e('prior_ppg'):.3f}  early-only {e('obs_ppg'):.3f}  blended {e('post_ppg'):.3f}  (n={len(g)})")
    # do ice-time changes add anything beyond the blend?
    D["dtoi"] = D.o_toi - D.toi_L1; D["dpp"] = D.o_pptoi - D.pptoi_L1
    D["res"] = D.ros_ppg - D.post_ppg
    for c, g in D.groupby("c"):
        g = g.dropna(subset=["dtoi", "dpp"])
        A = np.column_stack([g.dtoi, g.dpp]); wts = g.r_gp.values
        coef = np.linalg.lstsq(A * np.sqrt(wts)[:, None], g.res.values * np.sqrt(wts), rcond=None)[0]
        print(f"day {c}: extra per game per +1 min ice time {coef[0]:+.3f}, per +1 min power play {coef[1]:+.3f}")
    json.dump(dict(k=K), open("data/inseason_k.json", "w"))
    D.to_pickle("data/inseason_rows.pkl")
