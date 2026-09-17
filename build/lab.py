"""Research harness: features, v1 baseline, learned models, rolling out-of-sample evaluation."""
import numpy as np, pandas as pd, warnings
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")
SK = {"C": dict(g=3.0, a=2.0, fow=0.25), "W": dict(g=3.5, a=2.5, fow=0.0), "D": dict(g=4.0, a=4.0, fow=0.25)}
CATS = ["shots", "g", "a", "pm", "pim", "hit", "blk", "fow"]
AGE_PTS = {19: 1.14, 20: 1.14, 21: 1.14, 22: 1.12, 23: 1.07, 24: 1.06, 25: 1.01, 26: 0.995, 27: 0.995,
           28: 0.975, 29: 0.975, 30: 0.96, 31: 0.937, 32: 0.937, 33: 0.93, 34: 0.93, 35: 0.91}

def pg(npos): return {"C": "C", "L": "W", "R": "W", "D": "D"}.get(npos, "W")

def p_ht(lam):
    lam = np.clip(lam, 0, 3); return 1 - np.exp(-lam) * (1 + lam + lam ** 2 / 2)

def fppg(r, pos):
    s = SK[pos]
    return s["g"] * r["g"] + s["a"] * r["a"] + s["fow"] * r["fow"] + r["pm"] + 0.5 * r["pim"] + 0.25 * r["hit"] + 0.25 * r["blk"] + 3 * p_ht(r["g"])

def fppg_by_pos(df, pos_col="pg"):
    out = pd.Series(0.0, index=df.index)
    for p in ["C", "W", "D"]:
        m = df[pos_col] == p
        if m.any(): out[m] = fppg(df[m], p)
    return out

def load():
    df = pd.read_pickle("data/sk_all.pkl")
    df["pg"] = df.npos.map(pg)
    df["age"] = (pd.to_datetime(df.season.astype(str) + "-02-01") - pd.to_datetime(df.birthDate, errors="coerce")).dt.days / 365.25
    return df

# ------------------------------------------------------------------ v1 (the live method)
V1_OLD = dict(decay=0.5, k_rate=dict(shots=5, a=10, pm=150, pim=10, hit=40, blk=5, fow=2.5), k_sh=200, prior_q=0.5,
              k_gp=0.3, prior_avail=0.8, age_scale=2.0)
# Retuned on 2013-14..2025-26 targets (build/tune2.py). Better on its own (PPG miss 0.489 vs 0.491),
# but once the learned corrections sit on top the two bases score the same, so the live base stays V1_OLD.
V1_RETUNED = dict(decay=0.4, k_rate=dict(shots=1.25, a=10, pm=75, pim=20, hit=20, blk=20, fow=0.625), k_sh=200, prior_q=0.5,
                  k_gp=0.1, prior_avail=0.9, age_scale=1.5)
V1 = V1_OLD

def v1(df, T, p=V1):
    hist = df[(df.season < T) & (df.season >= T - 3)].copy()
    hist["w"] = p["decay"] ** (T - 1 - hist.season)
    reg = hist[hist.gp >= 40]
    prior = {g: {c: np.quantile(x[c] / x.gp, p["prior_q"]) for c in CATS} for g, x in reg.groupby("pg")}
    lg_sh = {g: x.g.sum() / x.shots.sum() for g, x in reg.groupby("pg")}
    hist = hist.sort_values(["playerId", "season"])
    last = hist.groupby("playerId").tail(1).set_index("playerId")
    out = last[["name", "npos", "pg", "birthDate", "teams", "season", "gp", "toi", "pptoi"]].rename(
        columns={"season": "last_season", "gp": "gp_last", "toi": "toi_last", "pptoi": "pptoi_last"})
    for c in CATS + ["gp"]:
        hist["w_" + c] = hist.w * hist[c]
    hist["w_share"] = hist.w * hist.share
    agg = hist.groupby("playerId")[[f"w_{c}" for c in CATS + ["gp", "share"]] + ["w"]].sum()
    out = out.join(agg)
    pri = pd.DataFrame(prior).T
    for c in CATS:
        if c == "g": continue
        k = p["k_rate"][c]
        out["v1_" + c] = (out["w_" + c] + k * out.pg.map(pri[c])) / (out.w_gp + k)
    car = df[df.season < T].groupby("playerId")[["g", "shots"]].sum()
    out = out.join(car.rename(columns={"g": "car_g", "shots": "car_shots"}))
    out["v1_sh"] = (out.car_g + p["k_sh"] * out.pg.map(lg_sh)) / (out.car_shots + p["k_sh"])
    out["v1_g"] = out.v1_shots * out.v1_sh
    out["v1_avail"] = ((out.w_share + p["k_gp"] * p["prior_avail"]) / (out.w + p["k_gp"])).clip(upper=0.98)
    out.loc[out.last_season != T - 1, "gp_last"] = 0
    age = (pd.Timestamp(f"{T}-02-01") - pd.to_datetime(out.birthDate, errors="coerce")).dt.days / 365.25
    out["age"] = age
    a = np.clip(np.round(np.nan_to_num(age, nan=27)), 19, 35).astype(int)
    f = 1 + p["age_scale"] * (np.array([AGE_PTS[x] for x in a]) - 1)
    for c in ["g", "a", "shots"]:
        out["v1_" + c] *= f
    return out.reset_index()

# ------------------------------------------------------------------ targets
def targets(df, T):
    t = df[df.season == T].set_index("playerId")
    nxt = set(df[df.season == T + 1].playerId) if (T + 1) in set(df.season) else None
    return t, nxt

def eval_frame(df, T, proj):
    """proj: DataFrame indexed by playerId with columns rate_<cat> (per game) and share (0-1)."""
    t, nxt = targets(df, T)
    base = proj.copy()
    base = base[base.gp_last >= 1]
    # actual per-game rates / fantasy ppg (NHL position)
    act = t[CATS].div(t.gp, axis=0)
    act["pg"] = t.pg
    t_ppg = fppg_by_pos(act)
    base["act_gp"] = t.gp.reindex(base.index)
    base["act_share"] = t.share.reindex(base.index)
    base["act_ppg"] = t_ppg.reindex(base.index)
    present = base.act_gp.notna()
    if nxt is not None:
        keep = present | base.index.isin(nxt)
    else:
        keep = present
    base = base[keep].copy()
    base["act_gp"] = base.act_gp.fillna(0); base["act_share"] = base.act_share.fillna(0); base["act_ppg"] = base.act_ppg.fillna(0)
    rates = pd.DataFrame({c: base["rate_" + c] for c in CATS}); rates["pg"] = base.pg
    base["pred_ppg"] = fppg_by_pos(rates)
    base["pred_tot"] = base.pred_ppg * base.share * 82
    base["act_tot"] = base.act_ppg * base.act_share * 82
    return base

def metrics(frames):
    res = []
    for T, b in frames.items():
        q = b[b.act_gp >= 20]
        top = b.sort_values("pred_tot", ascending=False).head(300)
        top150 = top.head(150)
        res.append(dict(T=T, ppg_mae=np.average((q.pred_ppg - q.act_ppg).abs(), weights=q.act_gp),
                        tot_mae300=(top.pred_tot - top.act_tot).abs().mean(),
                        rho300=spearmanr(top.pred_tot, top.act_tot).statistic,
                        rho150=spearmanr(top150.pred_tot, top150.act_tot).statistic,
                        share_mae=(top.share - top.act_share).abs().mean()))
    return pd.DataFrame(res)

def v1_proj(df, T, p=V1):
    o = v1(df, T, p).set_index("playerId")
    for c in CATS:
        o["rate_" + c] = o["v1_" + c]
    o["share"] = o.v1_avail
    return o

def naive_proj(df, T):
    last = df[df.season == T - 1].set_index("playerId")
    o = pd.DataFrame(index=last.index)
    o["pg"] = last.pg; o["gp_last"] = last.gp
    for c in CATS:
        o["rate_" + c] = last[c] / last.gp
    o["share"] = last.share
    return o

if __name__ == "__main__":
    df = load()
    Ts = list(range(2016, 2027))
    for name, fn in [("naive", naive_proj), ("v1", v1_proj)]:
        m = metrics({T: eval_frame(df, T, fn(df, T)) for T in Ts})
        print(name); print(m.round(3).to_string(index=False)); print("mean", m.drop(columns="T").mean().round(3).to_dict())
        ex = m[~m.T.isin([2020, 2021])]; print("mean excl 2020/21", ex.drop(columns="T").mean().round(3).to_dict())
