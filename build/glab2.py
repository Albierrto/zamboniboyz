import numpy as np, pandas as pd, sys
sys.path.insert(0, "build")
import glab as GL
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingRegressor
G, TEAM = GL.G, GL.TEAM

def frame(T):
    o = GL.v1(T); o = o[o.gp_last >= 10].copy()
    team = GL.target_team(T, o); o["team_T"] = team
    o["moved"] = (team != o.team_last).astype(float)
    o["v1_ppg"] = GL.ppg(o)
    # teammates' claims on the target team
    tot = o.groupby("team_T").claim.transform("sum")
    o["mates_claim"] = tot - o.claim
    o["team_rank"] = o.groupby("team_T").claim.rank(ascending=False)
    o["n_team"] = o.groupby("team_T").claim.transform("count")
    tp = TEAM[TEAM.season == T - 1].set_index("team")
    o["team_w"] = o.team_T.map(tp.w_pg); o["team_sa"] = o.team_T.map(tp.sa_pg); o["team_ga"] = o.team_T.map(tp.ga_pg)
    l1 = G[G.season == T - 1].set_index("playerId"); l2 = G[G.season == T - 2].set_index("playerId")
    o["sv_L1"] = (l1.sv / l1.sa).reindex(o.index); o["share_L2"] = l2.share.reindex(o.index).fillna(0)
    o["win_L1"] = (l1.w / l1.gs.replace(0, np.nan)).reindex(o.index)
    o["car_gs"] = G[G.season < T].groupby("playerId").gs.sum().reindex(o.index)
    o["svx"] = o.sv_pct - o.lg_sv
    # base allocation (v1)
    alloc = GL.allocate(o, team, 1.0); o["v1_share"] = alloc.share_p
    a = GL.actual(T, o)
    o = o.join(a.add_prefix("y_"), how="inner")
    o["y_gs_share"] = o.y_share
    o["T"] = T
    return o

F_SHARE = ["claim", "v1_share", "share_last", "share_L2", "gp_last", "age", "svx", "sv_L1", "mates_claim", "team_rank", "n_team", "moved", "car_gs", "win_L1"]
F_PPG = ["v1_ppg", "win_rate", "sa_pg", "sv_pct", "svx", "team_w", "team_sa", "team_ga", "moved", "age", "sv_L1", "win_L1", "gs_per_gp"]

def ridge(a): return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=a))
def gbm(): return HistGradientBoostingRegressor(max_iter=150, learning_rate=0.03, max_leaf_nodes=7, min_samples_leaf=30, l2_regularization=2.0)

def run(frames, Ts, share_m="ridge", ppg_m="ridge", alpha=30, cap_norm=True):
    res = {}
    for T in Ts:
        tr = pd.concat([frames[t] for t in frames if t < T]); te = frames[T].copy()
        # share
        if share_m == "v1": te["share_p"] = te.v1_share
        else:
            m = ridge(alpha) if share_m == "ridge" else gbm()
            m.fit(tr[F_SHARE], tr.y_gs_share - tr.v1_share)
            te["share_p"] = (te.v1_share + m.predict(te[F_SHARE])).clip(0, 0.85)
            if cap_norm:
                s = te.groupby("team_T").share_p.transform("sum")
                te["share_p"] = np.where(s > 1.0, te.share_p / s, te.share_p)
        # ppg
        if ppg_m == "v1": te["pred_ppg"] = te.v1_ppg
        else:
            q = tr.y_gp >= 10
            m = ridge(alpha) if ppg_m == "ridge" else gbm()
            m.fit(tr.loc[q, F_PPG], (tr.y_ppg - tr.v1_ppg)[q], **({"ridge__sample_weight": tr.y_gp[q]} if ppg_m == "ridge" else {"sample_weight": tr.y_gp[q]}))
            te["pred_ppg"] = te.v1_ppg + m.predict(te[F_PPG])
        te["pred_tot"] = te.pred_ppg * te.share_p * 82 / te.gs_per_gp
        d = te.rename(columns={"y_gp": "gp", "y_ppg": "ppg", "y_tot": "tot", "y_share": "share"})
        res[T] = d
    return res

if __name__ == "__main__":
    frames = {T: frame(T) for T in range(2012, 2027)}
    pd.to_pickle(frames, "data/glab_frames.pkl")
    Ts = list(range(2016, 2027))
    base = GL.evaluate(run(frames, Ts, "v1", "v1")); print("v1        ", base.mean().round(3).to_dict())
    for sm, pm, a in [("ridge", "v1", 30), ("v1", "ridge", 30), ("ridge", "ridge", 30), ("ridge", "ridge", 100), ("gbm", "ridge", 30), ("ridge", "gbm", 30), ("gbm", "gbm", 30)]:
        r = GL.evaluate(run(frames, Ts, sm, pm, a)); d = r - base
        print(f"{sm:5} {pm:5} a={a:3}", r.mean().round(3).to_dict(), "tot wins", int((d.tot_mae60 < 0).sum()), "rho wins", int((d.rho60 > 0).sum()))
