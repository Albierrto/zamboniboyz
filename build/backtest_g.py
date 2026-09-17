import sys, copy, numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, "build"); import model as M
g = pd.read_pickle("data/goalie_seasons.pkl")
def ev(p, verbose=False, naive=False):
    res = []
    for T in (2024, 2025, 2026):
        if naive:
            pr = M.actual_goalie_points(g, T - 1).rename(columns={"ppg_act": "ppg", "pts_act": "proj_pts", "gp": "gp_last"})
        else:
            pr = M.project_goalies(g, T, p)
            if p.get("gamma") is not None:
                tt = g[g.season == T].set_index("playerId").teams.str.split(",").str[-1].str.strip()
                lt = pr.team_last.astype(str).str.split(",").str[-1].str.strip()
                team = pr.playerId.map(tt).fillna(lt)
                pr = M.allocate_starts(pr, team, p.get("cap", 0.95), p["gamma"], incumbent=p.get("inc", 1.0))
        m = pr.merge(M.actual_goalie_points(g, T), on="playerId", how="left", suffixes=("", "_a"))
        m["gp"] = m.gp.fillna(0); m["pts_act"] = m.pts_act.fillna(0)
        base = m[m.gp_last >= 10]; q = base[base.gp >= 15]
        top = base.sort_values("proj_pts", ascending=False).head(60)
        res.append(dict(T=T, mae_ppg=np.average((q.ppg - q.ppg_act).abs(), weights=q.gp),
                        rho60=spearmanr(top.proj_pts, top.pts_act).statistic, mae_tot60=(top.proj_pts - top.pts_act).abs().mean(), n=len(q)))
    r = pd.DataFrame(res)
    if verbose: print(r.round(3).to_string(index=False))
    return r.mean(numeric_only=True)
if __name__ == "__main__":
    print("naive"); ev(None, True, naive=True)
    p = copy.deepcopy(M.GP_); print("model"); ev(p, True)
    for key, vals in {"k_sv": [500, 1500, 3000, 6000, 12000], "k_win": [10, 30, 60, 120], "k_sa": [5, 15, 40, 100], "k_so": [20, 60, 150, 400],
                      "decay": [0.35, 0.5, 0.7, 0.9]}.items():
        res = []
        for v in vals:
            q = copy.deepcopy(p); q[key] = v; res.append((ev(q).mae_ppg, v))
        p[key] = min(res)[1]; print(key, [(round(a, 4), b) for a, b in res])
    for key, vals in {"k_gs": [0.2, 0.5, 1, 2], "prior_gs": [0.15, 0.25, 0.35, 0.45], "decay": [0.35, 0.5, 0.7, 0.9]}.items():
        res = []
        for v in vals:
            q = copy.deepcopy(p); q[key] = v; r = ev(q); res.append((r.mae_tot60 / 60 - r.rho60, v, round(r.rho60, 3), round(r.mae_tot60, 1)))
        best = min(res)[1]; print(key, res)
        if key != "decay": p[key] = best
    print(p); ev(p, True)
