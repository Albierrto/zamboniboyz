"""How much should analyst rankings move our numbers? Out-of-sample test on 2022-23..2025-26.
Model predictions are the v2 out-of-sample ones (lab_v2_frames / glab2). Expert lists: data/raw/experts/hist + theScore."""
import numpy as np, pandas as pd, sys, re, unicodedata, glob, os
from scipy.stats import spearmanr
sys.path.insert(0, "build")
import glab2 as G2

FIX = {"gabe vilardi": "gabriel vilardi", "matty beniers": "matthew beniers", "jj peterka": "john jason peterka",
       "j j peterka": "john jason peterka", "alexander ovechkin": "alex ovechkin", "mitch marner": "mitchell marner",
       "sam montembeault": "samuel montembeault", "cam york": "cameron york", "arturri lehkonen": "artturi lehkonen",
       "alexandre texier": "alexandre texier", "zach hyman": "zach hyman", "josh morrissey": "josh morrissey",
       "nicholas paul": "nick paul", "mathew barzal": "mathew barzal", "matt boldy": "matt boldy",
       "cal petersen": "calvin petersen", "alex kerfoot": "alexander kerfoot", "vitek vanecek": "vitek vanecek",
       "danil yurov": "danila yurov", "alex nylander": "alexander nylander", "jake middleton": "jacob middleton",
       "zachary werenski": "zach werenski", "jonathan marchessault": "jonathan marchessault",
       "tim stutzle": "tim stutzle", "matthew boldy": "matt boldy", "nikolai kovalenko": "nikolai kovalenko",
       "evgeni malkin": "evgeni malkin", "mike matheson": "michael matheson", "nick suzuki": "nick suzuki",
       "joshua norris": "josh norris", "janis moser": "j j moser", "jj moser": "j j moser",
       "pierreolivier joseph": "pierre olivier joseph", "ukkopekka luukkonen": "ukko pekka luukkonen",
       "juusepekka kukkonen": "juuse pekka kukkonen"}
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = s.replace("-", " ").replace(".", " ").replace("'", "")
    s = re.sub(r"[^a-z ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return FIX.get(s, s)

def load_list(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split("|")
        if len(parts) < 2 or not parts[0].strip().isdigit(): continue
        k = norm(parts[1])
        if k and k not in out: out[k] = int(parts[0])
    return out

def sources_for(T):
    S = {}
    for f in sorted(glob.glob(f"data/raw/experts/hist/*_{T}.txt")):
        S[os.path.basename(f).rsplit("_", 1)[0]] = load_list(f)
    ts = f"data/raw/market/thescore_{T}.txt"
    if os.path.exists(ts): S["thescore"] = load_list(ts)
    return S

def consensus(keys, S, min_n=150, skip=()):
    """Mean log-rank across lists; unranked in a list counts as 1.3x that list's length."""
    use = {k: v for k, v in S.items() if len(v) >= min_n and k not in skip}
    if not use: return pd.Series(np.nan, index=keys.index), 0
    cols = []
    for name, L in use.items():
        n = max(L.values())
        cols.append(keys.map(lambda k: np.log(L.get(k, 1.3 * n))))
    M = pd.concat(cols, axis=1)
    anyin = pd.concat([keys.map(lambda k: k in L) for L in use.values()], axis=1).any(axis=1)
    sc = M.mean(axis=1).where(anyin)
    return sc, len(use)

def implied(d, score, grp):
    """Map an ordering (lower score = better) onto our own points scale within each position group."""
    imp = pd.Series(np.nan, index=d.index)
    for g, x in d.groupby(grp):
        ours = np.sort(x.pred_tot.values)[::-1]
        ranked = x[score.loc[x.index].notna()].index
        order = list(score.loc[ranked].sort_values().index) + list(x.drop(ranked).sort_values("pred_tot", ascending=False).index)
        imp.loc[order] = ours[:len(order)]
    return imp

def ev(d, col, n_top=250, fixed=None):
    sub = d.loc[fixed] if fixed is not None else d.sort_values(col, ascending=False).head(n_top)
    return spearmanr(sub[col], sub.act_tot).statistic, (sub[col] - sub.act_tot).abs().mean()

if __name__ == "__main__":
    sk = pd.read_pickle("data/lab_v2_frames.pkl")
    W = [1.0, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.0]
    res = []
    for T in (2023, 2024, 2025, 2026):
        d = sk[T][sk[T].gp_last >= 1].copy(); d["k"] = d.name.map(norm)
        S = sources_for(T)
        # fixed evaluation pool: our top 250 plus anyone in any 150+ list
        cs, nsrc = consensus(d.k, S)
        pool = set(d.sort_values("pred_tot", ascending=False).head(250).index) | set(cs.dropna().index)
        pool = list(pool)
        line = {"T": T, "n_src": nsrc, "pool": len(pool), "matched": int(cs.notna().sum())}
        for name, L in S.items():
            if len(L) < 150: continue
            s1 = d.k.map(lambda k: np.log(L[k]) if k in L else np.nan)
            d["imp_" + name] = implied(d, s1, "pg")
            line[name] = ev(d, "imp_" + name, fixed=pool)
        d["imp_cons"] = implied(d, cs, "pg")
        for w in W:
            d["b"] = w * d.pred_tot + (1 - w) * d.imp_cons
            line[f"w{w}"] = ev(d, "b", fixed=pool)
            line[f"t{w}"] = ev(d, "b", n_top=250)
        res.append(line)
        print(T, {k: (tuple(round(x, 3) for x in v) if isinstance(v, tuple) else v) for k, v in line.items()})
    print("\nMEAN over seasons (fixed pool): rho, MAE")
    for w in W:
        print(f"  model weight {w}: rho {np.mean([r[f'w{w}'][0] for r in res]):.3f}  mae {np.mean([r[f'w{w}'][1] for r in res]):.1f}"
              f"   | top250-by-blend rho {np.mean([r[f't{w}'][0] for r in res]):.3f} mae {np.mean([r[f't{w}'][1] for r in res]):.1f}")
