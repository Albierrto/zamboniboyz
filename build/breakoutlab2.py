"""Breakout, redefined (Sep 2026): a real jump, not just finishing near the line.

Old target: a skater projected below waiver level finishes at or above it. Players projected just under the line
(often 30+ vets) got 40-60% "breakout" chances just for being close, which isn't what breakout means.
New target: he beats his own projection by 30% or more AND finishes at or above waiver level (worth rostering).
Pool: projected 40+ points and below 1.2x waiver level (fringe players and free agents), played last season.
Tested leave-one-season-out on 2017-18..2025-26, same features as before."""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "build")
from breakoutlab import add_feats, FEATS, REPL, models, prep
from sklearn.metrics import roc_auc_score, brier_score_loss
JUMP = 1.30

def frame():
    sk = pd.read_pickle("data/lab_v2_frames.pkl")
    X = pd.concat([d.assign(season=T, pid=d.index) for T, d in sk.items()])
    X["repl"] = X.pg.map(REPL)
    X["gap"] = (X.repl - X.pred_tot) / X.repl
    X["pool"] = (X.pred_tot < 1.2 * X.repl) & (X.pred_tot >= 40) & (X.gp_last >= 1)
    X["y"] = ((X.act_tot >= X.repl) & (X.act_tot >= JUMP * X.pred_tot)).astype(int)
    X["y_old"] = (X.act_tot >= X.repl).astype(int)
    add_feats(X)
    return X

if __name__ == "__main__":
    X = frame(); P = X[X.pool].reset_index(drop=True)
    print("pool", len(P), "new breakout rate", round(P.y.mean(), 3), "| old-definition rate in same pool", round(P.y_old.mean(), 3))
    for name, mk in models().items():
        preds = np.zeros(len(P))
        for T in sorted(P.season.unique()):
            tr, te = P[P.season != T], P[P.season == T]
            Ztr, med = prep(tr); Zte, _ = prep(te, med)
            m = mk(); m.fit(Ztr, tr.y); preds[te.index] = m.predict_proba(Zte)[:, 1]
        P["p_" + name] = preds
        top = P.sort_values("p_" + name, ascending=False).groupby("season").head(30)
        print(f"{name}: AUC {roc_auc_score(P.y, preds):.3f} Brier {brier_score_loss(P.y, preds):.4f} top-30 hit {top.y.mean():.3f} (base {P.y.mean():.3f})")
    for nm, s in [("closest to waiver level", -P.gap), ("youngest", -P.age), ("projection only", P.ppg_pred)]:
        top = P.assign(s=s).sort_values("s", ascending=False).groupby("season").head(30)
        print(f"baseline {nm}: AUC {roc_auc_score(P.y, s):.3f} top-30 hit {top.y.mean():.3f}")
    P["ab"] = pd.cut(P.age, [0, 22, 24, 26, 28, 30, 32, 50])
    print("rate and mean prediction by age:\n", P.groupby("ab", observed=True).agg(n=("y", "size"), actual=("y", "mean"), pred=("p_logit", "mean")).round(3).to_string())
    P["dec"] = pd.qcut(P.p_logit, 10, labels=False, duplicates="drop")
    print("calibration (logit):\n", P.groupby("dec").agg(p=("p_logit", "mean"), y=("y", "mean"), n=("y", "size")).round(3).to_string())
    up = P[P.y == 1]; print("mean extra points in a breakout season:", round(float((up.act_tot - up.pred_tot).mean())))
    P.to_pickle("data/breakout2_oos.pkl")
