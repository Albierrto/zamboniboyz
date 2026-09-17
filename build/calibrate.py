"""How projected season totals line up with what happened (backtest seasons 2023-24 to 2025-26)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "build")
import model as M

def rows():
    sk = pd.read_pickle("data/skater_seasons.pkl"); gl = pd.read_pickle("data/goalie_seasons.pkl")
    out = []
    for T in (2024, 2025, 2026):
        ps = M.project_skaters(sk, T); a = M.actual_skater_points(sk, T)
        m = ps.merge(a[["playerId", "pts_act"]], on="playerId", how="left"); m["pts_act"] = m.pts_act.fillna(0)
        m = m[m.gp_last >= 20].assign(T=T, grp=lambda x: x.pg)
        out.append(m[["T", "grp", "proj_pts", "pts_act", "name"]])
        pg = M.project_goalies(gl, T, M.GP_)
        tt = gl[gl.season == T].set_index("playerId").teams.str.split(",").str[-1].str.strip()
        lt = pg.team_last.astype(str).str.split(",").str[-1].str.strip()
        pg = M.allocate_starts(pg, pg.playerId.map(tt).fillna(lt), M.GP_["cap"], M.GP_["gamma"], incumbent=M.GP_["inc"])
        ag = M.actual_goalie_points(gl, T)
        g = pg.merge(ag[["playerId", "pts_act"]], on="playerId", how="left"); g["pts_act"] = g.pts_act.fillna(0)
        g = g[g.gp_last >= 10].assign(T=T, grp="G")
        out.append(g[["T", "grp", "proj_pts", "pts_act", "name"]])
    return pd.concat(out)

TOP = {"C": 60, "W": 120, "D": 120, "G": 60}

def fits():
    d = rows(); res = {}
    for grp, n in TOP.items():
        x = d[d.grp == grp].sort_values(["T", "proj_pts"], ascending=[True, False]).groupby("T").head(n)
        b, a = np.polyfit(x.proj_pts, x.pts_act, 1)
        res[grp] = dict(a=float(a), b=float(b), corr=float(np.corrcoef(x.proj_pts, x.pts_act)[0, 1]), n=len(x),
                        top12_proj=float(x.groupby("T").head(12).proj_pts.mean()), top12_act=float(x.groupby("T").head(12).pts_act.mean()))
    return res

def goalie_fit():
    return fits()["G"]

if __name__ == "__main__":
    for k, v in fits().items(): print(k, {a: round(b, 2) for a, b in v.items()})
