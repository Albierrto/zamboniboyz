"""Values, tiers, per-player cards -> site/data/board.js"""
import json, sys, datetime, numpy as np, pandas as pd
sys.path.insert(0, "build")
import model as M

T = 2027
ps = pd.read_pickle("data/final_skaters.pkl"); pg = pd.read_pickle("data/final_goalies.pkl"); rook = pd.read_pickle("data/rookies.pkl")
sk = pd.read_pickle("data/skater_seasons.pkl"); gl = pd.read_pickle("data/goalie_seasons.pkl")
league = json.load(open("data/raw/getLeagueInfo.json"))
import experts as EX, news as NEWS
from expertlab import norm as enorm
rosters = json.load(open("data/raw/getTeamRosters.json"))
draft = json.load(open("data/raw/getDraftResults.json"))
standings = json.load(open("data/raw/getStandings.json"))
adp = json.load(open("data/raw/adp.json"))

# ---- rookies: projection from ADP only ----
rook = rook[rook.adp < 250].copy()
e = ps[(ps.wgp >= 60) & ps.adp.notna() & ~ps.no_team]
b, a = np.polyfit(np.log(e.adp), e.proj_pts, 1)
eg = pg[(pg.x_gp >= 30) & pg.adp.notna() & ~pg.no_team]
bg, ag = np.polyfit(np.log(eg.adp), eg.proj_pts, 1)
rook["proj_pts"] = np.where(rook.pg == "G", ag + bg * np.log(rook.adp), a + b * np.log(rook.adp)).clip(0)
rook["proj_gp"] = np.nan

# ---- one table ----
S = ps.assign(kind="S"); G = pg.assign(kind="G", slots=[["G"]] * len(pg), best_slot="G")
R = rook.assign(kind=np.where(rook.pg == "G", "G", "S"))
R["slots"] = [s if k == "S" else ["G"] for s, k in zip(R.slots, R.kind)]
R["best_slot"] = [s[0] if len(s) else "W" for s in R.slots]
allp = pd.concat([S, G, R], ignore_index=True)
allp = allp[allp.proj_pts.notna()].copy()
allp["nm"] = [n if isinstance(n, str) else f for n, f in zip(allp["name"], allp.fname)]

# ---- 2026-27 schedule: 84 games, but the fantasy season ends with the last scoring period ----
SCHED = json.load(open("data/raw/sched/2027.json"))
PERIODS = league["scoringPeriods"]
def _ts(x):  # Fantrax "2026-10-05T18:59:59.0-0400" -> aware datetime
    return datetime.datetime.strptime(x.replace(".0", ""), "%Y-%m-%dT%H:%M:%S%z")
P_START, P_END = _ts(PERIODS[0]["startDate"]), _ts(PERIODS[-1]["endDate"])
def _gts(g): return datetime.datetime.fromisoformat(g["utc"].replace("Z", "+00:00"))
FGAMES = [g for g in SCHED if P_START <= _gts(g) <= P_END]
TG = {}
for g in FGAMES:
    for t in (g["home"], g["away"]): TG[t] = TG.get(t, 0) + 1
TG_AVG = float(np.mean(list(TG.values())))
print("fantasy-window games per team:", min(TG.values()), "-", max(TG.values()))
def missed(team, ret):
    if not isinstance(ret, str) or not isinstance(team, str) or not team: return 0
    return sum(1 for g in FGAMES if g["date"] < ret and team in (g["home"], g["away"]))
allp["tg"] = allp.team.map(lambda t: TG.get(t, TG_AVG) if isinstance(t, str) and t else TG_AVG)
allp["inj_ret"] = allp.nm.map(lambda n: NEWS.INJ.get(n, (None, None))[0])
allp["inj_note"] = allp.nm.map(lambda n: NEWS.INJ.get(n, (None, None))[1])
allp["miss"] = [missed(t, r) for t, r in zip(allp.team, allp.inj_ret)]
print("injured players matched:", int(allp.inj_ret.notna().sum()), "of", len(NEWS.INJ),
      "| missing:", sorted(set(NEWS.INJ) - set(allp.nm)))
# model numbers are on an 82-game scale: rescale to this team's fantasy games, minus known absences
fac = (allp.tg - allp.miss) / 82.0
lost_gs = np.where(allp.kind.eq("G"), allp.proj_gs.fillna(0) * allp.miss / 82.0, 0)
for c in ["proj_pts", "proj_gp", "proj_gs"]:
    allp[c] = allp[c] * fac
# a hurt or absent goalie's starts go to his healthy teammates
allp["gs_extra"] = 0.0
for i in allp.index[(lost_gs > 0.5)]:
    t = allp.at[i, "team"]
    mates = allp[(allp.kind == "G") & (allp.team == t) & (allp.index != i) & (allp.miss == 0) & allp.proj_gs.notna()]
    if not len(mates) or not t: continue
    share = mates.proj_gs / mates.proj_gs.sum()
    for j, sh in share.items():
        allp.at[j, "gs_extra"] += lost_gs[allp.index.get_loc(i)] * sh
g_m = allp.kind.eq("G") & (allp.gs_extra > 0) & (allp.proj_gs > 0)
per_start = allp.proj_pts / allp.proj_gs
allp.loc[g_m, "proj_pts"] = allp.loc[g_m, "proj_pts"] + allp.loc[g_m, "gs_extra"] * per_start[g_m]
allp.loc[g_m, "proj_gp"] = allp.loc[g_m, "proj_gp"] + allp.loc[g_m, "gs_extra"] / allp.loc[g_m, "gs_per_gp"]
allp.loc[g_m, "proj_gs"] = allp.loc[g_m, "proj_gs"] + allp.loc[g_m, "gs_extra"]
print("goalie starts moved to teammates:", allp.loc[g_m, ["nm", "team", "gs_extra"]].round(1).values.tolist())

# points at each slot for the season (skaters): scale per-slot ppg by the same blend factor
for s in ["C", "W", "D"]:
    col = "pts_" + s
    allp[col] = np.nan
    m = allp.kind.eq("S") & allp["ppg_" + s].notna()
    ratio = (allp.loc[m, "proj_pts"] / (allp.loc[m, "ppg"] * allp.loc[m, "proj_gp"])).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    allp.loc[m, col] = allp.loc[m, "ppg_" + s] * allp.loc[m, "proj_gp"] * ratio
allp["pts_G"] = np.where(allp.kind.eq("G"), allp.proj_pts, np.nan)
# rookies have no per-slot rates: same number at every eligible slot
for i, r in allp[allp.get("rookie", False) == True].iterrows():
    for s in r.slots:
        allp.at[i, "pts_" + s] = r.proj_pts

# ---- replacement level and value ----
REPL = {"C": 36, "W": 72, "D": 72, "G": 30}   # ~3 C, 6 W, 6 D, 2.5 G rostered per team (216 roster spots)

def assign(df, repl):
    best = []
    for i, r in df.iterrows():
        opts = [(r["pts_" + s] - repl[s], s) for s in r.slots if pd.notna(r["pts_" + s])]
        best.append(max(opts) if opts else (np.nan, None))
    df["value"] = [x[0] for x in best]; df["slot"] = [x[1] for x in best]

def solve_repl(df):
    repl = {"C": 0, "W": 0, "D": 0, "G": 0}
    for it in range(8):
        assign(df, repl)
        new = {}
        for s, n in REPL.items():
            pts = df.loc[df.slot == s, "pts_" + s].sort_values(ascending=False)
            new[s] = float(pts.iloc[n - 1]) if len(pts) >= n else 0.0
        done = all(abs(new[s] - repl[s]) < 0.5 for s in repl)
        repl = new
        if done: break
    assign(df, repl)
    return repl

# 1) goalie calibration: in the backtest, projected goalie totals were too spread out
#    (top goalies came in lower, depth goalies higher). Fit actual = a + b * projected.
CAL = dict(a=float(pg.cal_a.iloc[0]), b=float(pg.cal_b.iloc[0]))
import calibrate
_old = calibrate.goalie_fit()  # only for the page's "top 12 projected vs actual" note
CAL["top12_proj"], CAL["top12_act"] = float(pg.cal_t12p.iloc[0]), float(pg.cal_t12a.iloc[0])
print("goalie calibration: actual = %.1f + %.2f x projected" % (CAL["a"], CAL["b"]))
allp["pts_model_raw"] = np.where(allp.kind.eq("G"), allp.pts_G, np.nan)
allp["pts_G"] = np.where(allp.kind.eq("G"), CAL["a"] + CAL["b"] * allp.pts_G, np.nan)

# 2) blend with the analysts. Within each position, a player's analyst-consensus rank is turned into
#    points using this league's own scoring: the analysts' k-th goalie gets our k-th goalie's points.
#    Our model decides how much a position is worth here; the analysts help decide who is good
#    (depth charts, injuries, new teams, prospects). How far each player moves toward the analysts
#    was tested on four past seasons (build/expertlab.py, build/experts.py).
ADP_FLOOR = EX.ADP_FLOOR
solve_repl(allp)
for s_ in ["C", "W", "D", "G"]:
    allp["model_" + s_] = allp["pts_" + s_]
allp["prim"] = allp.slot
allp["k"] = allp.nm.map(enorm)
allp["rookie"] = allp.get("rookie", False).fillna(False).astype(bool) if "rookie" in allp else False
allp["moved"] = [(isinstance(t, str) and isinstance(l, str) and t != "" and t != l) for t, l in zip(allp.team, allp.get("team_last", pd.Series(index=allp.index)))]
allp["exp_score"], allp["exp_n"] = EX.consensus(allp, allp.kind.eq("G"))
allp["market_pts"] = np.nan
allp["market_rank_pos"] = np.nan
for s_ in ["C", "W", "D", "G"]:
    grp = allp[allp.prim == s_]
    ours = np.sort(grp["pts_" + s_].values)[::-1]
    ranked = grp[grp.exp_score.notna()].sort_values("exp_score")
    rest = grp[grp.exp_score.isna()].sort_values("pts_" + s_, ascending=False)
    for k, idx in enumerate(list(ranked.index) + list(rest.index)):
        allp.at[idx, "market_pts"] = ours[min(k, len(ours) - 1)]
    for k, idx in enumerate(ranked.index):
        allp.at[idx, "market_rank_pos"] = k + 1
allp["w_exp"] = EX.weights(allp)
inj = allp.miss > 0
allp.loc[inj & allp.kind.eq("S") & ~allp.rookie, "w_exp"] = allp.loc[inj & allp.kind.eq("S") & ~allp.rookie, "w_exp"].clip(upper=0.10)
allp.loc[inj & allp.kind.eq("G"), "w_exp"] = allp.loc[inj & allp.kind.eq("G"), "w_exp"].clip(upper=0.30)
own_pts = allp.apply(lambda r: r["pts_" + r.prim] if isinstance(r.prim, str) else np.nan, axis=1)
delta = allp.w_exp * (allp.market_pts - own_pts)
for s_ in ["C", "W", "D", "G"]:
    allp["pts_" + s_] = allp["pts_" + s_] + delta.where(allp["pts_" + s_].notna())
print("expert weights used:", allp.groupby(["kind"]).w_exp.describe()[["mean", "min", "max"]].round(2).to_dict("index"))
W_MODEL = {"C": 0.95, "W": 0.8, "D": 0.8, "G": 0.35}  # typical share kept from our own model (see experts.weights)

repl = solve_repl(allp)
print("replacement:", {k: round(v, 1) for k, v in repl.items()})
allp["proj_pts_final"] = allp.apply(lambda r: r["pts_" + r.slot], axis=1)
allp["model_pts_slot"] = allp.apply(lambda r: r["model_" + r.slot], axis=1)
allp = allp[allp.slot.notna()].sort_values("value", ascending=False).reset_index(drop=True)
allp["model_rank_pos"] = allp.groupby("slot").model_pts_slot.rank(ascending=False, method="first").astype(int)

# ---- owners (kept players) ----
teams = {k: v["name"] for k, v in league["teamInfo"].items()}
owner = {}
for tid, t in rosters["rosters"].items():
    for it in t["rosterItems"]:
        owner[it["id"]] = tid
allp["owner"] = allp.fid.map(owner)
print("kept players matched:", allp.owner.notna().sum(), "of", len(owner))
missing = set(owner) - set(allp.fid)
print("kept but not on board:", missing)

# ---- per-player history lines ----
skh = sk[sk.season >= 2024]; glh = gl[gl.season >= 2024]
def hist_s(pid, slot):
    out = []
    for _, r in skh[skh.playerId == pid].sort_values("season").iterrows():
        rates = {c: r[c] / r.gp for c in M.CATS} if r.gp else None
        fp = float(M.skater_ppg(pd.DataFrame([rates]), slot).iloc[0] * r.gp) if r.gp else 0
        out.append([f"{r.season-1}-{str(r.season)[2:]}", r.teams, int(r.gp), int(r.g), int(r.a), int(r.pm), int(r.pim), int(r.hit), int(r.blk),
                    int(r.fow), round(r.toi, 1), round(r.pptoi, 1), int(r.shots), round(fp)])
    return out
def hist_g(pid):
    out = []
    for _, r in glh[glh.playerId == pid].sort_values("season").iterrows():
        fp = 3 * r.w + 0.25 * r.sv - r.ga + 4 * r.so + 2 * r.a + 0.5 * r.pim
        out.append([f"{r.season-1}-{str(r.season)[2:]}", r.teams, int(r.gp), int(r.gs), int(r.w), int(r.sv), int(r.ga), int(r.so),
                    round(r.sv / r.sa, 3) if r.sa else None, round(fp)])
    return out

def chips(r):
    c = []  # (tone, text)  tone: good / bad / info
    if r.get("rookie") == True:
        c.append(("info", "No NHL track record yet. Projection comes from where drafters are taking him."))
    if r.no_team:
        c.append(("bad", "No NHL contract right now. Might not play in the NHL this season."))
    if r.kind == "S" and r.get("rookie") != True:
        gp = r.proj_gp
        if r.slot == "C" and r.fow * gp * 0.25 >= 50:
            c.append(("good", f"Faceoff machine: about {round(r.fow * gp * 0.25)} points a season just from faceoff wins."))
        if r.slot == "D" and r.ppg >= 2.0:
            c.append(("good", "Scoring defenseman. Every goal and assist is worth 4 points."))
        hb = (r.hit + r.blk) * gp * 0.25
        if hb >= 45:
            c.append(("good", f"Hits and blocks add about {round(hb)} points a season."))
        if r.pptoi >= 2.5:
            c.append(("good", f"Power-play regular: about {r.pptoi:.1f} minutes a game on the power play."))
        last = skh[(skh.playerId == r.playerId) & (skh.season == 2026)]
        if len(last) and last.iloc[0].shots >= 80:
            l = last.iloc[0]; lsh = l.g / l.shots; car = r.sh
            if lsh - car >= 0.035:
                c.append(("bad", f"Lucky finishing last season: scored on {lsh:.0%} of shots vs about {car:.0%} normally. Expect fewer goals."))
            elif car - lsh >= 0.03:
                c.append(("good", f"Unlucky finishing last season: scored on {lsh:.0%} of shots vs about {car:.0%} normally. Goals should bounce back."))
        if len(r.slots) > 1:
            pts = {s: r["pts_" + s] for s in r.slots if pd.notna(r["pts_" + s])}
            if len(pts) > 1:
                o = sorted(pts.items(), key=lambda x: -x[1])
                c.append(("info", f"Can play {' or '.join(r.slots)}. Worth about {round(o[0][1])} as a {o[0][0]} vs {round(o[1][1])} as a {o[1][0]}."))
        if 0 < r.gp_last < 65:
            c.append(("bad", f"Played only {int(r.gp_last)} games last season."))
    if r.kind == "G" and r.get("rookie") != True:
        c.append(("info", f"We project about {round(r.proj_gs)} starts for him."))
        if r.proj_gs >= 55: c.append(("good", "Clear starter. Workload is what wins goalie points here."))
        elif r.proj_gs < 35 and not r.no_team: c.append(("bad", "Shares the net or is a backup. Fewer starts means fewer points."))
        if r.gp_last and r.gp_last < 30 and r.proj_gs >= 40:
            c.append(("bad", f"Only {int(r.gp_last)} games last season."))
    if pd.notna(r.get("market_rank_pos")) and r.get("rookie") != True:
        pn = {"C": "center", "W": "winger", "D": "defenseman", "G": "goalie"}[r.slot]
        mr, orank = int(r.market_rank_pos), int(r.model_rank_pos)
        pull = "a lot" if r.w_exp >= 0.5 else "partway" if r.w_exp >= 0.3 else "a little" if r.w_exp >= 0.15 else "only slightly"
        if mr >= orank + 8 and mr > 6:
            c.append(("info", f"Our stats like him more than the analysts do: they have him around the {ordinal(mr)} {pn}, we have him {ordinal(orank)}. His number is pulled {pull} toward theirs."))
        elif orank >= mr + 8 and orank > 6:
            c.append(("info", f"Analysts like him more than our stats do: around the {ordinal(mr)} {pn} for them vs {ordinal(orank)} for us. His number is pulled {pull} toward theirs."))
    if isinstance(r.get("inj_note"), str):
        c.insert(0, ("bad", f"Injury: {r.inj_note} We take off about {int(r.miss)} games."))
    note = NEWS.NOTES.get(r.nm)
    if note:
        c.insert(0, ("info", "Camp news: " + note))
    if pd.notna(r.get("age")):
        if r.age >= 33: c.append(("bad", f"Age {int(r.age)} this season: some decline built in."))
        elif r.age <= 23 and r.get("rookie") != True: c.append(("good", f"Age {int(r.age)} this season: still improving, growth built in."))
    return c

def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

def rnd(x, n=1):
    return None if pd.isna(x) else round(float(x), n)

players = []
for i, r in allp.iterrows():
    kind = r.kind
    rookie = r.get("rookie") == True
    p = dict(id=r.fid, n=r["name"] if isinstance(r["name"], str) else r.fname, t=r.team or "", pos=r.elig, slot=r.slot,
             pts=rnd(r.proj_pts_final, 0), val=rnd(r.value, 0),
             mp=rnd(r.model_pts_slot, 0), mk=rnd(r.market_pts, 0),
             mr=None if pd.isna(r.market_rank_pos) else int(r.market_rank_pos), orank=int(r.model_rank_pos), adp=rnd(r.adp, 1), own=r.owner if isinstance(r.owner, str) else None,
             age=None if pd.isna(r.get("age")) else int(r.age), rk=1 if rookie else 0, nt=1 if r.no_team else 0,
             ch=chips(r))
    p["slotpts"] = {s: rnd(r["pts_" + s], 0) for s in r.slots if pd.notna(r["pts_" + s])}
    p["gm"] = int(round(r.tg - r.miss))          # team games he can play in the fantasy season
    if r.miss > 0:
        p["ret"] = r.inj_ret; p["miss"] = int(r.miss)
    p["wx"] = rnd(r.w_exp, 2)
    if kind == "S" and not rookie:
        gp = r.proj_gp; blend = r.proj_pts_final / (r.ppg * gp) if r.ppg * gp else 1
        sc = M.SK[r.slot]
        p["gp"] = rnd(gp, 0)
        p["line"] = dict(g=rnd(r.g * gp, 0), a=rnd(r.a * gp, 0), pm=rnd(r.pm * gp, 0), pim=rnd(r.pim * gp, 0), hit=rnd(r.hit * gp, 0),
                         blk=rnd(r.blk * gp, 0), fow=rnd(r.fow * gp, 0), sog=rnd(r.shots * gp, 0), toi=rnd(r.toi, 1), pptoi=rnd(r.pptoi, 1))
        brk = {"Goals": sc["g"] * r.g, "Assists": sc["a"] * r.a, "Faceoff wins": sc["fow"] * r.fow, "Hits": 0.25 * r.hit,
               "Blocks": 0.25 * r.blk, "Plus/minus": r.pm, "Penalty minutes": 0.5 * r.pim, "Hat tricks": 3 * M.p_hat_trick(r.g)}
        p["brk"] = {k: rnd(v * gp * blend, 0) for k, v in brk.items() if abs(v * gp) >= 0.5}
        p["hist"] = hist_s(r.playerId, r.slot)
        p["pid"] = int(r.playerId)
    elif kind == "G" and not rookie:
        gp = r.proj_gp; blend = r.proj_pts_final / (r.ppg * gp) if r.ppg * gp else 1
        p["gp"] = rnd(gp, 0); p["gs"] = rnd(r.proj_gs, 0)
        p["gppg"] = rnd(r.proj_pts_final / gp if gp else r.ppg, 3); p["gpg"] = rnd(r.gs_per_gp, 3)
        p["line"] = dict(w=rnd(r.w_pg * gp, 0), sv=rnd(r.sv_pg * gp, 0), ga=rnd(r.ga_pg * gp, 0), so=rnd(r.so_pg * gp, 1), svp=rnd(r.sv_pct, 3))
        brk = {"Wins": 3 * r.w_pg, "Saves": 0.25 * r.sv_pg, "Goals against": -r.ga_pg, "Shutouts": 4 * r.so_pg, "Assists": 2 * r.a_pg}
        p["brk"] = {k: rnd(v * gp * blend, 0) for k, v in brk.items()}
        p["hist"] = hist_g(r.playerId)
        p["pid"] = int(r.playerId)
    players.append(p)

# keep the board a sensible size: everything kept, on the ADP list, or with value above -60
players = [p for p in players if p["own"] or p["adp"] is not None or (p["val"] is not None and p["val"] > -60)]
# tiers by value
def tier(v):
    if v is None: return 6
    return 1 if v >= 120 else 2 if v >= 80 else 3 if v >= 50 else 4 if v >= 20 else 5 if v >= 0 else 6
for p in players: p["tier"] = tier(p["val"])
print("players exported:", len(players))

meta = dict(
    built=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    leagueId="fbmei87xmo5yu9ni", leagueName=league["leagueName"], season="2026-27",
    teams=[dict(id=k, name=v["name"], short=next((m[s]["shortName"] for mm in league["matchups"] for m in mm["matchupList"] for s in ("home", "away") if m[s]["id"] == k), "")) for k, v in league["teamInfo"].items()],
    picks=[[p["round"], p["pick"], p["teamId"], p.get("playerId")] for p in draft["draftPicks"]],
    draftDate=draft.get("draftDate"),
    roster=dict(C=2, W=4, D=4, G=2, bench=6, max=18),
    repl={k: round(v, 1) for k, v in repl.items()},
    replN=REPL, wModel=W_MODEL, gcal=dict(a=round(CAL["a"], 1), b=round(CAL["b"], 2), top12_proj=round(CAL["top12_proj"]), top12_act=round(CAL["top12_act"])),
    scoring=dict(C=M.SK["C"], W=M.SK["W"], D=M.SK["D"], common=M.COMMON, goalie=M.GOALIE),
    periods=len(league["scoringPeriods"]), playoffTeams=league["playoffs"]["numPlayoffTeams"],
    firstPlayoff=league["playoffs"]["firstPlayoffPeriod"], seasonStart=league["startDate"],
    defaultTeam="nuevz47fmo5yu9nr",
)
meta["backtest"] = json.load(open("data/report.json"))
TIDX = sorted(TG)
days = {}
for g in FGAMES:
    days.setdefault(g["date"], []).extend([TIDX.index(g["home"]), TIDX.index(g["away"])])
meta["sched"] = dict(teams=TIDX, days=[[d, sorted(v)] for d, v in sorted(days.items())])
meta["periodDates"] = [[pp["number"], pp["startDate"], pp["endDate"]] for pp in PERIODS]
meta["matchups"] = [[m["period"], [[x["away"]["id"], x["home"]["id"]] for x in m["matchupList"]]] for m in league["matchups"]]
meta["experts"] = dict(sources=EX.SOURCES_TEXT, asOf=NEWS.AS_OF, n=len(EX.SOURCES_TEXT))
meta["newsAsOf"] = NEWS.AS_OF
meta["expTest"] = json.load(open("data/expert_report.json"))
meta["adpNote"] = "Fantrax average draft position across all Fantrax NHL drafts, as of " + datetime.date.today().isoformat()
import os; os.makedirs("site/data", exist_ok=True)
with open("site/data/board.js", "w") as f:
    f.write("window.BOARD=" + json.dumps(dict(meta=meta, players=players), separators=(",", ":"), ensure_ascii=False) + ";\n")
print("board.js bytes:", os.path.getsize("site/data/board.js"))
