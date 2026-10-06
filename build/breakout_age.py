"""Do veterans break out? (Bort: "does a 31 year old really break out in hockey? in baseball that would be rare")
On the breakout pool (build/breakoutlab2.py, 2017-18..2025-26): breakout rate by age, and for breakout seasons what
changed: ice time and power-play time (from the next season's L1 columns), where the extra points came from, and how
much of the breakout year a player kept the season after. Adds the numbers to data/breakout2_meta.json as test.age."""
import json
import numpy as np, pandas as pd

META = json.load(open("data/breakout2_meta.json"))
sk = pd.read_pickle("data/lab_v2_frames.pkl")
P = pd.read_pickle("data/breakout2_oos.pkl"); P = P[P.pool].copy()
W = {"C": dict(g=3.0, a=2.0, fow=0.25), "W": dict(g=3.5, a=2.5, fow=0.0), "D": dict(g=4.0, a=4.0, fow=0.25)}
OLD = 30
P["old"] = P.age >= OLD
rate = P.groupby(pd.cut(P.age, [0, 23, 26, 29, 32, 50]), observed=True).y.mean().round(3)
print("breakout rate by age:", rate.to_dict())

rows = []
for T in range(2018, 2026):
    nx = sk[T + 1][["toi_L1", "pptoi_L1", "g_L1", "a_L1", "pm_L1", "pim_L1", "hit_L1", "blk_L1", "fow_L1", "gp_L1"]].rename(columns=lambda c: "n_" + c)
    rows.append(P[P.season == T].merge(nx, left_on="pid", right_index=True, how="inner"))
D = pd.concat(rows); D = D[D.n_gp_L1 >= 20]
D["dtoi"] = D.n_toi_L1 - D.toi_L1; D["dpp"] = D.n_pptoi_L1 - D.pptoi_L1
D["role"] = (D.dtoi >= 1.5) | (D.dpp >= 0.75)
pgp = D.pred_tot / D.pred_ppg
for c, k in [("g", None), ("a", None), ("pm", 1), ("pim", .5), ("hit", .25), ("blk", .25), ("fow", None)]:
    w = D.pg.map(lambda s: W[s][c]) if k is None else k
    D["x_" + c] = w * (D["n_" + c + "_L1"] - D["rate_" + c]) * D.n_gp_L1
D["x_games"] = D.pred_ppg * (D.n_gp_L1 - pgp)
B = D[D.y == 1]
src = B.groupby("old")[["x_g", "x_a", "x_pm", "x_games"]].mean().round(1)
print("extra points in breakout seasons by source:\n", src.to_string())

nxt = []
for T in range(2018, 2025):
    a = P[(P.season == T) & (P.y == 1)][["pid", "act_tot", "old"]]
    b = sk[T + 1][["act_tot"]].rename(columns={"act_tot": "nx_tot"})
    nxt.append(a.merge(b, left_on="pid", right_index=True, how="inner"))
N = pd.concat(nxt)
keep = (N.nx_tot / N.act_tot).groupby(N.old).median().round(2)

out = dict(
    rate_old=round(float(P[P.old].y.mean()), 3), rate_young=round(float(P[~P.old].y.mean()), 3),
    rate_u24=round(float(P[P.age < 24].y.mean()), 3),
    role_old=round(float(B[B.old].role.mean()), 2), role_young=round(float(B[~B.old].role.mean()), 2),
    dtoi_old=round(float(B[B.old].dtoi.median()), 2), dtoi_young=round(float(B[~B.old].dtoi.median()), 2),
    keep_old=float(keep[True]), keep_young=float(keep[False]),
    src_old={k: float(v) for k, v in src.loc[True].items()}, old_age=OLD)
print(out)
META["test"]["age"] = out
json.dump(META, open("data/breakout2_meta.json", "w"))
