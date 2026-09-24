"""Goalies in-season: how fast should starts share and points per start update? (2021-22..2025-26)"""
import json, sys, numpy as np, pandas as pd
from scipy.optimize import minimize_scalar
sys.path.insert(0, "build")
import glab2 as G2
gf = pd.read_pickle("data/glab_frames.pkl")
res = G2.run(gf, [2022, 2023, 2024, 2025, 2026], "ridge", "ridge", 30)
rows = []
for T in (2022, 2023, 2024, 2025, 2026):
    pr = res[T]
    for c in (14, 28, 42, 70):
        to = pd.DataFrame(json.load(open(f"data/raw/splits/{T}_{c}_to_goalie_summary.json"))).set_index("playerId")
        re = pd.DataFrame(json.load(open(f"data/raw/splits/{T}_{c}_rest_goalie_summary.json"))).set_index("playerId")
        sk_to = pd.DataFrame(json.load(open(f"data/raw/splits/{T}_{c}_to_skater_summary.json")))
        sk_re = pd.DataFrame(json.load(open(f"data/raw/splits/{T}_{c}_rest_skater_summary.json")))
        tg_to, tg_re = sk_to.gamesPlayed.quantile(0.95), sk_re.gamesPlayed.quantile(0.95)
        d = pr[["share_p", "pred_ppg", "gs_per_gp"]].join(to.add_prefix("o_"), how="inner").join(re.add_prefix("r_"), how="inner")
        d["tg_to"], d["tg_re"], d["T"], d["c"] = tg_to, tg_re, T, c
        rows.append(d)
D = pd.concat(rows)
D["o_share"] = D.o_gamesStarted / D.tg_to
D["r_share"] = D.r_gamesStarted / D.tg_re
pps = lambda p: (3 * D[p + "wins"] + 0.25 * D[p + "saves"] - D[p + "goalsAgainst"] + 4 * D[p + "shutouts"])
D["o_pps"] = pps("o_") / D.o_gamesStarted.replace(0, np.nan)
D["r_pps"] = pps("r_") / D.r_gamesStarted.replace(0, np.nan)
D["pr_pps"] = D.pred_ppg / D.gs_per_gp.replace(0, np.nan)
def tune(prior, obs, n, target, wts):
    def loss(k):
        post = (k * prior + n * obs.fillna(prior)) / (k + n)
        return float(np.average((post - target) ** 2, weights=wts))
    return minimize_scalar(loss, bounds=(0.5, 300), method="bounded").x
S = D.dropna(subset=["share_p", "r_share"])
ks = tune(S.share_p, S.o_share, S.tg_to, S.r_share, S.tg_re)
Q = D.dropna(subset=["pr_pps", "r_pps"]); Q = Q[Q.r_gamesStarted >= 5]
kq = tune(Q.pr_pps, Q.o_pps, Q.o_gamesStarted, Q.r_pps, Q.r_gamesStarted)
print(f"starts share: prior worth {ks:.1f} team games; points per start: prior worth {kq:.1f} starts")
for c, g in S.groupby("c"):
    post = (ks * g.share_p + g.tg_to * g.o_share) / (ks + g.tg_to)
    print(f"day {c}: share miss prior {np.average((g.share_p-g.r_share).abs(),weights=g.tg_re):.3f} blended {np.average((post-g.r_share).abs(),weights=g.tg_re):.3f}")
json.dump(dict(k_share=round(ks, 1), k_pps=round(kq, 1)), open("data/inseason_goalie_k.json", "w"))
