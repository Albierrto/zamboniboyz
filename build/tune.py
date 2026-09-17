import copy, sys, numpy as np
sys.path.insert(0, "build")
import model as M, backtest as B
p = copy.deepcopy(M.P)
def score(p):
    r = B.evaluate(p)
    return r
def obj(r): return r.mae_ppg
def obj_tot(r): return r.mae_tot300 / 60 - r.rho300
best = score(p); print("start", best.round(4).to_dict())
grid = {
 "decay": [0.35, 0.5, 0.6, 0.75, 0.9],
 "k_sh": [100, 200, 300, 500, 800],
 "prior_q": [0.15, 0.25, 0.35, 0.5],
 "age_scale": [0, 0.5, 1.0, 1.5, 2.0],
}
kscale = [0.25, 0.5, 1, 2, 4]
for rnd in range(2):
    for key, vals in grid.items():
        res = []
        for v in vals:
            q = copy.deepcopy(p); q[key] = v; res.append((obj(score(q)), v))
        res.sort(); p[key] = res[0][1]; print(rnd, key, [(round(a, 4), b) for a, b in sorted(res, key=lambda x: x[1])])
    for c in list(p["k_rate"]):
        res = []
        base = M.P["k_rate"][c]
        for m in kscale:
            q = copy.deepcopy(p); q["k_rate"][c] = base * m; res.append((obj(score(q)), base * m))
        res.sort(); p["k_rate"][c] = res[0][1]; print(rnd, "k_" + c, [(round(a, 4), b) for a, b in sorted(res, key=lambda x: x[1])])
# availability params on total-points objective
for key, vals in {"k_gp": [0.3, 0.6, 1.2, 2.5, 5], "prior_avail": [0.6, 0.7, 0.8, 0.9]}.items():
    res = []
    for v in vals:
        q = copy.deepcopy(p); q[key] = v; r = score(q); res.append((obj_tot(r), v, round(r.rho300, 4), round(r.mae_tot300, 2)))
    res.sort(); p[key] = res[0][1]; print(key, sorted(res, key=lambda x: x[1]))
print("FINAL", p); print(score(p).round(4).to_dict())
B.evaluate(p, verbose=True)
