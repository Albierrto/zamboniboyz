import numpy as np, pandas as pd, sys, time
sys.path.insert(0, "build")
import lab as L
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

RATE_COLS = ["g", "a", "a1", "shots", "hit", "blk", "fow", "pim", "pm", "ppPoints"]

def features(df, T):
    o = L.v1(df, T).set_index("playerId")
    hist = df[(df.season < T) & (df.season >= T - 3)]
    for lag in (1, 2, 3):
        h = hist[hist.season == T - lag].set_index("playerId")
        f = pd.DataFrame(index=h.index)
        f["gp"] = h.gp; f["share"] = h.share
        for c in RATE_COLS:
            f[c] = h[c] / h.gp
        if lag <= 2:
            f["toi"] = h.toi; f["pptoi"] = h.pptoi; f["shtoi"] = h.shtoi
            f["ipp"] = (h.g + h.a) / h.oigf.replace(0, np.nan)
            f["oish"] = h.oish; f["cf"] = h.cf; f["ozs"] = h.ozs
            f["shp"] = h.g / h.shots.replace(0, np.nan)
            f["a1s"] = h.a1 / h.a.replace(0, np.nan)
        f.columns = [f"{c}_L{lag}" for c in f.columns]
        o = o.join(f)
    car = df[df.season < T].groupby("playerId").agg(car_gp=("gp", "sum"), car_seasons=("season", "nunique"))
    o = o.join(car)
    last = hist.sort_values("season").groupby("playerId").tail(1).set_index("playerId")
    o["height"] = last.height; o["weight"] = last.weight; o["draft"] = last.draftOverall
    o["is_C"] = (o.pg == "C").astype(int); o["is_D"] = (o.pg == "D").astype(int)
    tgt = df[df.season == T].set_index("playerId")
    o["team_T"] = tgt.teams.str.split(",").str[0].str.strip().reindex(o.index)
    o["team_last"] = last.teams.str.split(",").str[-1].str.strip()
    o["moved"] = np.where(o.team_T.isna(), np.nan, (o.team_T != o.team_last).astype(float))
    o["T"] = T
    return o

FEATS = None

def build_all(df, Ts):
    frames = {}
    for T in Ts:
        frames[T] = features(df, T)
    return frames

def target_cols(df, T, o):
    t = df[df.season == T].set_index("playerId")
    y = pd.DataFrame(index=o.index)
    y["gp"] = t.gp.reindex(o.index)
    for c in L.CATS:
        y[c] = (t[c] / t.gp).reindex(o.index)
    y["share"] = t.share.reindex(o.index)
    nxt = set(df[df.season == T + 1].playerId) if (T + 1) in set(df.season) else set()
    absent = y.gp.isna()
    y.loc[absent & o.index.isin(nxt), "share"] = 0.0
    return y

def feat_list(o):
    drop = {"name", "npos", "pg", "birthDate", "teams", "last_season", "team_T", "team_last", "T",
            "w_shots", "w_g", "w_a", "w_pm", "w_pim", "w_hit", "w_blk", "w_fow", "w_gp", "w_share", "w", "car_g", "car_shots"}
    return [c for c in o.columns if c not in drop and o[c].dtype != object]

def gbm(**kw):
    p = dict(max_iter=250, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0)
    p.update(kw)
    return HistGradientBoostingRegressor(**p)

def ridge(alpha=10):
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=alpha))

def run(df, frames, Ts_test, model="gbm", resid=True, share_model="gbm", min_train=4, verbose=False):
    ys = {T: target_cols(df, T, frames[T]) for T in frames}
    out = {}
    for T in Ts_test:
        train_T = [t for t in frames if t < T]
        if len(train_T) < min_train: continue
        Xtr = pd.concat([frames[t] for t in train_T]); Ytr = pd.concat([ys[t] for t in train_T])
        Xtr = Xtr[Xtr.gp_last >= 1]; Ytr = Ytr.loc[Xtr.index] if False else pd.concat([ys[t].loc[frames[t][frames[t].gp_last >= 1].index] for t in train_T])
        Xte = frames[T][frames[T].gp_last >= 1].copy()
        F = feat_list(Xte)
        proj = Xte.copy()
        for c in L.CATS:
            m = Ytr.gp.fillna(0) >= 10
            X = Xtr.loc[m.values, F] if False else Xtr[F][m.values]
            yv = Ytr[c][m.values]
            base_tr = Xtr["v1_" + c][m.values]
            w = Ytr.gp[m.values]
            mdl = gbm() if model == "gbm" else ridge()
            if model == "ridge":
                X = X.replace([np.inf, -np.inf], np.nan)
            mdl.fit(X, (yv - base_tr) if resid else yv, **({"sample_weight": w} if model == "gbm" else {"ridge__sample_weight": w}))
            Xp = Xte[F].replace([np.inf, -np.inf], np.nan)
            pred = mdl.predict(Xp)
            proj["rate_" + c] = (Xte["v1_" + c] + pred) if resid else pred
            proj["rate_" + c] = proj["rate_" + c].clip(lower=-1 if c == "pm" else 0)
        # games share
        ms = Ytr.share.notna().values
        if share_model == "v1":
            proj["share"] = Xte.v1_avail
        else:
            mdl = gbm(loss="squared_error") if share_model == "gbm" else ridge()
            X = Xtr[F][ms].replace([np.inf, -np.inf], np.nan)
            yv = Ytr.share[ms]; base = Xtr.v1_avail[ms]
            mdl.fit(X, yv - base)
            proj["share"] = (Xte.v1_avail + mdl.predict(Xte[F].replace([np.inf, -np.inf], np.nan))).clip(0, 1)
        out[T] = L.eval_frame(df, T, proj)
    return out

if __name__ == "__main__":
    t0 = time.time()
    df = L.load()
    frames = build_all(df, range(2014, 2027))
    pd.to_pickle(frames, "data/lab_frames.pkl")
    print("features built", round(time.time() - t0), "s")
    Ts = list(range(2018, 2027))
    base = L.metrics({T: L.eval_frame(df, T, L.v1_proj(df, T)) for T in Ts})
    print("v1   ", base.drop(columns="T").mean().round(3).to_dict())
    for model, resid, sm in [("gbm", True, "v1"), ("gbm", True, "gbm"), ("ridge", True, "ridge"), ("gbm", False, "gbm")]:
        res = L.metrics(run(df, frames, Ts, model, resid, sm))
        print(model, "resid" if resid else "raw", sm, res.drop(columns="T").mean().round(3).to_dict())
