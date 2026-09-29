"""Keeper-league facts for the trade tools, added to board.js meta (also run at the end of export.py).

- keeperAge: next-season factor by age (build/keeperlab.py; skaters quadratic, goalies by age band)
- pickCurve: value of overall pick n in this league's draft, from the 2026 draft (players' projected season
  points above waiver level, floored at 0): v(n) = A*exp(-b*n) + c, floored at 0
- rules: from the league rulebook and Fantrax settings
"""
import json, os
import numpy as np
from scipy.optimize import curve_fit

def build(board_players, draft_path="data/raw/getDraftResults.json"):
    ka = json.load(open("data/keeper_age.json"))
    P = {p["id"]: p for p in board_players}
    dr = json.load(open(draft_path))
    n, v = [], []
    for pk in dr.get("draftPicks", []):
        p = P.get(pk.get("playerId"))
        if not p or pk.get("pick") is None: continue
        n.append(pk["pick"]); v.append(max(0.0, p.get("val") or 0.0))
    f = lambda x, A, b, c: A * np.exp(-b * x) + c
    (A, b, c), _ = curve_fit(f, np.array(n, float), np.array(v, float), p0=(80, 0.03, 5), maxfev=20000)
    rounds = {r + 1: round(float(np.mean(v[r * 12:(r + 1) * 12])), 1) for r in range(len(v) // 12)}
    return {
        "keeperAge": {"coef": ka["coef"], "goalie": ka["goalie"], "test": ka["test"]},
        "pickCurve": {"A": round(float(A), 3), "b": round(float(b), 5), "c": round(float(c), 3), "n": len(n), "byRound": rounds},
        "rules": {
            "keepers": {"C": 1, "W": 2, "D": 2, "G": 1, "X": 1},
            "draftRounds": 11, "pickYears": 1,
            "lottery": [30, 25, 20, 15, 10],          # 12th..8th place, round 1 only
            "playoffTeams": 7, "tradeDeadline": "2027-02-23",
            "fees": {"add": 2, "goalieAdd": 4, "sundayAdd": 4, "drop": 1, "trade": 1},
            "irSlots": 4, "noAddsInPlayoffs": True, "ruleChangeVote": 0.66,
        },
    }

if __name__ == "__main__":
    path = "site/data/board.js"
    raw = open(path, encoding="utf-8").read()
    B = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    B["meta"].update(build(B["players"]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("window.BOARD=" + json.dumps(B, separators=(",", ":"), ensure_ascii=False) + ";\n")
    m = B["meta"]
    print("pickCurve", m["pickCurve"]); print("keeperAge", m["keeperAge"]["goalie"], m["keeperAge"]["test"])
    print("board.js bytes:", os.path.getsize(path))
