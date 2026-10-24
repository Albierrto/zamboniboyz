"""Backup goalies' points per start (build step, also runnable on docs/data/board.js).

A goalie's season total (`pts`) went through the calibration 28.5 + 0.88 x projected (fit on 2016-2026: low-projected
goalies end up with more points than projected) and the analyst blend, but his projected starts (`gs`) did not. For
a backup the extra points really come from extra starts (an injury ahead of him, a hot run), not from scoring more
per start, so total / starts came out impossible: Sebastian Cossa 110 pts on 6 starts = 18.3 a start, when real
goalies score 4-6 a start in this league. The in-season update (live.py) then treats every start he gets as worth 18.

Fix: points per start come from his own projected stat line (wins, saves, goals against, shutouts per start), shrunk
toward the median goalie with 10 starts of weight. When total / starts is more than 15% above that, starts are raised
to total / points-per-start (capped at 85% of his team's games). Only backups (under 30 projected starts) are
changed, and a team's goalies together never go past 97% of its games (raises are scaled back to fit). Totals never
change, and no goalie's starts go down.
"""
import json, re, statistics, sys

K = 10          # starts of weight on the median points per start
OVER = 1.15     # only fix goalies whose total / starts is this far above their stat-line rate
BACKUP = 30     # only backups (fewer projected starts than this): starters' totals already come from their workload
TEAM_MAX = 0.97 # a team's goalies can't start more than its games: raises are scaled back to fit


def line_pps(p):
    L = p.get("line") or {}
    if not p.get("gs") or not L:
        return None
    return (3 * L.get("w", 0) + 0.25 * L.get("sv", 0) - L.get("ga", 0) + 4 * L.get("so", 0)) / p["gs"]


def fix(players):
    G = [p for p in players if p.get("slot") == "G" and p.get("gs") and p.get("pts")]
    med = statistics.median([x for x in (line_pps(p) for p in G if p["gs"] >= 30) if x]) if G else 4.85
    want = {}
    for p in G:
        lp = line_pps(p)
        if lp is None or p["gs"] >= BACKUP:
            continue
        pps = (p["gs"] * lp + K * med) / (p["gs"] + K)
        if p["pts"] / p["gs"] <= OVER * pps:
            continue
        gs_new = min(0.85 * (p.get("gm") or 82), p["pts"] / pps)
        if gs_new > p["gs"]:
            want[p["id"]] = (gs_new, pps)
    # a team's goalies can't start more games than it plays: scale the raises back to fit
    by_team = {}
    for p in G:
        by_team.setdefault(p.get("t") or "", []).append(p)
    changed = []
    for t, gs in by_team.items():
        raised = [p for p in gs if p["id"] in want]
        if not raised:
            continue
        cap = TEAM_MAX * max(p.get("gm") or 82 for p in gs)
        base = sum(p["gs"] for p in gs)
        extra = sum(want[p["id"]][0] - p["gs"] for p in raised)
        room = max(0.0, cap - base)
        f = 1.0 if extra <= room else room / extra
        for p in raised:
            old = p["gs"]
            new = round(old + f * (want[p["id"]][0] - old))
            if new <= old:
                continue
            p["gs"] = new
            if p.get("gpg"):
                p["gppg"] = round(p["pts"] * p["gpg"] / p["gs"], 3)      # keeps pts = gppg * gs / gpg
            for c in p.get("ch") or []:
                c[1] = re.sub(r"We project about \d+ starts for him\.", f"We project about {p['gs']} starts for him.", c[1])
            changed.append((p["n"], old, p["gs"], round(p["pts"] / old, 1), round(p["pts"] / p["gs"], 2)))
    return changed, med


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "docs/data/board.js"
    s = open(path, encoding="utf-8").read()
    B = json.loads(s[s.index("{"):s.rindex("}") + 1])
    changed, med = fix(B["players"])
    B["meta"]["goalieStartsFix"] = {"median_pps": round(med, 2), "k": K, "over": OVER, "n": len(changed)}
    open(path, "w", encoding="utf-8").write("window.BOARD=" + json.dumps(B, separators=(",", ":"), ensure_ascii=False) + ";\n")
    print(f"median points per start {med:.2f}; {len(changed)} goalies changed")
    for c in changed:
        print("  %-22s starts %3d -> %3d   (was %.1f a start, now %.2f)" % c)
