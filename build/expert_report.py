"""Numbers for the How-it-works table: analysts vs our model vs the blend used on the site (4 past seasons)."""
import json, sys
sys.path.insert(0, "build")
from expertlab import *
import glab2 as G2

def w_skater(x):
    ysm = (x.age <= 23) | (x.gp_last < 50) | (x.moved == 1)
    return np.where(ysm, 0.35, np.where(x.pg == "C", 0.05, 0.2))

sk = pd.read_pickle("data/lab_v2_frames.pkl")
R = {k: [] for k in ["model", "cons", "blend", "single"]}
for T in (2023, 2024, 2025, 2026):
    d = sk[T][sk[T].gp_last >= 1].copy(); d["k"] = d.name.map(norm)
    S = sources_for(T); cs, n = consensus(d.k, S)
    d["imp"] = implied(d, cs, "pg")
    pool = list(set(d.sort_values("pred_tot", ascending=False).head(250).index) | set(cs.dropna().index))
    x = d.loc[pool]
    R["model"].append(ev(x, "pred_tot", fixed=x.index))
    R["cons"].append(ev(x, "imp", fixed=x.index))
    x = x.assign(b=x.pred_tot + w_skater(x) * (x.imp - x.pred_tot))
    R["blend"].append(ev(x, "b", fixed=x.index))
    singles = []
    for name, L in S.items():
        if len(L) < 150: continue
        s1 = d.k.map(lambda k: np.log(L[k]) if k in L else np.nan)
        d["i1"] = implied(d, s1, "pg")
        singles.append(ev(d.loc[pool], "i1", fixed=pool))
    R["single"].append((np.mean([s[0] for s in singles]), np.mean([s[1] for s in singles])))
out = {k: dict(rho=round(float(np.mean([a for a, b in v])), 3), mae=round(float(np.mean([b for a, b in v])), 1)) for k, v in R.items()}
# goalies
gf = pd.read_pickle("data/glab_frames.pkl")
gres = G2.run(gf, [2023, 2024, 2025, 2026], "ridge", "ridge", 30)
GR = {k: [] for k in ["model", "cons", "blend"]}
for T in (2023, 2024, 2025, 2026):
    d = gres[T].copy(); d["act_tot"] = d["tot"]; d["k"] = d.name.map(norm); d["grp"] = "G"
    cs, n = consensus(d.k, sources_for(T)); d["imp"] = implied(d, cs, "grp")
    pool = list(set(d.sort_values("pred_tot", ascending=False).head(45).index) | set(cs.dropna().index))
    x = d.loc[pool].assign(b=lambda z: 0.35 * z.pred_tot + 0.65 * z.imp)
    for k, c in [("model", "pred_tot"), ("cons", "imp"), ("blend", "b")]: GR[k].append(ev(x, c, fixed=x.index))
out["goalies"] = {k: dict(rho=round(float(np.mean([a for a, b in v])), 3), mae=round(float(np.mean([b for a, b in v])), 1)) for k, v in GR.items()}
json.dump(out, open("data/expert_report.json", "w"), indent=1)
print(json.dumps(out, indent=1))
