import numpy as np, pandas as pd, sys, re, unicodedata
from scipy.stats import spearmanr
sys.path.insert(0, "build")
import glab2 as G2, glab as GL
def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", " ").replace(".", ""))
    s = re.sub(r"\s+", " ", s).strip()
    fix = {"gabe vilardi": "gabriel vilardi", "matty beniers": "matthew beniers", "jj peterka": "john jason peterka",
           "alexander ovechkin": "alex ovechkin", "mitch marner": "mitchell marner", "tim stutzle": "tim stutzle",
           "zach werenski": "zach werenski", "pheonix copley": "pheonix copley", "sam montembeault": "samuel montembeault",
           "cam york": "cameron york", "alexandar georgiev": "alexandar georgiev", "tj oshie": "tj oshie"}
    return fix.get(s, s)
def market(T):
    rows = [l.split("|") for l in open(f"data/raw/market/thescore_{T}.txt").read().strip().splitlines()]
    return {norm(n): int(r) for r, n, p in rows}

sk = pd.read_pickle("data/lab_v2_frames.pkl")
gf = pd.read_pickle("data/glab_frames.pkl")
gres = G2.run(gf, [2024, 2025, 2026], "ridge", "ridge", 30)

def blend_eval(d, rank, w_list, grp_col, n_eval):
    d = d.copy()
    d["k"] = d.name.map(norm)
    d["mrank"] = d.k.map(rank)
    out = {}
    matched = d.mrank.notna().sum()
    for w in w_list:
        d["blend"] = np.nan
        for g, x in d.groupby(grp_col):
            ours = np.sort(x.pred_tot.values)[::-1]
            order = list(x[x.mrank.notna()].sort_values("mrank").index) + list(x[x.mrank.isna()].sort_values("pred_tot", ascending=False).index)
            imp = pd.Series(ours[:len(order)], index=order)
            d.loc[x.index, "blend"] = w * x.pred_tot + (1 - w) * imp.reindex(x.index)
        top = d.sort_values("blend", ascending=False).head(n_eval)
        out[w] = dict(rho=spearmanr(top.blend, top.act_tot if "act_tot" in d else top.tot).statistic,
                      mae=(top.blend - (top.act_tot if "act_tot" in d else top.tot)).abs().mean())
    return out, matched

W = [0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
print("SKATERS (top 250 by blended number)")
agg = {w: [] for w in W}
for T in (2024, 2025, 2026):
    d = sk[T][sk[T].gp_last >= 1].copy()
    r, n = blend_eval(d, market(T), W, "pg", 250)
    print(T, "matched", n, {w: (round(v["rho"], 3), round(v["mae"], 1)) for w, v in r.items()})
    for w in W: agg[w].append((r[w]["rho"], r[w]["mae"]))
print("mean", {w: (round(np.mean([a for a, b in v]), 3), round(np.mean([b for a, b in v]), 1)) for w, v in agg.items()})
print("GOALIES (top 40)")
agg = {w: [] for w in W}
for T in (2024, 2025, 2026):
    d = gres[T].copy(); d["grp"] = "G"
    r, n = blend_eval(d, market(T), W, "grp", 40)
    print(T, "matched", n, {w: (round(v["rho"], 3), round(v["mae"], 1)) for w, v in r.items()})
    for w in W: agg[w].append((r[w]["rho"], r[w]["mae"]))
print("mean", {w: (round(np.mean([a for a, b in v]), 3), round(np.mean([b for a, b in v]), 1)) for w, v in agg.items()})
