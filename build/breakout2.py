"""Breakout chances for 2026-27, new definition (build/breakoutlab2.py): he beats his own projection by 30%+ AND
finishes at or above waiver level. Model: gradient-boosted trees on the same features (best out of sample),
stacked with the analysts' view (2022-23..2025-26), plus a projection-only baseline for "typical for his projection".
Also re-fits the in-season update: logit(p) += chg * ln(projection multiplier) * n/(n+5).
Writes data/breakout_2027.json (same format the export reads) and data/breakout2_meta.json."""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "build")
from breakoutlab import add_feats, FEATS, REPL
from breakoutlab2 import frame, JUMP
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss
import lab as L, lab2 as L2, expertlab as EL

gbm = lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=40, l2_regularization=1.0)
logit = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=3000))
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))

X = frame(); P = X[X.pool].reset_index(drop=True)
Z = P[FEATS].astype(float)
oos = np.zeros(len(P))
for T in sorted(P.season.unique()):
    tr, te = P.season != T, P.season == T
    med = Z[tr].median(); m = gbm().fit(Z[tr].fillna(med), P.y[tr]); oos[te.values] = m.predict_proba(Z[te].fillna(med))[:, 1]
P["pA"] = oos
# analysts' view, 2023-2026
rows = []
for T in (2023, 2024, 2025, 2026):
    d = X[X.season == T].copy(); d["k"] = d.name.map(EL.norm)
    cs, n = EL.consensus(d.k, EL.sources_for(T)); imp = EL.implied(d, cs, "pg")
    rows.append(pd.DataFrame({"season": T, "pid": d.index, "exp_gap": ((imp - d.pred_tot) / d.repl).values, "exp_in": cs.notna().astype(int).values}))
E = pd.concat(rows)
P["pid"] = X[X.pool].index.values
S = P[P.season >= 2023].merge(E, on=["season", "pid"], how="left")
Zs = lambda D: np.column_stack([lg(D.pA), D.exp_gap.clip(-1, 1).fillna(0), D.exp_in.fillna(0)])
# out-of-sample check of the stack (leave one of the four seasons out)
st_oos = np.zeros(len(S))
for T in sorted(S.season.unique()):
    tr, te = S.season != T, S.season == T
    st_oos[te.values] = LogisticRegression(C=1.0, max_iter=2000).fit(Zs(S[tr]), S.y[tr]).predict_proba(Zs(S[te]))[:, 1]
stack = LogisticRegression(C=1.0, max_iter=2000).fit(Zs(S), S.y)
# The stack is overconfident at the top: out of sample, players it put above 30% broke out about 25% of the time,
# no better than the 22-25% band. So its chance is recalibrated on its own out-of-sample predictions with a bend at
# 22%: y ~ a + b*logit(p) + c*max(0, logit(p) - logit(.22)). In practice nobody is better than about 1 in 4 before
# the season starts; the in-season update is what separates them.
KNEE = lg(0.22)
Xc = lambda p: np.column_stack([lg(np.asarray(p)), np.maximum(0, lg(np.asarray(p)) - KNEE)])
cal = LogisticRegression(C=100.0, max_iter=3000).fit(Xc(st_oos), S.y)
# keep it rising a little above the bend (a quarter of the slope below it) so the order of the best bets is kept
cal.coef_[0][1] = max(cal.coef_[0][1], -0.75 * cal.coef_[0][0])
calp = lambda p: cal.predict_proba(Xc(p))[:, 1]
print("recalibration:", cal.intercept_.round(3), cal.coef_.round(3))
auc_A = roc_auc_score(P.y, P.pA); top_A = P.sort_values("pA", ascending=False).groupby("season").head(30).y.mean()
auc_S = roc_auc_score(S.y, st_oos); auc_SA = roc_auc_score(S.y, S.pA)
top_S = S.assign(s=st_oos).sort_values("s", ascending=False).groupby("season").head(30).y.mean()
print(f"model A (9 seasons): AUC {auc_A:.3f}, top-30 hit {top_A:.3f}, base {P.y.mean():.3f}")
print(f"2023-26: A alone AUC {auc_SA:.3f} | with analysts AUC {auc_S:.3f}, top-30 hit {top_S:.3f}")
S["st"] = st_oos; S["dq"] = pd.qcut(S.st, 5, labels=False, duplicates="drop")
S["sc"] = calp(st_oos); S["dc"] = pd.qcut(S.sc, 10, labels=False, duplicates="drop")
print("recalibrated deciles (2023-26, out of sample; in-sample for the calibration itself):\n", S.groupby("dc").agg(p=("sc", "mean"), y=("y", "mean"), n=("y", "size")).round(3).T.to_string())
print("raw top decile:", S[S.st >= S.st.quantile(0.9)].agg({"st": "mean", "y": "mean"}).round(3).to_dict())
print("calibration of the blend (2023-26, out of sample, quintiles):\n", S.groupby("dq").agg(p=("st", "mean"), y=("y", "mean"), n=("y", "size")).round(3).T.to_string())
P["dec"] = pd.qcut(P.pA, 10, labels=False, duplicates="drop")
print("calibration A:\n", P.groupby("dec").agg(p=("pA", "mean"), y=("y", "mean")).round(3).T.to_string())
BASEF = ["gap", "ppg_pred"]
mB = logit().fit(P[BASEF].astype(float).fillna(P[BASEF].median()), P.y)
auc_B = roc_auc_score(P.y, mB.predict_proba(P[BASEF].astype(float).fillna(P[BASEF].median()))[:, 1])
up = P[P.y == 1]; UPLIFT = float((up.act_tot - up.pred_tot).mean())
print("projection-only AUC (in-sample)", round(auc_B, 3), "| mean extra points in a breakout", round(UPLIFT))
mA_final = gbm().fit(Z.fillna(Z.median()), P.y); medA = Z.median()
mL = logit().fit(Z.fillna(medA), P.y)      # for plain-English reasons only
coef = mL[-1].coef_[0]; mu = mL[0].mean_; sd = mL[0].scale_

# ---- in-season update coefficient, refit for the new definition ----
chg = None
try:
    R = pd.read_pickle("data/inseason_rows.pkl").reset_index().rename(columns={"index": "playerId"})
    if "playerId" not in R: R["playerId"] = R.index
    SKW = {"C": dict(g=3.0, a=2.0, fow=0.25), "W": dict(g=3.5, a=2.5, fow=0.0), "D": dict(g=4.0, a=4.0, fow=0.25)}
    def fp(r, pre):
        s = SKW[r.pg]; g = lambda c: r[pre + c]
        return s["g"] * g("g") + s["a"] * g("a") + s["fow"] * g("fow") + g("pm") + 0.5 * g("pim") + 0.25 * g("hit") + 0.25 * g("blk")
    R["pr"] = R.apply(lambda r: fp(r, "pr_"), axis=1); R["po"] = R.apply(lambda r: fp(r, "po_"), axis=1)
    R = R[R.pr > 0.2]
    R["lm"] = np.log((R.po / R.pr).clip(0.5, 1.8)) * R.o_gp / (R.o_gp + 5)
    M = R.merge(P[["pid", "season", "pA", "y"]].rename(columns={"pid": "playerId", "season": "T"}), on=["playerId", "T"], how="inner")
    best = None
    for c in np.arange(0, 30.01, 0.25):
        pp = 1 / (1 + np.exp(-(lg(M.pA) + c * M.lm)))
        ll = -np.mean(M.y * np.log(pp) + (1 - M.y) * np.log(1 - pp))
        if best is None or ll < best[1]: best = (c, ll)
    chg = float(best[0])
    base_ll = -np.mean(M.y * np.log(M.pA.clip(1e-4, 1 - 1e-4)) + (1 - M.y) * np.log((1 - M.pA).clip(1e-4, 1 - 1e-4)))
    print(f"in-season update: chg {chg} (log loss {best[1]:.4f} vs {base_ll:.4f} preseason only), rows {len(M)}")
except Exception as e:
    print("in-season refit skipped:", e)

# ---- 2026-27 players ----
df = L.load()
F = L2.features(df, 2027)
ps = pd.read_pickle("data/final_skaters.pkl").set_index("playerId")
F = F.drop(columns=[c for c in ["team_last"] if c in F]).join(ps[["fid", "ppg_C", "ppg_W", "ppg_D", "proj_gp", "team", "team_last"]], how="inner")
F["pred_ppg"] = [r["ppg_" + r.pg] for _, r in F.iterrows()]
F["pred_tot"] = F.pred_ppg * F.proj_gp
F["repl"] = F.pg.map(REPL)
F["gap"] = (F.repl - F.pred_tot) / F.repl
F["gp_last"] = F.gp_L1.fillna(0)
F["moved"] = (F.team.fillna("") != F.team_last.fillna("")).astype(float)
add_feats(F)
F = F[(F.pred_tot < 1.2 * F.repl) & (F.pred_tot >= 40) & (F.gp_last >= 1)].copy()
ZF = F[FEATS].astype(float).fillna(medA)
pA = mA_final.predict_proba(ZF)[:, 1]
b = open("site/data/board.js").read(); B = json.loads(b[b.index("{"):b.rindex("}") + 1])
BP = {p["id"]: p for p in B["players"]}
eg, ei = [], []
for fid, r in zip(F.fid, F.itertuples()):
    p = BP.get(fid)
    if p and p.get("mk") is not None and p.get("mp") is not None and p.get("mr"):
        eg.append((p["mk"] - p["mp"]) / REPL.get(p["slot"], r.repl)); ei.append(1)
    else:
        eg.append(0.0); ei.append(0)
F["exp_gap"], F["exp_in"] = eg, ei
F["pA"] = pA
F["p"] = calp(stack.predict_proba(Zs(F))[:, 1])
F["pb"] = mB.predict_proba(F[BASEF].astype(float).fillna(P[BASEF].median()))[:, 1]
TXT = {
    "toi_L1": lambda r: f"Played big minutes last season ({r.toi_L1:.1f} a game)",
    "toi_tr": lambda r: f"Ice time went up last season (+{r.toi_tr:.1f} min a game)",
    "pptoi_tr": lambda r: f"Power-play time went up last season (+{r.pptoi_tr:.1f} min a game)",
    "age": lambda r: f"Young ({int(r.age)})",
    "gp_last": lambda r: (f"Only {int(r.gp_last)} NHL games last season, and he produced in them" if r.gp_last < 20 else f"Missed time last season ({int(r.gp_last)} games): a healthy year would beat his projection"),
    "oish_L1": lambda r: "His team scored a lot with him on the ice",
    "cf_L1": lambda r: "His team controlled play when he was out there",
    "pts60_L1": lambda r: "Scored a lot for the minutes he got",
    "sog60_L1": lambda r: "Shoots a lot for his minutes",
    "sh_luck": lambda r: "Shot below his usual percentage last season, so more goals should come",
    "ipp_L1": lambda r: "In on a big share of his team's goals",
    "pptoi_L1": lambda r: "Gets power-play time",
    "moved": lambda r: "New team, new role",
    "draft_r": lambda r: "High draft pick",
}
why = []
for i, r in enumerate(F.itertuples()):
    x = ZF.iloc[i].values
    contrib = coef * (x - mu) / sd
    order = np.argsort(-contrib)
    w = [TXT[FEATS[j]](r) for j in order[:5] if contrib[j] > 0.10 and FEATS[j] in TXT][:2]
    if F.exp_in.iloc[i] and F.exp_gap.iloc[i] > 0.08: w.append("Analysts rank him higher than our numbers do")
    why.append(w)
F["why"] = why
out = {r.fid: {"p": round(float(r.p), 3), "pb": round(float(r.pb), 3), "why": r.why} for r in F.itertuples()}
json.dump(dict(players=out, uplift=round(UPLIFT), base=round(float(P.y.mean()), 3)), open("data/breakout_2027.json", "w"))
json.dump(dict(uplift=round(UPLIFT), base=round(float(P.y.mean()), 3), chg=chg, jump=JUMP,
               test=dict(auc=round(float(auc_A), 3), auc_stack=round(float(auc_S), 3), top30=round(float(top_A), 3), top30_stack=round(float(top_S), 3),
                         base_rate=round(float(P.y.mean()), 3), n=int(len(P)), seasons="2017-18..2025-26")), open("data/breakout2_meta.json", "w"))
print("scored", len(out))
F["age_"] = F.age.round()
print("mean chance by age now:", F.groupby(pd.cut(F.age, [0, 22, 25, 28, 31, 50]), observed=True).p.mean().round(3).to_dict())
for r in F.sort_values("p", ascending=False).head(20).itertuples():
    print(f"{r.name:24} {r.pg} {r.team:4} age {r.age:4.1f} pred {r.pred_tot:5.0f} repl {r.repl:4.0f} p {r.p:.2f} base {r.pb:.2f} {r.why}")
