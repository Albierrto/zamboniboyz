#!/usr/bin/env python3
"""In-season refresh for the ZamboniBoyz site. Runs on GitHub Actions several times a day (stdlib only).

Reads docs/data/board.js (preseason projections), pulls 2026-27 season-to-date stats from the NHL's
public stats API, and writes docs/data/live.json with updated points-per-game for every player.

How much the early numbers count was tuned on five past seasons (build/inseason_lab.py,
build/inseason_goalies.py): each stat's projection is worth K games of evidence, so fast-settling
stats (faceoffs, hits) move quickly and goals barely move early. Ice-time and power-play-time changes
add a little on top. Goalies: starts share and points per start update the same way.

Goalie starts: every team's starting goalie game by game for the last 30 days ("gst", with names in "gnm"), call-ups
included, so the site can tell who is actually starting when a team's goalies are hurt.

Injuries: every run (before the season too) it reads ESPN's public NHL injury report and writes each
listed player's status, expected return date and body part into live.json ("inj"). Only those facts
are kept, never the report's write-ups. Players from the preseason news list who have since played
a game are listed in "back" so the site stops treating them as hurt.
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
# playing time (build/inseason_games.py, 2021-22..2025-26, players active in the last 10 days): the share of his team's
# games he'll play from here = (K*preseason share + games played) / (K + team games). K is 6.5 team games when he's
# playing more than expected (a rookie projected for 36 games who has played all 17 was still being valued at 36), and
# 30.7 when he's playing less (a regular back from an injury mostly plays from here, but misses a bit more than
# planned). Never raised past 84.6% unless the board already had him higher: even everyday players miss games.
KA = {"up": 6.5, "down": 30.7, "cap": 0.846}
KG = {"share": 23.2, "pps": 53.6}
# start share with recent games counting more (build/inseason_goalie_recency.py, 2015-16..2025-26, LOSO):
# share = (KD*prior + sum(d^k * started k games ago)) / (KD + sum(d^k)). Prior worth 11.6 team games, each older
# game counts 0.907 as much as the one after it. Beat the flat K=23.2 update at 7 of 8 checkpoints (RMSE .1609 -> .1585).
GD = {"k": 11.6, "d": 0.907}
SK = {"C": {"g": 3.0, "a": 2.0, "fow": 0.25}, "W": {"g": 3.5, "a": 2.5, "fow": 0.0}, "D": {"g": 4.0, "a": 4.0, "fow": 0.25}}
COM = {"pm": 1.0, "pim": 0.5, "hit": 0.25, "blk": 0.25}
CATS = ["g", "a", "pm", "pim", "hit", "blk", "fow"]
INJ_URL = os.environ.get("LIVE_INJ_URL", "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries")
ESPN_TEAM = {"LA": "LAK", "NJ": "NJD", "SJ": "SJS", "TB": "TBL", "UTAH": "UTA"}


def w(slot, c):
    return SK[slot].get(c, COM.get(c, 0.0))


def get(url, tries=6, ua="zamboniboyz-refresh/1.0"):
    last = None
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua} if ua else {})
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


def goalie_log(today, thru=None):
    """Every team's starting goalie, game by game, this season so far, including call-ups who aren't on the board.
    Returns ({team: [[date, nhlId], ...]} in game order, {nhlId: name})."""
    hi = thru or (today - dt.timedelta(days=1)).isoformat()
    exp = f'seasonId={SEASON} and gameTypeId=2 and gameDate<="{hi}"'
    url = ("https://api.nhle.com/stats/rest/en/goalie/summary?isAggregate=false&isGame=true&limit=-1&start=0"
           f"&cayenneExp={urllib.parse.quote(exp)}")
    rows = get(url).get("data", [])
    time.sleep(1.5)
    by, names = {}, {}
    for r in rows:
        if not r.get("gamesStarted") or not r.get("teamAbbrev"):
            continue
        by.setdefault(r["teamAbbrev"], []).append([str(r["gameDate"])[:10], r["gameId"], r["playerId"]])
        names[str(r["playerId"])] = r.get("goalieFullName") or ""
    return {t: [[g[0], g[2]] for g in sorted(v)] for t, v in by.items()}, names


def goalie_starts(log, today, thru=None):
    """The last 30 days of the goalie log (the site uses it to split a hurt goalie's starts among whoever is actually
    starting). Returns {team: [[date, nhlId], ...]}."""
    hi = thru or (today - dt.timedelta(days=1)).isoformat()
    lo = (dt.date.fromisoformat(hi) - dt.timedelta(days=29)).isoformat()
    return {t: [g for g in v if g[0] >= lo] for t, v in log.items() if any(g[0] >= lo for g in v)}


def recent_share(prior, starters, nid):
    """Start share with recent games weighted more (GD). starters = the team's starting goalie ids in game order."""
    n = len(starters)
    if not n:
        return prior
    num = den = 0.0
    for k, s in enumerate(reversed(starters)):
        wk = GD["d"] ** k
        den += wk
        if s == nid:
            num += wk
    return (GD["k"] * prior + num) / (GD["k"] + den)


def current_teams():
    """NHL id -> the team he's on now (the NHL's bios report). Players are traded after the board is built: without
    this the site kept Matthew Knies on Toronto's schedule six weeks after he went to Columbus, and Connor Hellebuyck
    in Winnipeg's net after his trade to New Jersey. Last season's report is read first so players who haven't
    played yet this season (injured) are covered too; this season's wins."""
    cur = {}
    prev = f"{int(SEASON[:4]) - 1}{SEASON[:4]}"
    for season in (prev, SEASON):
        for kind in ("skater", "goalie"):
            exp = urllib.parse.quote(f"seasonId={season} and gameTypeId=2")
            d = get(f"https://api.nhle.com/stats/rest/en/{kind}/bios?isAggregate=false&isGame=false&limit=-1&start=0&cayenneExp={exp}")
            time.sleep(1.5)
            for r in d.get("data", []):
                if r.get("currentTeamAbbrev"):
                    cur[r["playerId"]] = r["currentTeamAbbrev"]
    return cur


def goalie_plan(players, tm, glog):
    """What each goalie's start share should be measured against, now that goalies change teams and come back from
    injuries. Returns {board id: (prior share, the games that count as evidence, as a list of starter ids)}.
    - Prior: his preseason share, rescaled when his team's goalies changed (someone was traded in or out), so the
      team's goalies still add up to what the board gave that team (at most 97% of its games).
    - Evidence: his current team's starters, game by game, but only since the newest real arrival: a goalie with a
      20%+ share who first started for this team 3 or more games in because he was hurt in camp or came in a trade.
      Games before that say who played while he wasn't there, not how the net is split now. A lesser goalie who
      arrived late is judged only on games since his own first start."""
    G = [p for p in players if p["slot"] == "G" and p.get("gs") and p.get("gm") and p.get("pid")]
    cur = lambda p: tm.get(p["id"]) or p.get("t") or ""
    share = lambda p: p["gs"] / max(p["gm"], 1)
    board, now = {}, {}
    for p in G:
        board.setdefault(p.get("t") or "", []).append(p)
        now.setdefault(cur(p), []).append(p)
    plan = {}
    for t, group in now.items():
        old = board.get(t, [])
        prior = {p["id"]: share(p) for p in group}
        if {p["id"] for p in group} != {p["id"] for p in old} and old:
            target = min(0.97, sum(p["gs"] for p in old) / max(p["gm"] for p in old))
            tot = sum(prior.values())
            k = max(0.6, min(1.6, target / tot)) if tot > 0 else 1.0
            prior = {i: min(0.85, v * k) for i, v in prior.items()}
        starters = [g[1] for g in (glog or {}).get(t, [])]
        first, late = {}, {}
        for p in group:
            first[p["id"]] = starters.index(int(p["pid"])) if int(p["pid"]) in starters else None
            late[p["id"]] = first[p["id"]] is not None and first[p["id"]] >= 3 and bool(p.get("ret") or (p.get("t") or "") != t)
        r0 = max([first[p["id"]] for p in group if late[p["id"]] and prior[p["id"]] >= 0.2] or [0])
        for p in group:
            i0 = max(r0, first[p["id"]] if late[p["id"]] else 0)
            plan[p["id"]] = (prior[p["id"]], starters[i0:])
    return plan


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.replace("-", " ").replace(".", " "))).strip()


def injuries(players, today, old):
    """Injury report -> {board id: {s, ret, why, d}}. s: out, dtd, ir, ltir or susp.
    ret is the first day he can play. When the report's date has passed but he's still listed,
    we assume he's out through today. On a failed pull the last good list is kept."""
    try:
        d = get(INJ_URL, tries=3, ua=None)  # this feed turns away custom user agents
    except Exception as e:
        print("injury report unavailable, keeping the last one:", e, file=sys.stderr)
        return old.get("inj") or {}, old.get("injAt")
    by = {}
    for p in players:
        by.setdefault(norm(p["n"]), []).append(p)
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    out = {}
    for team in d.get("injuries", []):
        for it in team.get("injuries", []):
            a = it.get("athlete") or {}
            cands = by.get(norm(a.get("displayName", "")), [])
            ab = (a.get("team") or {}).get("abbreviation", "")
            ab = ESPN_TEAM.get(ab, ab)
            if len(cands) > 1:
                cands = [p for p in cands if p.get("t") == ab]
            if len(cands) != 1:
                continue
            p = cands[0]
            det = it.get("details") or {}
            fs = ((det.get("fantasyStatus") or {}).get("abbreviation") or "").upper()
            st = (it.get("status") or "").lower()
            kind = "susp" if ("suspens" in st or det.get("type") == "Suspension") else "dtd" if "day" in st else \
                "ltir" if fs == "IR-LT" else "ir" if (fs.startswith("IR") or "reserve" in st) else "out"
            rep = (it.get("date") or "")[:10] or today.isoformat()
            ret = (det.get("returnDate") or "")[:10] or None
            try:
                r0 = dt.date.fromisoformat(rep)
                if kind == "ir": ret = max(ret or "", (r0 + dt.timedelta(days=7)).isoformat())
                if kind == "ltir": ret = max(ret or "", (r0 + dt.timedelta(days=24)).isoformat())
            except ValueError:
                pass
            if kind != "dtd" and (not ret or ret <= today.isoformat()):
                ret = tomorrow
            why = det.get("type") or ""
            out[p["id"]] = {"s": kind, "ret": ret, "why": "" if why == "Suspension" else why, "d": rep}
    return out, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def main():
    raw = open(BOARD, encoding="utf-8").read()
    B = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    meta, players = B["meta"], B["players"]
    now = dt.datetime.now(dt.timezone.utc)
    today = dt.date.fromisoformat(os.environ["LIVE_TODAY"]) if os.environ.get("LIVE_TODAY") else now.astimezone(ET).date()
    out = {"generated": now.isoformat(timespec="seconds"), "season": SEASON, "players": {}, "started": False}
    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        old = {}
    out["inj"], out["injAt"] = injuries(players, today, old)
    print(f"injuries: {len(out['inj'])} board players listed")
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
    played = {}  # team -> dates of its games so far
    for d, idx in meta["sched"]["days"]:
        if d < today.isoformat():
            for i in idx:
                played.setdefault(teams[i], []).append(d)
    # testing hook: replay a past season's stats up to a date (LIVE_SEASON + LIVE_THROUGH)
    thru = os.environ.get("LIVE_THROUGH")
    s_hi = thru or None
    r_lo, r_hi = ((dt.date.fromisoformat(thru) - dt.timedelta(days=9)).isoformat(), thru) if thru else (d10, y)
    summ = nhl("skater", "summary", None, s_hi); rt = nhl("skater", "realtime", None, s_hi)
    fo = nhl("skater", "faceoffwins", None, s_hi); toi = nhl("skater", "timeonice", None, s_hi)
    recent = nhl("skater", "summary", r_lo, r_hi)
    gsum = nhl("goalie", "summary", None, s_hi); grecent = nhl("goalie", "summary", r_lo, r_hi)
    out["started"] = bool(summ)
    # who has changed NHL teams since the board was built: {board id: team now}
    try:
        cur_team = current_teams()
        tm = {p["id"]: cur_team[p["pid"]] for p in players if p.get("pid") and cur_team.get(p["pid"]) and cur_team[p["pid"]] != (p.get("t") or "")}
        print(f"teams: {len(tm)} players have moved since the board was built")
    except Exception as e:  # keep the last good list
        print("current teams skipped:", e)
        tm = old.get("tm") or {}
    out["tm"] = tm
    glog = None
    try:
        glog, out["gnm"] = goalie_log(today, thru)
        out["gst"] = goalie_starts(glog, today, thru)
        print(f"goalie starts: {sum(len(v) for v in glog.values())} games this season, {len(out['gnm'])} goalies")
    except Exception as e:  # optional: without it, start shares use the flat K=23.2 update
        print("goalie starts skipped:", e)
    gplan = goalie_plan(players, tm, glog)
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
        team = tm.get(p["id"]) or p.get("t") or ""
        rec = {}
        if p["slot"] == "G":
            if not p.get("gs") or not p.get("pts") or not p.get("gm"):
                continue
            s = gsum.get(nid)
            # a goalie who hasn't played at all: only update him if he's healthy and the log is in (a third-stringer's
            # share should shrink; a hurt goalie is handled by the injury report instead)
            if not s and (glog is None or p["id"] in out["inj"] or not glog.get(team)):
                continue
            s = s or {}
            starts = s.get("gamesStarted") or 0
            n_team = tg.get(team, 0)
            prior_share = p["gs"] / max(p["gm"], 1)
            prior_pps = p["pts"] / p["gs"]
            fp = 3 * (s.get("wins") or 0) + 0.25 * (s.get("saves") or 0) - (s.get("goalsAgainst") or 0) + 4 * (s.get("shutouts") or 0) + 3 * (s.get("goals") or 0) + 2 * (s.get("assists") or 0) + 0.5 * (s.get("penaltyMinutes") or 0)
            obs_pps = fp / starts if starts else prior_pps
            if glog is not None and glog.get(team) and p["id"] in gplan:
                share = recent_share(gplan[p["id"]][0], gplan[p["id"]][1], int(nid))
            else:
                share = (KG["share"] * prior_share + starts) / (KG["share"] + n_team) if n_team else prior_share
            pps = (KG["pps"] * prior_pps + starts * obs_pps) / (KG["pps"] + starts)
            mult = (share * pps) / (prior_share * prior_pps)
            rec = {"m": {"G": round(max(0.3, min(2.0, mult)), 4)}, "n": s.get("gamesPlayed") or 0, "gs": starts, "fp": round(fp, 1), "tg": n_team, "sh": round(share, 4)}
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
                    m[slot] = max(0.5, min(1.8, po / pr))
            gp10 = (recent.get(nid) or {}).get("gamesPlayed", 0)
            # playing time: only for players in the lineup lately (the injury report covers the ones who aren't)
            av, a0 = 1.0, min(1.0, gp0 / max(p.get("gm") or 82, 1))
            tgn = sum(1 for d in played.get(team, []) if not p.get("ret") or d >= p["ret"])
            if tgn >= 5 and a0 > 0 and gp10 > 0 and p["id"] not in out["inj"]:
                gpn = min(n, tgn)
                ka = KA["up"] if gpn / tgn >= a0 else KA["down"]
                pa = (ka * a0 + gpn) / (ka + tgn)
                av = max(0.5, min(2.2, min(pa, max(KA["cap"], a0)) / a0))
            # A raise multiplies his per-game projection, and for a player projected for few games that number is
            # shaky (a rookie's total came from where he was drafted, not from games). So a raise never lifts his
            # per-game projection more than 10% above what he has actually scored per game at that position.
            def raised(slot, v):
                a = av
                if a > 1 and n >= 8:
                    pgm = (p["slotpts"][slot] / gp0) * v
                    pgo = sum(w(slot, c) * tot[c] for c in CATS) / n
                    if pgm > 1.1 * pgo:
                        a = max(1.0, a * 1.1 * pgo / pgm)
                return round(max(0.4, min(2.5, v * a)), 4)
            m = {slot: raised(slot, v) for slot, v in m.items()}
            best = p["slot"] if p["slot"] in SK else next(iter(m), "W")
            fp = sum(w(best, c) * tot[c] for c in CATS)
            fps = {slot: round(sum(w(slot, c) * tot[c] for c in CATS), 1) for slot in m} if len(m) > 1 else None
            rec = {"m": m, "n": n, "fp": round(fp, 1), "toi": round(t_now, 1), "dtoi": round(dtoi, 2), "pp": round(pp_now, 2), "dpp": round(dpp, 2), "tg": tg.get(team, 0)}
            if fps:
                rec["fps"] = fps  # what he has scored at each position he can play (faceoffs only count at center)
            if abs(av - 1) >= 0.005:
                rec["av"] = round(av, 3)  # the playing-time part of m (m / av is the per-game part)
        # sitting out: his team played 3+ games in the last 10 days and he played none
        if tg10.get(team, 0) >= 3 and gp10 == 0:
            rec["out"] = tg10.get(team, 0)
        out["players"][p["id"]] = rec
        # on the preseason injury list but he has played since, and he's not on the report now: he's back
        if p.get("ret") and rec.get("n") and p["id"] not in out["inj"]:
            out.setdefault("back", []).append(p["id"])
    out["asOf"] = y
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print(f"live: {len(out['players'])} players updated through {y}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the site: keep the last good file
        print("refresh failed:", e, file=sys.stderr)
        sys.exit(1)
