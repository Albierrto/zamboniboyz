import numpy as np, pandas as pd, sys
sys.path.insert(0, "build")
import lab as L, lab2 as L2
df = L.load(); frames = pd.read_pickle("data/lab_frames.pkl")
Ts = list(range(2018, 2027))
base = L.metrics({T: L.eval_frame(df, T, L.v1_proj(df, T)) for T in Ts}).set_index("T")
def show(name, fr):
    m = L.metrics(fr).set_index("T")
    d = m - base
    wins = {k: int((d[k] < 0).sum()) if k in ("ppg_mae", "tot_mae300", "share_mae") else int((d[k] > 0).sum()) for k in d.columns}
    print(f"{name:28}", m.mean().round(3).to_dict(), "wins/9:", wins)
    return m
show("gbm resid+share", L2.run(df, frames, Ts, "gbm", True, "gbm"))
orig = L2.gbm
for kw in [dict(max_iter=150, learning_rate=0.03), dict(max_iter=400, learning_rate=0.02, min_samples_leaf=80), dict(max_leaf_nodes=7, max_iter=300), dict(l2_regularization=5.0, min_samples_leaf=100, max_iter=300)]:
    L2.gbm = lambda _kw=kw, **k: orig(**{**_kw, **k})
    show("gbm " + str(kw), L2.run(df, frames, Ts, "gbm", True, "gbm"))
L2.gbm = orig
