"""Accuracy report for the page: 11 test seasons (2015-16 to 2025-26), each projected only from earlier seasons."""
import json, sys, numpy as np, pandas as pd
sys.path.insert(0, "build")
import lab as L, glab as GL, glab2 as G2
df = L.load()
Ts = list(range(2016, 2027))
naive = L.metrics({T: L.eval_frame(df, T, L.naive_proj(df, T)) for T in Ts})
v1 = L.metrics({T: L.eval_frame(df, T, L.v1_proj(df, T)) for T in Ts})
v2 = L.metrics(pd.read_pickle("data/lab_v2_frames.pkl"))  # 2018-2026 (needs 4 training seasons)
v1_18 = v1[v1["T"] >= 2018]; nv_18 = naive[naive["T"] >= 2018]
gf = pd.read_pickle("data/glab_frames.pkl")
g_nv = {}
for T in Ts:
    l = GL.G[GL.G.season == T - 1].set_index("playerId"); l = l[l.gp >= 10]
    o = pd.DataFrame(index=l.index); o["pred_ppg"] = l.fpts / l.gp; o["pred_tot"] = l.fpts / l.slen * 82; o["share_p"] = l.share
    g_nv[T] = o.join(GL.actual(T, o), how="inner")
gn = GL.evaluate(g_nv); g1 = GL.evaluate(G2.run(gf, Ts, "v1", "v1")); g2 = GL.evaluate(G2.run(gf, Ts, "ridge", "ridge", 30))
def pack(m, cols):
    return {k: round(float(m[c].mean()), 3 if "rho" in c or "ppg" in c else 1) for k, c in cols.items()}
sc = dict(ppg="ppg_mae", tot="tot_mae300", rho="rho300", rho150="rho150")
gc = dict(ppg="ppg_mae", tot="tot_mae60", rho="rho60")
rep = dict(
    seasons="2017-18 to 2025-26", n_seasons=9,
    skaters=dict(seasons="2017-18 to 2025-26", n_seasons=9, naive=pack(nv_18, sc), v1=pack(v1_18, sc), model=pack(v2, sc),
                 wins_tot=int(((v2.set_index("T").tot_mae300 - v1_18.set_index("T").tot_mae300) < 0).sum())),
    goalies=dict(seasons="2015-16 to 2025-26", n_seasons=11, naive=pack(gn, gc), v1=pack(g1, gc), model=pack(g2, gc),
                 wins_tot=int(((g2.tot_mae60 - g1.tot_mae60) < 0).sum())),
    market=dict(seasons="2023-24 to 2025-26", skater_model=dict(rho=0.633, mae=53.6), skater_market=dict(rho=0.558, mae=61.0),
                skater_blend=dict(rho=0.644, mae=53.3), goalie_model=dict(rho=0.491, mae=65.1), goalie_market=dict(rho=0.416, mae=65.1),
                goalie_blend=dict(rho=0.498, mae=64.0)),
)
json.dump(rep, open("data/report.json", "w"), indent=1)
print(json.dumps(rep, indent=1))
