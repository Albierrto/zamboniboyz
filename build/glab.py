"""Goalie research harness (2010-11 to 2025-26)."""
import numpy as np, pandas as pd, sys
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingRegressor
G = pd.read_pickle("data/gl_all.pkl"); TEAM = pd.read_pickle("data/team_all.pkl")
G["share"] = (G.gs / G.slen).clip(upper=1)
G["age"] = (pd.to_datetime(G.season.astype(str) + "-02-01") - pd.to_datetime(G.birthDate, errors="coerce")).dt.days / 365.25
G["fpts"] = 3 * G.w + 0.25 * G.sv - G.ga + 4 * G.so + 2 * G.a + 0.5 * G.pim

P1 = dict(decay=0.7, decay_gs=0.1, k_gs=0.1, prior_gs=0.15, k_win=10, k_sa=15, k_sv=6000, k_so=400, k_gpgs=10, cap=1.0)

def v1(T, p=P1):
    h = G[(G.season < T) & (G.season >= T - 3)].copy()
    h["w8"] = p["decay"] ** (T - 1 - h.season); h["w9"] = p["decay_gs"] ** (T - 1 - h.season)
    lg = h[h.gp >= 20]
    L = dict(win=lg.w.sum() / lg.gs.sum(), sa=lg.sa.sum() / lg.gp.sum(), sv=lg.sv.sum() / lg.sa.sum(), so=lg.so.sum() / lg.gs.sum(),
             gsgp=lg.gs.sum() / lg.gp.sum(), a=lg.a.sum() / lg.gp.sum(), pim=lg.pim.sum() / lg.gp.sum())
    for c in ["gp", "gs", "w", "sv", "sa", "ga", "so", "a", "pim"]:
        h["x_" + c] = h.w8 * h[c]
    h["x_share"] = h.w9 * h.share
    h = h.sort_values(["playerId", "season"])
    last = h.groupby("playerId").tail(1).set_index("playerId")
    o = last[["name", "age", "team", "season", "gp", "share", "gs"]].rename(columns={"season": "last_season", "gp": "gp_last", "share": "share_last", "gs": "gs_last", "team": "team_last"})
    o = o.join(h.groupby("playerId")[[c for c in h.columns if c.startswith("x_")] + ["w8", "w9"]].sum())
    o["claim"] = (o.x_share + p["k_gs"] * p["prior_gs"]) / (o.w9 + p["k_gs"])
    o["gs_per_gp"] = (o.x_gs + p["k_gpgs"] * L["gsgp"]) / (o.x_gp + p["k_gpgs"])
    o["win_rate"] = (o.x_w + p["k_win"] * L["win"]) / (o.x_gs + p["k_win"])
    o["sa_pg"] = (o.x_sa + p["k_sa"] * L["sa"]) / (o.x_gp + p["k_sa"])
    o["sv_pct"] = (o.x_sv + p["k_sv"] * L["sv"]) / (o.x_sa + p["k_sv"])
    o["so_rate"] = (o.x_so + p["k_so"] * L["so"]) / (o.x_gs + p["k_so"])
    o["a_pg"] = (o.x_a + 20 * L["a"]) / (o.x_gp + 20); o["pim_pg"] = (o.x_pim + 20 * L["pim"]) / (o.x_gp + 20)
    o["gp_last"] = np.where(o.last_season == T - 1, o.gp_last, 0)
    o["lg_sv"] = L["sv"]; o["lg_win"] = L["win"]; o["lg_sa"] = L["sa"]
    return o

def ppg(o, win=None, sa=None, sv=None):
    win = o.win_rate if win is None else win; sa = o.sa_pg if sa is None else sa; sv = o.sv_pct if sv is None else sv
    return 3 * win * o.gs_per_gp + 0.25 * sa * sv - sa * (1 - sv) + 4 * o.so_rate * o.gs_per_gp + 2 * o.a_pg + 0.5 * o.pim_pg

def target_team(T, o):
    t = G[G.season == T].set_index("playerId")
    team = t.team.reindex(o.index)
    return team.fillna(o.team_last)

def allocate(o, team, cap):
    o = o.copy(); o["_t"] = team.values
    o["share_p"] = o.claim
    for t, g in o.groupby("_t"):
        tot = g.claim.sum()
        if tot > cap: o.loc[g.index, "share_p"] = g.claim * cap / tot
    return o

def actual(T, o):
    t = G[G.season == T].set_index("playerId")
    nxt = set(G[G.season == T + 1].playerId) if T + 1 <= G.season.max() else set()
    a = pd.DataFrame(index=o.index)
    a["gp"] = t.gp.reindex(o.index); a["ppg"] = (t.fpts / t.gp).reindex(o.index)
    a["tot"] = (t.fpts / t.slen * 82).reindex(o.index); a["share"] = t.share.reindex(o.index)
    keep = a.gp.notna() | o.index.isin(nxt)
    return a[keep].fillna(0)

def evaluate(res):
    rows = []
    for T, d in res.items():
        q = d[d.gp >= 15]; top = d.sort_values("pred_tot", ascending=False).head(60)
        rows.append(dict(T=T, ppg_mae=np.average((q.pred_ppg - q.ppg).abs(), weights=q.gp), tot_mae60=(top.pred_tot - top.tot).abs().mean(),
                         rho60=spearmanr(top.pred_tot, top.tot).statistic, rho30=spearmanr(top.head(30).pred_tot, top.head(30).tot).statistic,
                         share_mae=(top.share_p - top.share).abs().mean()))
    return pd.DataFrame(rows).set_index("T")

def run_v1(Ts, p=P1):
    res = {}
    for T in Ts:
        o = v1(T, p); o = o[o.gp_last >= 10]
        o = allocate(o, target_team(T, o), p["cap"])
        o["pred_ppg"] = ppg(o)
        o["pred_tot"] = o.pred_ppg * o.share_p * 82 / o.gs_per_gp
        a = actual(T, o)
        res[T] = o.join(a, how="inner")
    return res

if __name__ == "__main__":
    Ts = list(range(2016, 2027))
    r = evaluate(run_v1(Ts)); print("v1", r.mean().round(3).to_dict())
    # naive: last season
    res = {}
    for T in Ts:
        l = G[G.season == T - 1].set_index("playerId"); l = l[l.gp >= 10]
        o = pd.DataFrame(index=l.index); o["pred_ppg"] = l.fpts / l.gp; o["pred_tot"] = l.fpts / l.slen * 82; o["share_p"] = l.share
        res[T] = o.join(actual(T, o), how="inner")
    print("naive", evaluate(res).mean().round(3).to_dict())
