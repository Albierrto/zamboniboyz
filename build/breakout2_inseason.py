"""Out-of-sample check of the in-season breakout update (build/breakout2.py fits chg), 5 past seasons.
For players in the breakout pool, at about 10 and 20 games in: how often a hot start alone (30%+ above his projection)
ended in a breakout, how often players the update puts at 40%+ did, and the top 30 by updated vs preseason chance.
Adds the numbers to data/breakout2_meta.json as test.ins (the site's Help text uses them)."""
import json
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score

META = json.load(open("data/breakout2_meta.json"))
P = pd.read_pickle("data/breakout2_oos.pkl"); P = P[P.pool]
R = pd.read_pickle("data/inseason_rows.pkl").reset_index().rename(columns={"index": "playerId"})
SKW = {"C": dict(g=3.0, a=2.0, fow=0.25), "W": dict(g=3.5, a=2.5, fow=0.0), "D": dict(g=4.0, a=4.0, fow=0.25)}
def fp(r, pre):
    s = SKW[r.pg]; g = lambda c: r[pre + c]
    return s["g"] * g("g") + s["a"] * g("a") + s["fow"] * g("fow") + g("pm") + 0.5 * g("pim") + 0.25 * g("hit") + 0.25 * g("blk")
R["pr"] = R.apply(lambda r: fp(r, "pr_"), axis=1); R["po"] = R.apply(lambda r: fp(r, "po_"), axis=1)
R["o_fp"] = R.apply(lambda r: fp(r, "o_"), axis=1) / R.o_gp
R = R[R.pr > 0.2]
R["lm"] = np.log((R.po / R.pr).clip(0.5, 1.8)) * R.o_gp / (R.o_gp + 5)
M = R.merge(P[["pid", "season", "p_gbm", "y"]].rename(columns={"pid": "playerId", "season": "T"}), on=["playerId", "T"], how="inner")
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
M["pu"] = 1 / (1 + np.exp(-(lg(M.p_gbm) + META["chg"] * M.lm)))
ins = {}
for key, lo, hi in [("g10", 8, 14), ("g20", 15, 25)]:
    D = M[(M.o_gp >= lo) & (M.o_gp <= hi)].sort_values("o_gp").groupby(["playerId", "T"]).tail(1)
    hot, fl = D[D.o_fp >= 1.3 * D.pr], D[D.pu >= 0.4]
    ins[key] = dict(n=len(D), base=round(D.y.mean(), 3), auc_pre=round(roc_auc_score(D.y, D.p_gbm), 3), auc=round(roc_auc_score(D.y, D.pu), 3),
                    hot=round(hot.y.mean(), 3), flag=round(fl.y.mean(), 3),
                    top30=round(D.sort_values("pu", ascending=False).groupby("T").head(30).y.mean(), 3),
                    top30_pre=round(D.sort_values("p_gbm", ascending=False).groupby("T").head(30).y.mean(), 3))
    print(key, ins[key])
META["test"]["ins"] = ins
json.dump(META, open("data/breakout2_meta.json", "w"))
