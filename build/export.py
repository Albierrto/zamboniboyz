"""Values, tiers, per-player cards -> site/data/board.js"""
import json, sys, datetime, numpy as np, pandas as pd
sys.path.insert(0, "build")
import model as M

T = 2027
ps = pd.read_pickle("data/final_skaters.pkl"); pg = pd.read_pickle("data/final_goalies.pkl"); rook = pd.read_pickle("data/rookies.pkl")
sk = pd.read_pickle("data/skater_seasons.pkl"); gl = pd.read_pickle("data/goalie_seasons.pkl")
league = json.load(open("data/raw/getLeagueInfo.json"))
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

# points at each slot for the season (skaters): scale per-slot ppg by the same blend factor
for s in ["C", "W", "D"]:
    col = "pts_" + s
    allp[col] = np.nan
    m = allp.kind.eq("S") & allp["ppg_" + s].notna()
    ratio = allp.loc[m, "proj_pts"] / (allp.loc[m, "ppg"] * allp.loc[m, "proj_gp"])
    allp.loc[m, col] = allp.loc[m, "ppg_" + s] * allp.loc[m, "proj_gp"] * ratio
allp["pts_G"] = np.where(allp.kind.eq("G"), allp.proj_pts, np.nan)
# rookies have no per-slot rates: same number at every eligible slot
for i, r in allp[allp.get("rookie", False) == True].iterrows():
    for s in r.slots:
        allp.at[i, "pts_" + s] = r.proj_pts

# ---- replacement level and value ----
REPL = {"C": 36, "W": 72, "D": 72, "G": 36}
repl = {"C": 0, "W": 0, "D": 0, "G": 0}
for it in range(6):
    best = []
    for i, r in allp.iterrows():
        opts = [(r["pts_" + s] - repl[s], s) for s in r.slots if pd.notna(r["pts_" + s])]
        best.append(max(opts) if opts else (np.nan, None))
    allp["value"] = [x[0] for x in best]; allp["slot"] = [x[1] for x in best]
    new = {}
    for s, n in REPL.items():
        pts = allp.loc[allp.slot == s, "pts_" + s].sort_values(ascending=False)
        new[s] = float(pts.iloc[n - 1]) if len(pts) >= n else 0.0
    if all(abs(new[s] - repl[s]) < 0.5 for s in repl): repl = new; break
    repl = new
print("replacement:", {k: round(v, 1) for k, v in repl.items()})
best = []
for i, r in allp.iterrows():
    opts = [(r["pts_" + s] - repl[s], s) for s in r.slots if pd.notna(r["pts_" + s])]
    best.append(max(opts) if opts else (np.nan, None))
allp["value"] = [x[0] for x in best]; allp["slot"] = [x[1] for x in best]
allp = allp[allp.slot.notna()].sort_values("value", ascending=False).reset_index(drop=True)

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
    if pd.notna(r.get("age")):
        if r.age >= 33: c.append(("bad", f"Age {int(r.age)} this season: some decline built in."))
        elif r.age <= 23 and r.get("rookie") != True: c.append(("good", f"Age {int(r.age)} this season: still improving, growth built in."))
    return c

def rnd(x, n=1):
    return None if pd.isna(x) else round(float(x), n)

players = []
for i, r in allp.iterrows():
    kind = r.kind
    rookie = r.get("rookie") == True
    p = dict(id=r.fid, n=r["name"] if isinstance(r["name"], str) else r.fname, t=r.team or "", pos=r.elig, slot=r.slot,
             pts=rnd(r.proj_pts, 0), val=rnd(r.value, 0), adp=rnd(r.adp, 1), own=r.owner if isinstance(r.owner, str) else None,
             age=None if pd.isna(r.get("age")) else int(r.age), rk=1 if rookie else 0, nt=1 if r.no_team else 0,
             ch=chips(r))
    p["slotpts"] = {s: rnd(r["pts_" + s], 0) for s in r.slots if pd.notna(r["pts_" + s])}
    if kind == "S" and not rookie:
        gp = r.proj_gp; blend = r.proj_pts / (r.ppg * gp) if r.ppg * gp else 1
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
        gp = r.proj_gp; blend = r.proj_pts / (r.ppg * gp) if r.ppg * gp else 1
        p["gp"] = rnd(gp, 0); p["gs"] = rnd(r.proj_gs, 0)
        p["gppg"] = rnd(r.proj_pts / gp if gp else r.ppg, 3); p["gpg"] = rnd(r.gs_per_gp, 3)
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
    scoring=dict(C=M.SK["C"], W=M.SK["W"], D=M.SK["D"], common=M.COMMON, goalie=M.GOALIE),
    periods=len(league["scoringPeriods"]), playoffTeams=league["playoffs"]["numPlayoffTeams"],
    firstPlayoff=league["playoffs"]["firstPlayoffPeriod"], seasonStart=league["startDate"],
    defaultTeam="bx8lngpymo5yu9nq",
)
import backtest as B, backtest_g as BG
nv = B.naive(); md = B.evaluate(M.P)
gn = BG.ev(None, naive=True); gm = BG.ev(M.GP_)
meta["backtest"] = dict(
    skaters=dict(naive=dict(ppg=round(nv.mae_ppg, 2), tot=round(nv.mae_tot300), rho=round(nv.rho300, 2)),
                 model=dict(ppg=round(md.mae_ppg, 2), tot=round(md.mae_tot300), rho=round(md.rho300, 2))),
    goalies=dict(naive=dict(ppg=round(gn.mae_ppg, 2), tot=round(gn.mae_tot60), rho=round(gn.rho60, 2)),
                 model=dict(ppg=round(gm.mae_ppg, 2), tot=round(gm.mae_tot60), rho=round(gm.rho60, 2))),
    seasons="2023-24, 2024-25 and 2025-26")
meta["adpNote"] = "Fantrax average draft position across all Fantrax NHL drafts, as of " + datetime.date.today().isoformat()
import os; os.makedirs("site/data", exist_ok=True)
with open("site/data/board.js", "w") as f:
    f.write("window.BOARD=" + json.dumps(dict(meta=meta, players=players), separators=(",", ":"), ensure_ascii=False) + ";\n")
print("board.js bytes:", os.path.getsize("site/data/board.js"))
