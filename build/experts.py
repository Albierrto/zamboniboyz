"""Analyst consensus for 2026-27.

The raw lists stay in data/raw/experts (never published). The site only gets our blended numbers
and each player's consensus position rank. How much the consensus moves a player was tested on
2022-23..2025-26 (build/expertlab.py):
  - skaters: experts add a little overall (best flat weight ~0.2) but a lot more for young players,
    players with short track records and players who changed teams (~0.35), and almost nothing
    for centers (their faceoff points are invisible to category rankings; ~0.05)
  - goalies: experts know the depth charts; best weight ~0.6-0.7
"""
import csv, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, "build")
from expertlab import norm, load_list

CUR = "data/raw/experts/2026"
OVERALL = {  # file -> label used in the How-it-works page (outlet names only, no lists)
    "dailyfaceoff_larkin": "Daily Faceoff (Matt Larkin)",
    "dailyfaceoff_seguin": "Daily Faceoff (Brock Seguin)",
    "dailyfaceoff_bondy": "Daily Faceoff (Michael Bondy)",
    "nhlcom": "NHL.com",
    "rotoballer_smith": "RotoBaller (Andy Smith)",
    "razzball_viz": "Razzball",
    "cbs_top200": "CBS Sports",
}
AG_LABEL = "Apples & Ginos projections, re-scored with this league's points"
ADP_LABEL = "Fantrax ADP (where drafters took players)"
ADP_FLOOR = 285

SK = {"C": dict(g=3.0, a=2.0), "W": dict(g=3.5, a=2.5), "D": dict(g=4.0, a=4.0)}

def ag_points():
    """Apples & Ginos stat projections turned into this league's points (no faceoffs or +/- in their sheet)."""
    path = f"{CUR}/applesginos_skater_projections_raw.csv"
    out = {}
    if not os.path.exists(path): return out
    rows = list(csv.reader(open(path, encoding="utf-8")))
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == "Name")
    for r in rows[hdr + 1:]:
        if not r or not r[0].strip(): continue
        try:
            gp, g, a, hit, blk, pim = (float(r[i] or 0) for i in (4, 5, 6, 10, 11, 12))
        except ValueError:
            continue
        pos = r[2].upper()
        grp = "D" if pos.startswith("D") else ("C" if pos.startswith("C") else "W")
        s = SK[grp]
        out[norm(r[0])] = s["g"] * g + s["a"] * a + 0.25 * hit + 0.25 * blk + 0.5 * pim
    return out

def lists():
    L = {k: load_list(f"{CUR}/{k}.txt") for k in OVERALL if os.path.exists(f"{CUR}/{k}.txt")}
    return L

def consensus(df, goalie_mask, adp_col="adp"):
    """Mean log-rank across sources (a missing player counts as 1.3x that list's length).
    df needs columns k (normalized name) and adp. Returns (score, n_lists_with_player)."""
    L = lists()
    ag = ag_points()
    cols, present = [], []
    for name, lst in L.items():
        n = max(lst.values())
        cols.append(df.k.map(lambda k: np.log(lst.get(k, 1.3 * n))))
        present.append(df.k.map(lambda k: k in lst))
    # A&G: rank skaters by re-scored points (skaters only)
    if ag:
        order = sorted(ag, key=lambda k: -ag[k])
        agr = {k: i + 1 for i, k in enumerate(order)}
        n = len(agr)
        c = df.k.map(lambda k: np.log(agr.get(k, 1.3 * n)))
        cols.append(c.where(~goalie_mask))
        present.append(df.k.map(lambda k: k in agr) & ~goalie_mask)
    # Fantrax ADP as one more voice
    has = df[adp_col].notna() & (df[adp_col] < ADP_FLOOR)
    r = df.loc[has, adp_col].rank(method="first")
    n = int(has.sum())
    cols.append(np.log(r.reindex(df.index).fillna(1.3 * n)))
    present.append(has)
    M = pd.concat(cols, axis=1)
    P = pd.concat(present, axis=1)
    nin = P.sum(axis=1)
    score = M.mean(axis=1, skipna=True).where(nin > 0)
    return score, nin

def weights(d):
    """Share of the gap between our number and the analysts' number that we take, per player."""
    w = pd.Series(0.20, index=d.index)
    young = d.age.fillna(30) <= 23
    short = d.gp_last.fillna(0) < 50
    moved = d.moved.fillna(False).astype(bool)
    w[d.prim.eq("C")] = 0.05
    w[(young | short | moved) & d.kind.eq("S")] = 0.35
    w[d.kind.eq("G")] = 0.65
    w[d.rookie.fillna(False).astype(bool)] = 0.60
    return w

SOURCES_TEXT = [OVERALL[k] for k in OVERALL] + [AG_LABEL, ADP_LABEL]
