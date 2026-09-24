"""Preseason breakout chances for 2026-27 (see breakoutlab.py for the test).
Model A: logistic on 9 past seasons (projection gap, ice time, age, games missed, on-ice numbers...).
Stack: on 2022-23..2025-26 out-of-sample predictions, re-weight A with the analysts' view (tested: small but real gain).
Output: data/breakout_2027.json {fid: {p, why:[...]}} for skaters projected below waiver level."""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "build")
from breakoutlab import frame, add_feats, FEATS, REPL, make_pipeline, StandardScaler, LogisticRegression
import lab as L, lab2 as L2, expertlab as EL

def fitA(P):
    Z = P[FEATS].astype(float); med = Z.median()
    m = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=3000)).fit(Z.fillna(med), P.y)
    return m, med

X = frame(); P = X[X.pool].reset_index(drop=True)
# out-of-sample A predictions for the stacking seasons
oos = np.zeros(len(P))
for T in sorted(P.season.unique()):
    tr, te = P[P.season != T], P[P.season == T]
    m, med = fitA(tr); oos[te.index] = m.predict_proba(te[FEATS].astype(float).fillna(med))[:, 1]
P["pA"] = oos
# analysts' view for 2023-2026
rows = []
for T in (2023, 2024, 2025, 2026):
    d = X[X.season == T].copy(); d["k"] = d.name.map(EL.norm)
    cs, n = EL.consensus(d.k, EL.sources_for(T)); imp = EL.implied(d, cs, "pg")
    rows.append(pd.DataFrame({"season": T, "pid": d.index, "exp_gap": ((imp - d.pred_tot) / d.repl).values, "exp_in": cs.notna().astype(int).values}))
E = pd.concat(rows)
P["pid"] = X[X.pool].index.values
S = P[P.season >= 2023].merge(E, on=["season", "pid"], how="left")
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
Zs = np.column_stack([lg(S.pA), S.exp_gap.clip(-1, 1).fillna(0), S.exp_in.fillna(0)])
stack = LogisticRegression(C=1.0, max_iter=2000).fit(Zs, S.y)
print("stack coefs [logit A, analyst gap, ranked by analysts]:", stack.coef_.round(3), stack.intercept_.round(3))
mA, medA = fitA(P)
# projection-only baseline: the chance for a typical player projected like him
BASEF = ["gap", "ppg_pred"]
mB = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=3000)).fit(P[BASEF].astype(float).fillna(P[BASEF].median()), P.y)
up = P[P.y == 1]
UPLIFT = float((up.act_tot - up.pred_tot).mean())
print("mean extra points in a breakout season:", round(UPLIFT), "| base rate", round(P.y.mean(), 3))
coef = mA[-1].coef_[0]; mu = mA[0].mean_; sd = mA[0].scale_

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
F = F[(F.pred_tot < F.repl) & (F.pred_tot >= 40) & (F.gp_last >= 1)].copy()
Z = F[FEATS].astype(float).fillna(medA)
pA = mA.predict_proba(Z)[:, 1]
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
F["p"] = stack.predict_proba(np.column_stack([lg(pA), np.clip(F.exp_gap, -1, 1), F.exp_in]))[:, 1]
F["pb"] = mB.predict_proba(F[BASEF].astype(float).fillna(P[BASEF].median()))[:, 1]

# plain-English reasons from the biggest positive pushes in model A
TXT = {
    "gap": lambda r: "Projected close to being a regular fantasy starter already",
    "toi_L1": lambda r: f"Played big minutes last season ({r.toi_L1:.1f} a game)",
    "toi_tr": lambda r: f"Ice time went up last season (+{r.toi_tr:.1f} min a game)",
    "age": lambda r: f"Young ({int(r.age)}): still improving",
    "gp_last": lambda r: (f"Only {int(r.gp_last)} NHL games last season, and he produced in them" if r.gp_last < 20 else f"Missed time last season ({int(r.gp_last)} games) but produced when he played"),
    "oish_L1": lambda r: "His team scored a lot with him on the ice",
    "height": lambda r: "Big body (tends to stick in the lineup)",
    "car_gp": lambda r: "Long NHL track record",
    "cf_L1": lambda r: "His team controlled play when he was out there",
    "ppg_pred": lambda r: "Scores well per game when he plays",
    "ipp_L1": lambda r: "In on a big share of his team's goals",
    "pptoi_L1": lambda r: "Gets power-play time",
    "moved": lambda r: "New team, new role",
}
why = []
for i, r in enumerate(F.itertuples()):
    x = Z.iloc[i].values
    contrib = coef * (x - mu) / sd
    order = np.argsort(-contrib)
    w = [TXT[FEATS[j]](r) for j in order[:4] if contrib[j] > 0.12 and FEATS[j] in TXT][:2]
    if F.exp_in.iloc[i] and F.exp_gap.iloc[i] > 0.08: w.append("Analysts rank him higher than our numbers do")
    why.append(w)
F["why"] = why
out = {r.fid: {"p": round(float(r.p), 3), "pb": round(float(r.pb), 3), "why": [w for w in r.why if not w.startswith("Projected close")]} for r in F.itertuples()}
json.dump(dict(players=out, uplift=round(UPLIFT), base=round(float(P.y.mean()), 3)), open("data/breakout_2027.json", "w"))
print("scored", len(out))
F["lift"] = F.p - F.pb
top = F.sort_values("lift", ascending=False).head(25)
for r in top.itertuples():
    print(f"{r.name:24} {r.pg} {r.team:4} age {r.age:4.1f} pred {r.pred_tot:5.0f} repl {r.repl:4.0f} p {r.p:.2f} base {r.pb:.2f}  {r.why}")
