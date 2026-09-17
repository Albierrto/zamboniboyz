import numpy as np, pandas as pd, itertools, copy, sys
from scipy.stats import spearmanr
sys.path.insert(0, "build")
import model as M
df = pd.read_pickle("data/skater_seasons.pkl")

def evaluate(p, Ts=(2024, 2025, 2026), verbose=False):
    res = []
    for T in Ts:
        pr = M.project_skaters(df, T, p)
        act = M.actual_skater_points(df, T)
        m = pr.merge(act, on="playerId", how="left", suffixes=("", "_a"))
        m["gp"] = m.gp.fillna(0); m["pts_act"] = m.pts_act.fillna(0)
        # draft-relevant: players who played >= 20 games last season
        base = m[m.gp_last >= 20]
        # PPG accuracy among players with >= 30 GP in T
        q = base[base.gp >= 30]
        mae_ppg = np.average((q.ppg - q.ppg_act).abs(), weights=q.gp)
        top = base.sort_values("proj_pts", ascending=False).head(300)
        rho = spearmanr(top.proj_pts, top.pts_act).statistic
        mae_tot = (top.proj_pts - top.pts_act).abs().mean()
        # naive: last season's ppg * last season gp
        res.append(dict(T=T, mae_ppg=mae_ppg, rho300=rho, mae_tot300=mae_tot, n=len(q)))
    r = pd.DataFrame(res)
    if verbose: print(r.round(4).to_string(index=False))
    return r[["mae_ppg", "rho300", "mae_tot300"]].mean()

def naive(Ts=(2024, 2025, 2026)):
    res = []
    for T in Ts:
        last = M.actual_skater_points(df, T - 1).rename(columns={"ppg_act": "ppg", "pts_act": "proj_pts", "gp": "gp_last"})
        # 3-year GP weighted ppg (simple)
        act = M.actual_skater_points(df, T)
        m = last.merge(act, on="playerId", how="left"); m["gp"] = m.gp.fillna(0); m["pts_act"] = m.pts_act.fillna(0)
        base = m[m.gp_last >= 20]; q = base[base.gp >= 30]
        top = base.sort_values("proj_pts", ascending=False).head(300)
        res.append(dict(T=T, mae_ppg=np.average((q.ppg - q.ppg_act).abs(), weights=q.gp),
                        rho300=spearmanr(top.proj_pts, top.pts_act).statistic, mae_tot300=(top.proj_pts - top.pts_act).abs().mean()))
    r = pd.DataFrame(res); print("NAIVE last season"); print(r.round(4).to_string(index=False)); return r.mean(numeric_only=True)

if __name__ == "__main__":
    print(naive())
    print("MODEL default"); print(evaluate(M.P, verbose=True))
