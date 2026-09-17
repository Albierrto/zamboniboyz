"""2026-27 projections with the tested v2 method.
Skaters: v1 (weighted, shrunk rates) + gradient-boosted corrections learned on 2013-14..2025-26.
Goalies: v1 + ridge corrections for starts and points per game (team context), then calibration."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "build")
import lab as L, lab2 as L2, glab as GL, glab2 as G2
from sklearn.ensemble import HistGradientBoostingRegressor

T = 2027
CFG = [dict(max_iter=150, learning_rate=0.03, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0, random_state=1),
       dict(max_iter=300, learning_rate=0.03, max_leaf_nodes=7, min_samples_leaf=40, l2_regularization=1.0, random_state=2),
       dict(max_iter=250, learning_rate=0.02, max_leaf_nodes=15, min_samples_leaf=60, l2_regularization=2.0, random_state=3)]

class Ens:
    def __init__(self): self.ms = [HistGradientBoostingRegressor(**c) for c in CFG]
    def fit(self, X, y, sample_weight=None):
        for m in self.ms: m.fit(X, y, sample_weight=sample_weight)
        return self
    def predict(self, X): return np.mean([m.predict(X) for m in self.ms], axis=0)

def skaters(team_now):
    """team_now: dict NHL playerId -> 2026-27 team abbrev (from Fantrax), used for the 'moved' feature."""
    df = L.load()
    frames = pd.read_pickle("data/lab_frames.pkl")
    ys = {t: L2.target_cols(df, t, frames[t]) for t in frames}
    X = pd.concat([frames[t][frames[t].gp_last >= 1] for t in frames])
    Y = pd.concat([ys[t].loc[frames[t][frames[t].gp_last >= 1].index] for t in frames])
    Xp = L2.features(df, T)
    Xp["team_T"] = pd.Series(team_now).reindex(Xp.index)
    Xp["moved"] = np.where(Xp.team_T.isna(), np.nan, (Xp.team_T != Xp.team_last).astype(float))
    F = L2.feat_list(Xp)
    out = Xp.copy()
    for c in L.CATS:
        m = (Y.gp.fillna(0) >= 10).values
        mdl = Ens().fit(X[F][m].replace([np.inf, -np.inf], np.nan), (Y[c] - X["v1_" + c])[m], sample_weight=Y.gp[m])
        out["m_" + c] = (Xp["v1_" + c] + mdl.predict(Xp[F].replace([np.inf, -np.inf], np.nan))).clip(lower=-1 if c == "pm" else 0)
    ms = Y.share.notna().values
    mdl = Ens().fit(X[F][ms].replace([np.inf, -np.inf], np.nan), (Y.share - X.v1_avail)[ms])
    out["m_share"] = (Xp.v1_avail + mdl.predict(Xp[F].replace([np.inf, -np.inf], np.nan))).clip(0.02, 0.98)
    return out

def goalies(team_now):
    frames = pd.read_pickle("data/glab_frames.pkl")
    tr = pd.concat(frames.values())
    o = GL.v1(T); o = o[o.gp_last >= 1].copy()
    team = pd.Series(team_now).reindex(o.index)
    o["has_team"] = team.notna()
    o["team_T"] = team.fillna(o.team_last)
    o["moved"] = (o.team_T != o.team_last).astype(float)
    o["v1_ppg"] = GL.ppg(o)
    teamed = o[o.has_team]
    tot = teamed.groupby("team_T").claim.transform("sum")
    o["mates_claim"] = (tot - teamed.claim).reindex(o.index).fillna(0)
    o["team_rank"] = teamed.groupby("team_T").claim.rank(ascending=False).reindex(o.index).fillna(1)
    o["n_team"] = teamed.groupby("team_T").claim.transform("count").reindex(o.index).fillna(1)
    tp = GL.TEAM[GL.TEAM.season == T - 1].set_index("team")
    o["team_w"] = o.team_T.map(tp.w_pg); o["team_sa"] = o.team_T.map(tp.sa_pg); o["team_ga"] = o.team_T.map(tp.ga_pg)
    l1 = GL.G[GL.G.season == T - 1].set_index("playerId"); l2 = GL.G[GL.G.season == T - 2].set_index("playerId")
    o["sv_L1"] = (l1.sv / l1.sa).reindex(o.index); o["share_L2"] = l2.share.reindex(o.index).fillna(0)
    o["win_L1"] = (l1.w / l1.gs.replace(0, np.nan)).reindex(o.index)
    o["car_gs"] = GL.G[GL.G.season < T].groupby("playerId").gs.sum().reindex(o.index)
    o["svx"] = o.sv_pct - o.lg_sv
    o["v1_share"] = o.claim
    for t_, g in o[o.has_team].groupby("team_T"):
        if g.claim.sum() > 1.0: o.loc[g.index, "v1_share"] = g.claim / g.claim.sum()
    ms = G2.ridge(30).fit(tr[G2.F_SHARE], tr.y_gs_share - tr.v1_share)
    o["share_p"] = (o.v1_share + ms.predict(o[G2.F_SHARE])).clip(0, 0.85)
    s = o[o.has_team].groupby("team_T").share_p.transform("sum")
    o.loc[s.index, "share_p"] = np.where(s > 1.0, o.loc[s.index, "share_p"] / s, o.loc[s.index, "share_p"])
    q = tr.y_gp >= 10
    mp = G2.ridge(30).fit(tr.loc[q, G2.F_PPG], (tr.y_ppg - tr.v1_ppg)[q], ridge__sample_weight=tr.y_gp[q])
    o["m_ppg"] = o.v1_ppg + mp.predict(o[G2.F_PPG])
    o["m_tot_raw"] = o.m_ppg * o.share_p * 82 / o.gs_per_gp
    # calibration from the rolling backtest (2016-2026 targets, top 60 a season)
    res = G2.run(frames, list(range(2016, 2027)), "ridge", "ridge", 30)
    d = pd.concat([r.assign(T=t) for t, r in res.items()])
    x = d.sort_values(["T", "pred_tot"], ascending=[True, False]).groupby("T").head(60)
    b, a = np.polyfit(x.pred_tot, x.tot, 1)
    o["cal_a"], o["cal_b"] = a, b
    t12 = x.groupby("T").head(12)
    o["cal_t12p"], o["cal_t12a"] = round(t12.pred_tot.mean()), round(t12.tot.mean())
    return o

if __name__ == "__main__":
    s = skaters({}); g = goalies({})
    print(s[["name", "m_g", "m_a", "m_fow", "m_share"]].head())
    print(g[["name", "share_p", "m_ppg", "m_tot_raw", "cal_a", "cal_b"]].sort_values("m_tot_raw", ascending=False).head(10))
