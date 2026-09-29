"""Next-season (keeper) value: how a player's fantasy total changes one more year out, by age.

For each season T (2014-15..2024-25) we take players with 20+ games in T-1 (so the group is fixed by what
was known before T), and compare their league-scoring totals (per 82 games, 0 if they didn't play) in T and T+1.
f(age) = sum(T+1) / sum(T) for players of that age at T. Retirements, demotions and injuries count, which is
what a keeper is exposed to. Tested leave-one-season-out: projection for T x f(age) vs the projection alone,
against what the player scored in T+1.
"""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "build")
import lab as L

df = L.load()
df["tot"] = L.fppg_by_pos(df.assign(**{c: df[c] / df.gp.clip(lower=1) for c in ["g", "a", "pm", "pim", "hit", "blk", "fow"]})) * df.gp
df["tot82"] = df.tot * 82 / df.slen.fillna(82)
tot = df.pivot_table(index="playerId", columns="season", values="tot82", aggfunc="sum")
gp = df.pivot_table(index="playerId", columns="season", values="gp", aggfunc="sum")
frames = pd.read_pickle("data/lab_frames.pkl")

rows = []
for T in range(2015, 2026):
    if T + 1 > df.season.max(): break
    fr = frames.get(T)
    if fr is None: continue
    base = fr[fr.gp_last >= 20].copy()
    # step-1 projection for T (known before T), per 82 games including availability
    rates = base.rename(columns={f"v1_{c}": c for c in ["g", "a", "pm", "pim", "hit", "blk", "fow"]})
    base["proj"] = L.fppg_by_pos(rates) * 82 * base.v1_avail
    base["t0"] = tot.reindex(base.index)[T].fillna(0) if T in tot else 0
    base["t1"] = tot.reindex(base.index)[T + 1].fillna(0) if T + 1 in tot else 0
    base["T"] = T
    rows.append(base[["name", "pg", "age", "proj", "t0", "t1", "T"]])
R = pd.concat(rows)
R = R[R.groupby("T").proj.rank(ascending=False) <= 360]   # the players who matter for keepers and trades
R["a"] = R.age.round().clip(19, 37).astype(int)

def fit(D):
    g = D.groupby("a")[["t0", "t1"]].sum()
    raw = (g.t1 / g.t0)
    n = D.groupby("a").size()
    # smooth: weighted quadratic in age, then cap
    x = raw.index.values.astype(float); w = n.reindex(raw.index).values
    c = np.polyfit(x, raw.values, 2, w=np.sqrt(w))
    return raw, n, c

raw, n, c = fit(R)
print("age  n   raw   smooth")
for a in raw.index: print(a, int(n[a]), round(raw[a], 3), round(np.polyval(c, a), 3))
for pgp in ["D", "C", "W"]:
    rr, nn, cc = fit(R[R.pg == pgp])
    print(pgp, "smooth at 21,25,29,33:", [round(np.polyval(cc, a), 3) for a in (21, 25, 29, 33)])

# leave-one-season-out test
errs = {"proj": [], "proj*f": [], "proj*f(pos)": []}
for T in sorted(R["T"].unique()):
    tr, te = R[R["T"] != T], R[R["T"] == T]
    _, _, cT = fit(tr)
    f = np.polyval(cT, te.a)
    errs["proj"].append(np.abs(te.proj - te.t1).mean())
    errs["proj*f"].append(np.abs(te.proj * f - te.t1).mean())
    fp = np.zeros(len(te))
    for pgp in ["C", "W", "D"]:
        m = (te.pg == pgp).values
        _, _, cc = fit(tr[tr.pg == pgp]); fp[m] = np.polyval(cc, te.a[m])
    errs["proj*f(pos)"].append(np.abs(te.proj * fp - te.t1).mean())
print({k: round(float(np.mean(v)), 1) for k, v in errs.items()})
# also: how does next-year total compare to the projection for this year, in rank terms
from scipy.stats import spearmanr
print("rank corr proj vs t1:", round(spearmanr(R.proj, R.t1)[0], 3), " proj*f vs t1:", round(spearmanr(R.proj * np.polyval(c, R.a), R.t1)[0], 3))
json.dump({"coef": list(map(float, c)), "ages": [int(a) for a in raw.index], "raw": [float(x) for x in raw.values], "n": [int(x) for x in n.values],
           "test": {k: round(float(np.mean(v)), 1) for k, v in errs.items()}}, open("data/keeper_age.json", "w"))

# ---- variant: local average over neighbouring ages instead of a quadratic
def fit_local(D):
    g = D.groupby("a")[["t0", "t1"]].sum()
    out = {}
    for a in range(19, 38):
        m = g.loc[[x for x in g.index if abs(x - a) <= 1]]
        out[a] = m.t1.sum() / m.t0.sum() if len(m) else 1.0
    return out
e2 = []
for T in sorted(R["T"].unique()):
    tr, te = R[R["T"] != T], R[R["T"] == T]
    fl = fit_local(tr)
    e2.append(np.abs(te.proj * te.a.map(fl) - te.t1).mean())
print("local-average MAE:", round(float(np.mean(e2)), 1))
fl = fit_local(R)
print({a: round(v, 3) for a, v in fl.items()})

# ---- goalies: same idea with the goalie frames (actual league-scoring totals per season)
G = pd.read_pickle("data/glab_frames.pkl")
gt = {}
for T, fr in G.items():
    for pid, r in fr.iterrows():
        gt[(pid, T)] = (r.y_tot if pd.notna(r.y_tot) else 0.0, r.age, r.gp_last, r.name)
grows = []
for (pid, T), (t0, age, gpl, nm) in gt.items():
    if (pid, T + 1) not in gt and T + 1 > max(G): continue
    if gpl is None or not (gpl >= 15): continue
    t1 = gt.get((pid, T + 1), (0.0,))[0]
    grows.append((nm, T, round(age), t0, t1))
GR = pd.DataFrame(grows, columns=["name", "T", "a", "t0", "t1"])
GR = GR[GR["T"] < max(G)]
GR["b"] = pd.cut(GR.a, [0, 25, 28, 31, 34, 50], labels=["<=25", "26-28", "29-31", "32-34", "35+"])
gg = GR.groupby("b", observed=True)[["t0", "t1"]].sum()
print("goalies:", (gg.t1 / gg.t0).round(3).to_dict(), GR.groupby("b", observed=True).size().to_dict())
json.dump({"coef": list(map(float, c)), "local": {str(a): round(v, 4) for a, v in fl.items()},
           "goalie": {str(k): round(float(v), 4) for k, v in (gg.t1 / gg.t0).items()},
           "test": {k: round(float(np.mean(v)), 1) for k, v in errs.items()} | {"local": round(float(np.mean(e2)), 1)}},
          open("data/keeper_age.json", "w"))
