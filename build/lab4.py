import numpy as np, pandas as pd, sys
sys.path.insert(0, "build")
import lab as L, lab2 as L2
from sklearn.ensemble import HistGradientBoostingRegressor
df = L.load(); frames = pd.read_pickle("data/lab_frames.pkl")
Ts = list(range(2018, 2027))
base = L.metrics({T: L.eval_frame(df, T, L.v1_proj(df, T)) for T in Ts}).set_index("T")
CFG = [dict(max_iter=150, learning_rate=0.03, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0, random_state=1),
       dict(max_iter=300, learning_rate=0.03, max_leaf_nodes=7, min_samples_leaf=40, l2_regularization=1.0, random_state=2),
       dict(max_iter=250, learning_rate=0.02, max_leaf_nodes=15, min_samples_leaf=60, l2_regularization=2.0, random_state=3)]
class Ens:
    def __init__(self, **kw): self.ms = [HistGradientBoostingRegressor(**{**c, **kw}) for c in CFG]
    def fit(self, X, y, sample_weight=None):
        for m in self.ms: m.fit(X, y, sample_weight=sample_weight)
        return self
    def predict(self, X): return np.mean([m.predict(X) for m in self.ms], axis=0)
L2.gbm = lambda **kw: Ens(**{k: v for k, v in kw.items() if k != "loss"})
fr = L2.run(df, frames, Ts, "gbm", True, "gbm")
m = L.metrics(fr).set_index("T")
print("ensemble", m.mean().round(3).to_dict())
print((m - base).round(3).to_string())
pd.to_pickle(fr, "data/lab_v2_frames.pkl")
# calibration of v2 totals by position (top-N per season)
rows = []
for T, b in fr.items():
    b = b.copy(); b["T"] = T; rows.append(b)
d = pd.concat(rows)
for p, n in [("C", 60), ("W", 120), ("D", 120)]:
    x = d[d.pg == p].sort_values(["T", "pred_tot"], ascending=[True, False]).groupby("T").head(n)
    bb, aa = np.polyfit(x.pred_tot, x.act_tot, 1)
    print(p, "slope", round(bb, 2), "int", round(aa, 1), "corr", round(np.corrcoef(x.pred_tot, x.act_tot)[0, 1], 3), "mean pred/act", round(x.pred_tot.mean()), round(x.act_tot.mean()))
