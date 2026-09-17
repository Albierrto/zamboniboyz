"""League-scoring projections for ZamboniBoyz (Fantrax, H2H points)."""
import numpy as np, pandas as pd
from math import exp

# ---- league scoring (from Fantrax getLeagueInfo) ----
SK = {  # per event, by scoring position
    "C": dict(g=3.0, a=2.0, fow=0.25),
    "W": dict(g=3.5, a=2.5, fow=0.0),
    "D": dict(g=4.0, a=4.0, fow=0.25),
}
COMMON = dict(pm=1.0, pim=0.5, hit=0.25, blk=0.25, ht=3.0)
GOALIE = dict(w=3.0, sv=0.25, ga=-1.0, so=4.0, g=3.0, a=2.0, pim=0.5)

def p_hat_trick(lam):
    lam = np.clip(lam, 0, 3)
    return 1 - np.exp(-lam) * (1 + lam + lam ** 2 / 2)

def skater_ppg(r, pos):
    """r: dict/Series of per-game rates (g, a, pm, pim, hit, blk, fow)."""
    s = SK[pos]
    return (s["g"] * r["g"] + s["a"] * r["a"] + s["fow"] * r["fow"] + COMMON["pm"] * r["pm"] + COMMON["pim"] * r["pim"]
            + COMMON["hit"] * r["hit"] + COMMON["blk"] * r["blk"] + COMMON["ht"] * p_hat_trick(r["g"]))

def pos_group(npos):
    return {"C": "C", "L": "W", "R": "W", "D": "D"}.get(npos, "W")

def age_on(birth, season_end):
    # age on Feb 1 of the season
    b = pd.to_datetime(birth, errors="coerce")
    ref = pd.Timestamp(f"{season_end}-02-01")
    return (ref - b).dt.days / 365.25

# ---- default parameters (tuned by backtest.py) ----
P = dict(
    decay=0.5,            # weight of season t-2 relative to t-1 (t-3 gets decay^2)
    k_rate=dict(shots=5, a=10, pm=150, pim=10, hit=40, blk=5, fow=2.5),  # games of prior added
    k_sh=200,             # shots of league-average finishing added to a player's career shooting %
    prior_q=0.5,          # prior = this quantile of regulars' per-game rate at the position
    k_gp=0.3,             # seasons of prior availability added
    prior_avail=0.80,
    age_on=True,
    age_scale=2.0,
)

AGE_PTS = {19: 1.14, 20: 1.14, 21: 1.14, 22: 1.12, 23: 1.07, 24: 1.06, 25: 1.01, 26: 0.995, 27: 0.995,
           28: 0.975, 29: 0.975, 30: 0.96, 31: 0.937, 32: 0.937, 33: 0.93, 34: 0.93, 35: 0.91}

def age_factor(age, scale=1.0):
    """Scoring-rate multiplier for next season by age: year-over-year points-per-game ratios
    for regulars 2022-2026 (backtest.py), smoothed, times a tuned scale."""
    age = np.asarray(age, dtype=float)
    a = np.clip(np.round(np.nan_to_num(age, nan=27)), 19, 35).astype(int)
    f = np.array([AGE_PTS[x] for x in a])
    f = 1 + scale * (f - 1)
    return np.where(np.isnan(age), 1.0, f)

CATS = ["shots", "g", "a", "pm", "pim", "hit", "blk", "fow"]

def project_skaters(df, T, p=P, players=None):
    """Project season T per-game rates and games from seasons < T. df = skater_seasons."""
    hist = df[(df.season < T) & (df.season >= T - 3)].copy()
    hist["w"] = p["decay"] ** (T - 1 - hist.season)
    hist["pg"] = hist.npos.map(pos_group)
    reg = hist[hist.gp >= 40]
    prior = {pg: {c: np.quantile(grp[c] / grp.gp, p["prior_q"]) for c in CATS} | {"toi": np.quantile(grp.toi, p["prior_q"])}
             for pg, grp in reg.groupby("pg")}
    lg_sh = {pg: grp.g.sum() / max(grp.shots.sum(), 1) for pg, grp in reg.groupby("pg")}
    hist = hist.sort_values(["playerId", "season"])
    last = hist.groupby("playerId").tail(1).set_index("playerId")
    out = last[["name", "npos", "pg", "birthDate", "currentTeamAbbrev", "teams", "season", "gp"]].rename(
        columns={"currentTeamAbbrev": "cur_team", "teams": "team_last", "season": "last_season", "gp": "gp_lastrow"})
    for c in CATS + ["gp"]:
        hist["w_" + c] = hist.w * hist[c]
    hist["w_toi"] = hist.w * hist.gp * hist.toi
    hist["w_pptoi"] = hist.w * hist.gp * hist.pptoi
    hist["w_avail"] = hist.w * hist.gp / 82
    g = hist.groupby("playerId")
    agg = g[[f"w_{c}" for c in CATS + ["gp", "toi", "pptoi", "avail"]] + ["w"]].sum()
    out = out.join(agg)
    out["wgp"] = out.w_gp
    pri = pd.DataFrame(prior).T
    for c in CATS:
        if c == "g":
            continue
        k = p["k_rate"][c]
        out[c] = (out["w_" + c] + k * out.pg.map(pri[c])) / (out.wgp + k)
    allh = df[df.season < T].groupby("playerId")[["g", "shots"]].sum()
    out = out.join(allh.rename(columns={"g": "car_g", "shots": "car_shots"}))
    out["sh"] = (out.car_g + p["k_sh"] * out.pg.map(lg_sh)) / (out.car_shots + p["k_sh"])
    out["g"] = out.shots * out.sh
    out["toi"] = (out.w_toi + 10 * out.pg.map(pri["toi"])) / (out.wgp + 10)
    out["pptoi"] = out.w_pptoi / out.wgp.clip(lower=1e-9)
    out["avail"] = ((out.w_avail + p["k_gp"] * p["prior_avail"]) / (out.w + p["k_gp"])).clip(upper=0.98)
    out["gp_last"] = np.where(out.last_season == T - 1, out.gp_lastrow, 0)
    out["age"] = age_on(out.birthDate, T)
    if p["age_on"]:
        f = age_factor(out.age, p["age_scale"])
        for c in ["g", "a", "shots"]:
            out[c] = out[c] * f
    out["ppg"] = 0.0
    for pg in ["C", "W", "D"]:
        m = out.pg == pg
        out.loc[m, "ppg"] = skater_ppg(out[m], pg)
    out["proj_gp"] = 82 * out.avail
    out["proj_pts"] = out.ppg * out.proj_gp
    return out.reset_index()

def actual_skater_points(df, T):
    a = df[df.season == T].copy()
    a["pg"] = a.npos.map(pos_group)
    rates = a[CATS].div(a.gp, axis=0)
    a["ppg_act"] = 0.0
    for pg in ["C", "W", "D"]:
        m = a.pg == pg
        a.loc[m, "ppg_act"] = skater_ppg(rates[m], pg)
    a["pts_act"] = a.ppg_act * a.gp
    return a[["playerId", "gp", "ppg_act", "pts_act", "pg"]]


# ---------------- goalies ----------------
GP_ = dict(decay=0.7, decay_gs=0.1, k_gs=0.1, prior_gs=0.15, k_win=10, k_sa=15, k_sv=6000, k_so=400, k_gpgs=10, gamma=0.0, cap=1.0, inc=1.0)

def goalie_ppg_from(r):
    return (GOALIE["w"] * r["w_pg"] + GOALIE["sv"] * r["sv_pg"] + GOALIE["ga"] * r["ga_pg"] + GOALIE["so"] * r["so_pg"]
            + GOALIE["a"] * r["a_pg"] + GOALIE["pim"] * r["pim_pg"])

def project_goalies(gdf, T, p=GP_):
    h = gdf[(gdf.season < T) & (gdf.season >= T - 3)].copy()
    h["w8"] = p["decay"] ** (T - 1 - h.season)
    lg = h[h.gp >= 20]
    lg_win = lg.w.sum() / lg.gs.sum(); lg_sa = lg.sa.sum() / lg.gp.sum(); lg_sv = lg.sv.sum() / lg.sa.sum()
    lg_so = lg.so.sum() / lg.gs.sum(); lg_gsgp = lg.gs.sum() / lg.gp.sum()
    lg_a = lg.a.sum() / lg.gp.sum(); lg_pim = lg.pim.sum() / lg.gp.sum()
    for c in ["gp", "gs", "w", "sv", "sa", "ga", "so", "a", "pim"]:
        h["x_" + c] = h.w8 * h[c]
    h["w9"] = p["decay_gs"] ** (T - 1 - h.season)
    h["x_share"] = h.w9 * h.gs / 82
    h = h.sort_values(["playerId", "season"])
    last = h.groupby("playerId").tail(1).set_index("playerId")
    agg = h.groupby("playerId")[[c for c in h.columns if c.startswith("x_")] + ["w8", "w9"]].sum()
    o = last[["name", "birthDate", "currentTeamAbbrev", "teams", "season", "gp"]].rename(
        columns={"currentTeamAbbrev": "cur_team", "teams": "team_last", "season": "last_season", "gp": "gp_lastrow"}).join(agg)
    o["gs_share"] = (o.x_share + p["k_gs"] * p["prior_gs"]) / (o.w9 + p["k_gs"])
    o["gs_per_gp"] = (o.x_gs + p["k_gpgs"] * lg_gsgp) / (o.x_gp + p["k_gpgs"])
    o["win_rate"] = (o.x_w + p["k_win"] * lg_win) / (o.x_gs + p["k_win"])
    o["sa_pg"] = (o.x_sa + p["k_sa"] * lg_sa) / (o.x_gp + p["k_sa"])
    o["sv_pct"] = (o.x_sv + p["k_sv"] * lg_sv) / (o.x_sa + p["k_sv"])
    o["so_rate"] = (o.x_so + p["k_so"] * lg_so) / (o.x_gs + p["k_so"])
    o["w_pg"] = o.win_rate * o.gs_per_gp
    o["so_pg"] = o.so_rate * o.gs_per_gp
    o["sv_pg"] = o.sa_pg * o.sv_pct
    o["ga_pg"] = o.sa_pg * (1 - o.sv_pct)
    o["a_pg"] = (o.x_a + 20 * lg_a) / (o.x_gp + 20)
    o["pim_pg"] = (o.x_pim + 20 * lg_pim) / (o.x_gp + 20)
    o["ppg"] = goalie_ppg_from(o)
    o["proj_gs"] = 82 * o.gs_share
    o["proj_gp"] = o.proj_gs / o.gs_per_gp
    o["proj_pts"] = o.ppg * o.proj_gp
    o["gp_last"] = np.where(o.last_season == T - 1, o.gp_lastrow, 0)
    o["age"] = age_on(o.birthDate, T)
    o["pg"] = "G"
    return o.reset_index()

def actual_goalie_points(gdf, T):
    a = gdf[gdf.season == T].copy()
    a["pts_act"] = GOALIE["w"] * a.w + GOALIE["sv"] * a.sv + GOALIE["ga"] * a.ga + GOALIE["so"] * a.so + GOALIE["a"] * a.a + GOALIE["pim"] * a.pim
    a["ppg_act"] = a.pts_act / a.gp
    return a[["playerId", "gp", "gs", "ppg_act", "pts_act"]]


def allocate_starts(o, team, cap=0.95, gamma=8.0, max_share=0.80, incumbent=1.0):
    """Share a team's starts among its goalies: each goalie's claim (recent workload) weighted by quality^gamma,
    scaled so the team total never exceeds `cap`. team: Series aligned with o (None = no team)."""
    o = o.copy()
    o["_team"] = team.values
    q = o.ppg / o.ppg.median()
    o["_c"] = o.gs_share
    last_team = o.team_last.astype(str).str.split(",").str[-1].str.strip()
    inc = np.where(last_team.values == o._team.values, incumbent, 1.0)
    o["_cq"] = o._c * q ** gamma * inc
    for t, g in o[o._team.notna()].groupby("_team"):
        tot = min(g._c.sum(), cap)
        o.loc[g.index, "gs_share"] = (tot * g._cq / g._cq.sum()).clip(upper=max_share)
    o["proj_gs"] = 82 * o.gs_share
    o["proj_gp"] = o.proj_gs / o.gs_per_gp
    o["proj_pts"] = o.ppg * o.proj_gp
    return o.drop(columns=["_team", "_c", "_cq"])
