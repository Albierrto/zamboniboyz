"""Assemble one row per player-season from the NHL stats reports."""
import json, pandas as pd
SEASONS = ["20212022", "20222023", "20232024", "20242025", "20252026"]
R = "data/raw/nhl"

def load(kind, rep, s):
    return pd.DataFrame(json.load(open(f"{R}/{kind}_{rep}_{s}.json")))

def skaters():
    out = []
    for s in SEASONS:
        a = load("skater", "summary", s)[["playerId", "skaterFullName", "positionCode", "teamAbbrevs", "gamesPlayed",
             "goals", "assists", "plusMinus", "penaltyMinutes", "shots", "timeOnIcePerGame", "ppPoints", "points"]]
        b = load("skater", "realtime", s)[["playerId", "hits", "blockedShots", "emptyNetGoals", "emptyNetAssists"]]
        c = load("skater", "faceoffwins", s)[["playerId", "totalFaceoffWins", "totalFaceoffs"]]
        d = load("skater", "timeonice", s)[["playerId", "ppTimeOnIcePerGame", "shTimeOnIcePerGame"]]
        e = load("skater", "bios", s)[["playerId", "birthDate", "currentTeamAbbrev", "draftOverall", "draftYear", "height", "weight"]]
        df = a.merge(b, on="playerId", how="left").merge(c, on="playerId", how="left").merge(d, on="playerId", how="left").merge(e, on="playerId", how="left")
        df["season"] = int(s[4:])  # season end year
        out.append(df)
    df = pd.concat(out, ignore_index=True)
    df = df.rename(columns={"gamesPlayed": "gp", "goals": "g", "assists": "a", "plusMinus": "pm", "penaltyMinutes": "pim",
                            "hits": "hit", "blockedShots": "blk", "totalFaceoffWins": "fow", "totalFaceoffs": "fo",
                            "timeOnIcePerGame": "toi", "ppTimeOnIcePerGame": "pptoi", "shTimeOnIcePerGame": "shtoi",
                            "skaterFullName": "name", "positionCode": "npos", "teamAbbrevs": "teams"})
    for col in ["hit", "blk", "fow", "fo"]:
        df[col] = df[col].fillna(0)
    df["toi"] /= 60; df["pptoi"] = df["pptoi"].fillna(0) / 60; df["shtoi"] = df["shtoi"].fillna(0) / 60
    return df

def goalies():
    out = []
    for s in SEASONS:
        a = load("goalie", "summary", s)[["playerId", "goalieFullName", "teamAbbrevs", "gamesPlayed", "gamesStarted", "wins",
             "saves", "shotsAgainst", "goalsAgainst", "shutouts", "goals", "assists", "penaltyMinutes", "timeOnIce"]]
        e = load("goalie", "bios", s)[["playerId", "birthDate", "currentTeamAbbrev", "draftOverall", "draftYear"]]
        df = a.merge(e, on="playerId", how="left"); df["season"] = int(s[4:]); out.append(df)
    df = pd.concat(out, ignore_index=True)
    return df.rename(columns={"goalieFullName": "name", "teamAbbrevs": "teams", "gamesPlayed": "gp", "gamesStarted": "gs",
                              "wins": "w", "saves": "sv", "shotsAgainst": "sa", "goalsAgainst": "ga", "shutouts": "so",
                              "goals": "g", "assists": "a", "penaltyMinutes": "pim"})

def team_context():
    """Per team-season: shots against / game, wins / game, goals against / game (from goalie rows)."""
    g = goalies()
    rows = []
    for s in SEASONS:
        t = load("goalie", "summary", s)
        # multi-team goalies have 'A, B' in teamAbbrevs; keep single-team rows for context
        t = t[~t.teamAbbrevs.str.contains(",")]
        agg = t.groupby("teamAbbrevs").agg(sa=("shotsAgainst", "sum"), ga=("goalsAgainst", "sum"), w=("wins", "sum"), gs=("gamesStarted", "sum"))
        agg["season"] = int(s[4:]); rows.append(agg.reset_index().rename(columns={"teamAbbrevs": "team"}))
    return pd.concat(rows, ignore_index=True)

if __name__ == "__main__":
    s = skaters(); g = goalies()
    s.to_pickle("data/skater_seasons.pkl"); g.to_pickle("data/goalie_seasons.pkl")
    team_context().to_pickle("data/team_context.pkl")
    print(s.shape, g.shape)
    print(s[s.season == 2026].sort_values("points", ascending=False).head(5)[["name", "gp", "g", "a", "fow", "hit", "blk", "toi", "pptoi"]])
