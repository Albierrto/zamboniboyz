#!/usr/bin/env python3
"""In-season refresh for the ZamboniBoyz site. Runs on GitHub Actions several times a day (stdlib only).

Reads docs/data/board.js (preseason projections), pulls 2026-27 season-to-date stats from the NHL's
public stats API, and writes docs/data/live.json with updated points-per-game for every player.

How much the early numbers count was tuned on five past seasons (build/inseason_lab.py,
build/inseason_goalies.py): each stat's projection is worth K games of evidence, so fast-settling
stats (faceoffs, hits) move quickly and goals barely move early. Ice-time and power-play-time changes
add a little on top. Goalies: starts share and points per start update the same way.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = dt.timezone(dt.timedelta(hours=-4))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.environ.get("LIVE_BOARD", os.path.join(ROOT, "docs", "data", "board.js"))
OUT = os.environ.get("LIVE_OUT", os.path.join(ROOT, "docs", "data", "live.json"))
SEASON = os.environ.get("LIVE_SEASON", "20262027")
K = {"g": 81.5, "a": 69.7, "pm": 105.8, "pim": 133.5, "hit": 17.5, "blk": 34.7, "fow": 8.2}
ROLE = {"toi": 0.043, "pp": 0.033}
KG = {"share": 23.2, "pps": 53.6}
SK = {"C": {"g": 3.0, "a": 2.0, "fow": 0.25}, "W": {"g": 3.5, "a": 2.5, "fow": 0.0}, "D": {"g": 4.0, "a": 4.0, "fow": 0.25}}
COM = {"pm": 1.0, "pim": 0.5, "hit": 0.25, "blk": 0.25}
CATS = ["g", "a", "pm", "pim", "hit", "blk", "fow"]


def w(slot, c):
    return SK[slot].get(c, COM.get(c, 0.0))


def get(url, tries=6):
    last = None
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "zamboniboyz-refresh/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # rate limits and hiccups: back off
            last = e
            time.sleep(5 * (a + 1))
    raise RuntimeError(f"{url}: {last}")


def nhl(kind, report, d0=None, d1=None):
    exp = f"seasonId={SEASON} and gameTypeId=2"
    if d0: exp += f' and gameDate>="{d0}"'
    if d1: exp += f' and gameDate<="{d1}"'
    url = (f"https://api.nhle.com/stats/rest/en/{kind}/{report}?isAggregate=true&isGame=false&limit=-1&start=0"
           f"&cayenneExp={urllib.parse.quote(exp)}")
    d = get(url)
    time.sleep(1.5)
    return {r["playerId"]: r for r in d.get("data", [])}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.replace("-", " ").replace(".", " "))).strip()


def main():
    raw = open(BOARD, encoding="utf-8").read()
    B = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    meta, players = B["meta"], B["players"]
    now = dt.datetime.now(dt.timezone.utc)
    today = dt.date.fromisoformat(os.environ["LIVE_TODAY"]) if os.environ.get("LIVE_TODAY") else now.astimezone(ET).date()
    out = {"generated": now.isoformat(timespec="seconds"), "season": SEASON, "players": {}, "started": False}
    start = dt.date.fromisoformat(meta["sched"]["days"][0][0])
    if today <= start:
        out["note"] = "Season hasn't started; nothing to update yet."
        json.dump(out, open(OUT, "w"), separators=(",", ":"))
        print(out["note"])
        return
    # team games completed (dates before today, ET)
    teams = meta["sched"]["teams"]
    tg, tg10 = {}, {}
    d10 = (today - dt.timedelta(days=10)).isoformat()
    for d, idx in meta["sched"]["days"]:
        if d >= today.isoformat():
            continue
        for i in idx:
            t = teams[i]
            tg[t] = tg.get(t, 0) + 1
            if d >= d10:
                tg10[t] = tg10.get(t, 0) + 1
    y = (today - dt.timedelta(days=1)).isoformat()
    # testing hook: replay a past season's stats up to a date (LIVE_SEASON + LIVE_THROUGH)
    thru = os.environ.get("LIVE_THROUGH")
    s_hi = thru or None
    r_lo, r_hi = ((dt.date.fromisoformat(thru) - dt.timedelta(days=9)).isoformat(), thru) if thru else (d10, y)
    summ = nhl("skater", "summary", None, s_hi); rt = nhl("skater", "realtime", None, s_hi)
    fo = nhl("skater", "faceoffwins", None, s_hi); toi = nhl("skater", "timeonice", None, s_hi)
    recent = nhl("skater", "summary", r_lo, r_hi)
    gsum = nhl("goalie", "summary", None, s_hi); grecent = nhl("goalie", "summary", r_lo, r_hi)
    out["started"] = bool(summ)
    # NHL id -> board player (by NHL id; rookies without one by name)
    byname = {}
    for pid, r in list(summ.items()) + list(gsum.items()):
        byname.setdefault(norm(r.get("skaterFullName") or r.get("goalieFullName")), []).append(pid)
    for p in players:
        nid = p.get("pid")
        if not nid:
            c = byname.get(norm(p["n"]), [])
            if len(c) == 1:
                nid = c[0]
        if not nid:
            continue
        team = p.get("t") or ""
        rec = {}
        if p["slot"] == "G":
            s = gsum.get(nid)
            if not s or not p.get("gs") or not p.get("pts") or not p.get("gm"):
                continue
            starts = s.get("gamesStarted") or 0
            n_team = tg.get(team, 0)
            prior_share = p["gs"] / max(p["gm"], 1)
            prior_pps = p["pts"] / p["gs"]
            fp = 3 * (s.get("wins") or 0) + 0.25 * (s.get("saves") or 0) - (s.get("goalsAgainst") or 0) + 4 * (s.get("shutouts") or 0) + 3 * (s.get("goals") or 0) + 2 * (s.get("assists") or 0) + 0.5 * (s.get("penaltyMinutes") or 0)
            obs_pps = fp / starts if starts else prior_pps
            share = (KG["share"] * prior_share + starts) / (KG["share"] + n_team) if n_team else prior_share
            pps = (KG["pps"] * prior_pps + starts * obs_pps) / (KG["pps"] + starts)
            mult = (share * pps) / (prior_share * prior_pps)
            rec = {"m": {"G": round(max(0.3, min(2.0, mult)), 4)}, "n": s.get("gamesPlayed") or 0, "gs": starts, "fp": round(fp, 1), "tg": n_team}
            gp10 = (grecent.get(nid) or {}).get("gamesPlayed", 0)
        else:
            s = summ.get(nid)
            if not s or not p.get("line") or not p.get("gp"):
                continue
            n = s.get("gamesPlayed") or 0
            if n <= 0:
                continue
            L, gp0 = p["line"], p["gp"]
            prior = {c: (L.get(c) or 0) / gp0 for c in CATS}
            tot = {"g": s.get("goals") or 0, "a": s.get("assists") or 0, "pm": s.get("plusMinus") or 0, "pim": s.get("penaltyMinutes") or 0,
                   "hit": (rt.get(nid) or {}).get("hits") or 0, "blk": (rt.get(nid) or {}).get("blockedShots") or 0,
                   "fow": (fo.get(nid) or {}).get("totalFaceoffWins") or 0}
            post = {c: (K[c] * prior[c] + tot[c]) / (K[c] + n) for c in CATS}
            t_now = ((toi.get(nid) or {}).get("timeOnIcePerGame") or 0) / 60
            pp_now = ((toi.get(nid) or {}).get("ppTimeOnIcePerGame") or 0) / 60
            shrink = n / (n + 5)
            dtoi = max(-6, min(6, t_now - (L.get("toi") or t_now))) * shrink
            dpp = max(-3, min(3, pp_now - (L.get("pptoi") or pp_now))) * shrink
            m = {}
            for slot in (p.get("slotpts") or {}):
                if slot not in SK:
                    continue
                pr = sum(w(slot, c) * prior[c] for c in CATS)
                po = sum(w(slot, c) * post[c] for c in CATS) + ROLE["toi"] * dtoi + ROLE["pp"] * dpp
                if pr > 0.2:
                    m[slot] = round(max(0.5, min(1.8, po / pr)), 4)
            best = p["slot"] if p["slot"] in SK else next(iter(m), "W")
            fp = sum(w(best, c) * tot[c] for c in CATS)
            rec = {"m": m, "n": n, "fp": round(fp, 1), "toi": round(t_now, 1), "dtoi": round(dtoi, 2), "pp": round(pp_now, 2), "dpp": round(dpp, 2), "tg": tg.get(team, 0)}
            gp10 = (recent.get(nid) or {}).get("gamesPlayed", 0)
        # sitting out: his team played 3+ games in the last 10 days and he played none
        if tg10.get(team, 0) >= 3 and gp10 == 0:
            rec["out"] = tg10.get(team, 0)
        out["players"][p["id"]] = rec
    out["asOf"] = y
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print(f"live: {len(out['players'])} players updated through {y}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the site: keep the last good file
        print("refresh failed:", e, file=sys.stderr)
        sys.exit(1)
