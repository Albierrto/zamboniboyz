import copy, sys, numpy as np, pandas as pd
sys.path.insert(0, "build")
import lab as L
df = L.load()
Ts = list(range(2014, 2027))
def score(p):
    m = L.metrics({T: L.eval_frame(df, T, L.v1_proj(df, T, p)) for T in Ts})
    return m.drop(columns="T").mean()
p = copy.deepcopy(L.V1)
best = score(p); print("start", best.round(4).to_dict(), flush=True)
grid = {"decay": [0.4, 0.5, 0.6, 0.7, 0.8], "k_sh": [100, 200, 300, 500], "prior_q": [0.35, 0.5, 0.6], "age_scale": [1.0, 1.5, 2.0, 2.5]}
for rnd in range(2):
    for key, vals in grid.items():
        res = []
        for v in vals:
            q = copy.deepcopy(p); q[key] = v; res.append((score(q).ppg_mae, v))
        p[key] = min(res)[1]; print(rnd, key, [(round(a, 4), b) for a, b in res], "->", p[key], flush=True)
    for c in list(p["k_rate"]):
        res = []; base = L.V1["k_rate"][c]
        for m in [0.25, 0.5, 1, 2, 4]:
            q = copy.deepcopy(p); q["k_rate"][c] = base * m; res.append((score(q).ppg_mae, base * m))
        p["k_rate"][c] = min(res)[1]; print(rnd, "k_" + c, "->", p["k_rate"][c], flush=True)
for key, vals in {"k_gp": [0.1, 0.3, 0.6, 1.2], "prior_avail": [0.7, 0.8, 0.9]}.items():
    res = []
    for v in vals:
        q = copy.deepcopy(p); q[key] = v; s = score(q); res.append((s.tot_mae300 / 55 - s.rho300, v))
    p[key] = min(res)[1]; print(key, "->", p[key], flush=True)
print("FINAL", p); print(score(p).round(4).to_dict())
