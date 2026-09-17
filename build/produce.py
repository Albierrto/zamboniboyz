"""Build the 2026-27 ZamboniBoyz draft data: projections, Fantrax ids, eligibility, ADP, keepers, values."""
import json, re, sys, unicodedata, numpy as np, pandas as pd
sys.path.insert(0, "build")
import model as M

T = 2027
RAW = "data/raw"
sk = pd.read_pickle("data/skater_seasons.pkl")
gl = pd.read_pickle("data/goalie_seasons.pkl")
league = json.load(open(f"{RAW}/getLeagueInfo.json"))
rost = json.load(open(f"{RAW}/getTeamRosters.json"))["rosters"]
fx = json.load(open(f"{RAW}/nhl_ids.json"))
adp = json.load(open(f"{RAW}/adp.json"))

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", " ").replace(".", ""))
    return re.sub(r"\s+", " ", s).strip()

ALIAS = {"alex": "alexander", "alexandre": "alexander", "mitch": "mitchell", "matt": "matthew", "mike": "michael",
         "zach": "zachary", "josh": "joshua", "nick": "nicholas", "nicolas": "nicholas", "jake": "jacob", "sam": "samuel",
         "dan": "daniel", "danny": "daniel", "will": "william", "tim": "timothy", "tony": "anthony", "jon": "jonathan",
         "cam": "cameron", "chris": "christopher", "fred": "frederick", "freddie": "frederick", "joe": "joseph",
         "max": "maxim", "vince": "vincent", "pat": "patrick", "ben": "benjamin", "andy": "andrew", "steve": "stephen",
         "jt": "jt", "tj": "tj", "pk": "pk", "ej": "ej", "zack": "zachary", "johnny": "john", "jonny": "john",
         "maxime": "maxim", "max": "maxim", "evgeni": "evgeny", "evgenii": "evgeny", "yegor": "egor", "matvey": "matvei"}
NAME_FIX = {"mats zuccarello aasen": "mats zuccarello"}
def key(name):
    n = norm(name); n = NAME_FIX.get(n, n)
    parts = n.split(" ")
    if not parts: return ""
    parts[0] = ALIAS.get(parts[0], parts[0])
    return " ".join(parts)

# ---------- projections ----------
ps = M.project_skaters(sk, T)
pg = M.project_goalies(gl, T, M.GP_)  # team crowding applied after Fantrax teams are known

# ---------- Fantrax players ----------
fxp = []
for fid, v in fx.items():
    nm = v.get("name", "")
    if ", " in nm:
        last, first = nm.split(", ", 1); full = f"{first} {last}"
    else:
        full = nm
    fxp.append(dict(fid=fid, fname=full, fteam=v.get("team"), fpos=v.get("position"), k=key(full), last=norm(full).split(" ")[-1] if full else ""))
fxp = pd.DataFrame(fxp)
elig = {k: v["eligiblePos"] for k, v in league["playerInfo"].items()}
fxp["elig"] = fxp.fid.map(elig)
fxp = fxp[fxp.elig.notna()]  # players in this league's player pool
fxp["isG"] = fxp.elig.str.contains("G")

def match(proj, goalie):
    proj = proj.copy()
    proj["k"] = proj.name.map(key)
    proj["last"] = proj.name.map(lambda s: norm(s).split(" ")[-1])
    pool = fxp[fxp.isG == goalie]
    out = {}
    used = set()
    for i, r in proj.iterrows():
        cands = pool[pool.k == r.k]
        if len(cands) == 0:
            # last name + team fallback, then last name + first initial
            c2 = pool[(pool["last"] == r["last"]) & (pool.fteam == r.cur_team)]
            if len(c2) == 1: cands = c2
            else:
                c3 = pool[(pool["last"] == r["last"]) & (pool.k.str[0] == r.k[0])]
                if len(c3) == 1: cands = c3
        if len(cands) > 1 and not goalie:
            isd = cands.elig.str.contains("D")
            c3b = cands[isd] if r.pg == "D" else cands[~cands.elig.isin(["D"])]
            if len(c3b) >= 1: cands = c3b
        if len(cands) > 1:
            c4 = cands[cands.fteam == r.cur_team]
            if len(c4) >= 1: cands = c4
        if len(cands) > 1:
            c5 = cands[cands.fteam.notna() & (cands.fteam != "(N/A)")]
            if len(c5) >= 1: cands = c5
        if len(cands) >= 1:
            out[i] = cands.iloc[0].fid
    proj["fid"] = pd.Series(out)
    # one Fantrax id -> one NHL player: keep the one whose team agrees (else the most recent)
    m = proj[proj.fid.notna()].merge(pool[["fid", "fteam"]], on="fid", how="left").set_axis(proj[proj.fid.notna()].index)
    m["agree"] = (m.fteam == m.cur_team).astype(int)
    m = m.sort_values(["agree", "last_season", "wgp" if "wgp" in m else "x_gp"], ascending=False)
    drop = m[m.fid.duplicated(keep="first")].index
    proj.loc[drop, "fid"] = None
    return proj

ps = match(ps, False); pg = match(pg, True)
print("skaters matched", ps.fid.notna().sum(), "/", len(ps), " goalies", pg.fid.notna().sum(), "/", len(pg))
unm = ps[ps.fid.isna() & (ps.gp_last >= 20)]
print("unmatched regulars:", unm[["name", "cur_team", "gp_last"]].to_string()[:1500])
ps.to_pickle("data/proj_skaters.pkl"); pg.to_pickle("data/proj_goalies.pkl"); fxp.to_pickle("data/fx_players.pkl")

# ---------- attach Fantrax info ----------
fxi = fxp.set_index("fid")
def attach(d):
    d = d[d.fid.notna()].copy()
    d["elig"] = d.fid.map(fxi.elig); d["fteam"] = d.fid.map(fxi.fteam); d["fname"] = d.fid.map(fxi.fname)
    d["no_team"] = d.fteam.isna() | (d.fteam == "(N/A)")
    d["team"] = np.where(d.no_team, d.cur_team.fillna(""), d.fteam)
    d.loc[d.no_team, "team"] = ""
    return d
ps = attach(ps); pg = attach(pg)

# goalie crowding on the goalie's 2026-27 team (Fantrax)
pg = pg.reset_index(drop=True)
pg = M.allocate_starts(pg, pd.Series(np.where(pg.no_team, None, pg.team)), M.GP_["cap"], M.GP_["gamma"], incumbent=M.GP_["inc"])

# points per game at each eligible slot
for slot in ["C", "W", "D"]:
    ps["ppg_" + slot] = M.skater_ppg(ps, slot)
def slots(e): return [x for x in str(e).split(",") if x in ("C", "W", "D")]
ps["slots"] = ps.elig.map(slots)
ps = ps[ps.slots.map(len) > 0].copy()
ps["best_slot"] = ps.apply(lambda r: max(r.slots, key=lambda s: r["ppg_" + s]), axis=1)
ps["ppg"] = ps.apply(lambda r: r["ppg_" + r.best_slot], axis=1)
ps["proj_pts"] = ps.ppg * ps.proj_gp

# ---------- ADP ----------
adp_map = {a["id"]: a["ADP"] for a in adp}
ps["adp"] = ps.fid.map(adp_map); pg["adp"] = pg.fid.map(adp_map)

def adp_curve(d, minw, wcol):
    e = d[(d[wcol] >= minw) & d.adp.notna() & ~d.no_team]
    b, a = np.polyfit(np.log(e.adp), e.proj_pts, 1)
    return lambda x: np.maximum(a + b * np.log(x), 0)
sk_curve = adp_curve(ps, 60, "wgp"); g_curve = adp_curve(pg, 30, "x_gp")

# players on the ADP list with no NHL history (rookies, returning players)
have = set(ps.fid) | set(pg.fid)
rook = []
for a_ in adp:
    if a_["id"] in have: continue
    f = fxi.loc[a_["id"]] if a_["id"] in fxi.index else None
    if f is None: continue
    isg = "G" in str(f.elig)
    rook.append(dict(fid=a_["id"], name=f.fname, fname=f.fname, elig=f.elig, fteam=f.fteam, team="" if f.fteam in (None, "(N/A)") else f.fteam,
                     no_team=f.fteam in (None, "(N/A)"), adp=a_["ADP"], pg="G" if isg else None, rookie=True,
                     slots=[] if isg else slots(f.elig), wgp=0.0, x_gp=0.0))
rook = pd.DataFrame(rook)
print("ADP players with no NHL history:", len(rook), rook[["name", "elig", "team", "adp"]].head(15).to_string())

# blend limited-history projections toward what their ADP implies
def blend(d, wcol, lim, curve):
    w = (1 - d[wcol].fillna(0) / lim).clip(0, 1)
    has = d.adp.notna()
    implied = curve(d.adp.fillna(999))
    d["adp_implied"] = np.where(has, implied, np.nan)
    d["proj_pts_model"] = d.proj_pts
    d.loc[has, "proj_pts"] = (1 - w[has]) * d.proj_pts[has] + w[has] * implied[has]
    return d
ps = blend(ps, "wgp", 40, sk_curve); pg = blend(pg, "x_gp", 25, g_curve)

# no NHL contract right now: most of these will not play in the NHL this season
ps.loc[ps.no_team, "proj_pts"] *= 0.25; pg.loc[pg.no_team, "proj_pts"] *= 0.25

ps.to_pickle("data/final_skaters.pkl"); pg.to_pickle("data/final_goalies.pkl"); rook.to_pickle("data/rookies.pkl")

