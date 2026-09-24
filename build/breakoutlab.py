"""Preseason breakout model: which waiver-level skaters become real fantasy starters?
Pool: projected below this league's waiver level at his position (and projected 40+ pts, so real NHLers).
Breakout: finishes at or above waiver level. Tested leave-one-season-out on 2017-18..2025-26."""
import numpy as np, pandas as pd, sys
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss
REPL = {"C": 272.0, "W": 180.1, "D": 158.7}

def frame():
    sk = pd.read_pickle("data/lab_v2_frames.pkl")
    X = pd.concat([d.assign(season=T, pid=d.index) for T, d in sk.items()])
    X["repl"] = X.pg.map(REPL)
    X["gap"] = (X.repl - X.pred_tot) / X.repl          # how far below waiver level (share)
    X["pool"] = (X.pred_tot < X.repl) & (X.pred_tot >= 40) & (X.gp_last >= 1)
    X["y"] = (X.act_tot >= X.repl).astype(int)
    add_feats(X)
    return X

def add_feats(X):
    g = lambda c: X[c] if c in X else np.nan
    X["pts60_L1"] = (X.g_L1 + X.a_L1) / (X.toi_L1 * X.gp_L1).replace(0, np.nan) * 60
    X["sog60_L1"] = X.shots_L1 / (X.toi_L1 * X.gp_L1).replace(0, np.nan) * 60
    X["toi_tr"] = X.toi_L1 - X.toi_L2
    X["pptoi_tr"] = X.pptoi_L1 - X.pptoi_L2
    X["sh_luck"] = X.shp_L1 - X.car_g / X.car_shots.replace(0, np.nan)
    X["ppg_pred"] = X.pred_ppg
    X["gp_share_last"] = X.share_L1
    X["young"] = (X.age <= 23).astype(int)
    X["draft_r"] = np.log1p(X.draft.fillna(250))
    X["is_D"] = (X.pg == "D").astype(int); X["is_C"] = (X.pg == "C").astype(int)
    return X

FEATS = ["gap", "age", "car_gp", "gp_last", "toi_L1", "toi_tr", "pptoi_L1", "pptoi_tr", "pts60_L1", "sog60_L1",
         "sh_luck", "ipp_L1", "oish_L1", "cf_L1", "ozs_L1", "draft_r", "height", "moved", "is_D", "is_C", "ppg_pred"]

def models():
    return {
        "logit": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)),
        "gbm": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=40, l2_regularization=1.0),
    }

def prep(D, med=None):
    Z = D[FEATS].astype(float).copy()
    med = Z.median() if med is None else med
    return Z.fillna(med), med

if __name__ == "__main__":
    X = frame(); P = X[X.pool].copy()
    print("pool", len(P), "breakout rate", round(P.y.mean(), 3), P.groupby("season").y.mean().round(3).to_dict())
    res = {}
    for name, mk in models().items():
        preds = pd.Series(np.nan, index=range(len(P)))
        P = P.reset_index(drop=True)
        for T in sorted(P.season.unique()):
            tr, te = P[P.season != T], P[P.season == T]
            Ztr, med = prep(tr); Zte, _ = prep(te, med)
            m = mk(); m.fit(Ztr, tr.y)
            preds[te.index] = m.predict_proba(Zte)[:, 1]
        P["p_" + name] = preds.values
        auc = roc_auc_score(P.y, preds); br = brier_score_loss(P.y, preds)
        # precision among the top 30 per season
        top = P.sort_values("p_" + name, ascending=False).groupby("season").head(30)
        res[name] = (auc, br, top.y.mean())
        print(f"{name}: AUC {auc:.3f}  Brier {br:.4f}  hit rate of top-30 per season {top.y.mean():.3f}  (base {P.y.mean():.3f})")
    # simple baselines
    for nm, s in [("closest to waiver level", -P.gap), ("youngest", -P.age), ("projection only (ppg)", P.ppg_pred)]:
        top = P.assign(s=s).sort_values("s", ascending=False).groupby("season").head(30)
        print(f"baseline {nm}: AUC {roc_auc_score(P.y, s):.3f}  top-30 hit {top.y.mean():.3f}")
    # calibration by decile (gbm/logit)
    best = max(res, key=lambda k: res[k][0])
    P["dec"] = pd.qcut(P["p_" + best], 10, labels=False, duplicates="drop")
    print(best, "calibration:", P.groupby("dec").agg(p=("p_" + best, "mean"), y=("y", "mean"), n=("y", "size")).round(3).to_string())
    P.to_pickle("data/breakout_oos.pkl")
