"""One row per player-season, 2010-11 to 2025-26, with usage and on-ice context."""
import json, os, pandas as pd, numpy as np
R = "data/raw/nhl"
SEASONS = [f"{y}{y+1}" for y in range(2010, 2026)]
SEASON_GAMES = {2013: 48, 2020: 70, 2021: 56}   # lockout / pandemic seasons (2019-20 teams played 68-71)

def load(kind, rep, s):
    fn = f"{R}/{kind}_{rep}_{s}.json"
    return pd.DataFrame(json.load(open(fn))) if os.path.exists(fn) else None

def skaters():
    out = []
    for s in SEASONS:
        a = load("skater", "summary", s)
        if a is None: continue
        a = a[["playerId", "skaterFullName", "positionCode", "teamAbbrevs", "gamesPlayed", "goals", "assists", "plusMinus",
               "penaltyMinutes", "shots", "timeOnIcePerGame", "ppPoints", "points", "ppGoals"]]
        parts = [a]
        for rep, cols in [("realtime", ["hits", "blockedShots"]), ("faceoffwins", ["totalFaceoffWins", "totalFaceoffs"]),
                          ("timeonice", ["ppTimeOnIcePerGame", "shTimeOnIcePerGame", "evTimeOnIcePerGame"]),
                          ("bios", ["birthDate", "currentTeamAbbrev", "draftOverall", "draftYear", "height", "weight"]),
                          ("goalsForAgainst", ["evenStrengthGoalsFor", "powerPlayGoalFor", "shortHandedGoalsFor", "evenStrengthGoalsAgainst"]),
                          ("scoringpergame", ["totalPrimaryAssists"]),
                          ("percentages", ["shootingPct5v5", "skaterSavePct5v5", "satPercentage", "zoneStartPct5v5"])]:
            d = load("skater", rep, s)
            if d is None:
                d = pd.DataFrame({"playerId": a.playerId})
            for c in cols:
                if c not in d: d[c] = np.nan
            parts.append(d[["playerId"] + cols].drop_duplicates("playerId"))
        df = parts[0]
        for p in parts[1:]:
            df = df.merge(p, on="playerId", how="left")
        df["season"] = int(s[4:])
        out.append(df)
    df = pd.concat(out, ignore_index=True)
    df = df.rename(columns={"gamesPlayed": "gp", "goals": "g", "assists": "a", "plusMinus": "pm", "penaltyMinutes": "pim",
                            "hits": "hit", "blockedShots": "blk", "totalFaceoffWins": "fow", "totalFaceoffs": "fo",
                            "timeOnIcePerGame": "toi", "ppTimeOnIcePerGame": "pptoi", "shTimeOnIcePerGame": "shtoi",
                            "evTimeOnIcePerGame": "evtoi", "skaterFullName": "name", "positionCode": "npos", "teamAbbrevs": "teams",
                            "totalPrimaryAssists": "a1", "shootingPct5v5": "oish", "skaterSavePct5v5": "oisv",
                            "satPercentage": "cf", "zoneStartPct5v5": "ozs"})
    for c in ["hit", "blk", "fow", "fo"]:
        df[c] = df[c].fillna(0)
    for c in ["toi", "pptoi", "shtoi", "evtoi"]:
        df[c] = df[c].fillna(0) / 60
    df["oigf"] = df[["evenStrengthGoalsFor", "powerPlayGoalFor", "shortHandedGoalsFor"]].sum(axis=1, min_count=1)
    df["slen"] = df.season.map(SEASON_GAMES).fillna(82)
    df["share"] = (df.gp / df.slen).clip(upper=1.0)
    return df

def goalies():
    out = []
    for s in SEASONS:
        a = load("goalie", "summary", s)
        if a is None: continue
        a = a[["playerId", "goalieFullName", "teamAbbrevs", "gamesPlayed", "gamesStarted", "wins", "saves", "shotsAgainst",
               "goalsAgainst", "shutouts", "goals", "assists", "penaltyMinutes", "timeOnIce"]]
        e = load("goalie", "bios", s)[["playerId", "birthDate", "currentTeamAbbrev"]]
        df = a.merge(e.drop_duplicates("playerId"), on="playerId", how="left"); df["season"] = int(s[4:]); out.append(df)
    df = pd.concat(out, ignore_index=True).rename(columns={
        "goalieFullName": "name", "teamAbbrevs": "teams", "gamesPlayed": "gp", "gamesStarted": "gs", "wins": "w",
        "saves": "sv", "shotsAgainst": "sa", "goalsAgainst": "ga", "shutouts": "so", "goals": "g", "assists": "a", "penaltyMinutes": "pim"})
    df["slen"] = df.season.map(SEASON_GAMES).fillna(82)
    df["team"] = df.teams.str.split(",").str[-1].str.strip()
    return df

def teams(g):
    """Team-season context from goalie rows: shots against, goals against, wins per game."""
    x = g[~g.teams.str.contains(",")]
    t = x.groupby(["season", "team"]).agg(sa=("sa", "sum"), ga=("ga", "sum"), w=("w", "sum"), gs=("gs", "sum")).reset_index()
    t["sa_pg"] = t.sa / t.gs; t["ga_pg"] = t.ga / t.gs; t["w_pg"] = t.w / t.gs
    return t

if __name__ == "__main__":
    s = skaters(); g = goalies()
    s.to_pickle("data/sk_all.pkl"); g.to_pickle("data/gl_all.pkl"); teams(g).to_pickle("data/team_all.pkl")
    print(s.groupby("season").size().to_dict())
    print("dups", s.duplicated(["playerId", "season"]).sum(), g.duplicated(["playerId", "season"]).sum())
    print(s[["oigf", "a1", "oish", "cf", "pptoi"]].isna().mean().round(3).to_dict())
