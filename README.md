# ZamboniBoyz Hockey

In-season tools for the ZamboniBoyz Fantrax hockey league (2026-27): projections built for this league's scoring and blended with analyst rankings, your weekly matchup night by night, and the best pickups. (It was the draft room until the Sep 20 draft.)

**Site:** https://albierrto.github.io/zamboniboyz/

- `docs/` is the website (GitHub Pages, branch `main`, folder `/docs`). `docs/data/board.js` holds the projections. Bump the `?v=` on the script tags after every rebuild.
- The page reads Fantrax's public league API (`fxea/general/getTeamRosters`, `getPlayerIds`) straight from the browser every few minutes. It is read-only and needs no keys.
- The 2026-27 NHL schedule (`api-web.nhle.com/v1/club-schedule-season/{TEAM}/20262027`) is saved to `data/raw/sched/2027.json` and baked into `board.js`.

## Rebuilding `board.js`
```
python build/fetch.py && python build/fetch2.py   # NHL stats 2010-11 to 2025-26 -> data/raw/nhl
# Fantrax (leagueId=fbmei87xmo5yu9ni): save getLeagueInfo, getTeamRosters, getDraftResults, getStandings,
#   getPlayerIds?sport=NHL (-> nhl_ids.json) and getAdp?sport=NHL (-> adp.json) into data/raw/
python build/assemble.py && python build/assemble2.py
python -c "import sys; sys.path.insert(0,'build'); import lab as L, lab2 as L2, pandas as pd; df=L.load(); pd.to_pickle(L2.build_all(df, range(2014,2027)), 'data/lab_frames.pkl')"
python -c "import sys; sys.path.insert(0,'build'); import glab2 as G; import pandas as pd; pd.to_pickle({T: G.frame(T) for T in range(2012,2027)}, 'data/glab_frames.pkl')"
python build/lab4.py      # skater test run (writes data/lab_v2_frames.pkl)
python build/report.py    # accuracy numbers shown on the page -> data/report.json
python build/expert_report.py   # analyst-vs-model test numbers -> data/expert_report.json
python build/produce.py
python build/export.py    # -> site/data/board.js (copy to docs/data/)
```

## Method (all tested out of sample)
- `lab.py`: step 1, weighted and shrunk three-season rates (`V1`), plus the evaluation harness.
- `lab2.py` / `lab4.py`: step 2, gradient-boosted corrections to each stat and to games played (average of 3 models), trained on 2013-14 to 2025-26.
- `glab.py` / `glab2.py`: goalies. Ridge corrections for starts (age, save %, teammates) and points per game (the new team's win rate and shots against), then calibration.
- `marketlab.py`: how much to blend in where drafters take players. It was tested against published preseason rankings, which are not included in this repo.
- `tune.py` / `tune2.py`: parameter searches. `project2.py`: 2026-27 projections.
- `expertlab.py` / `expert_report.py` / `experts.py`: the analyst blend. Four past seasons of preseason rankings (Daily Faceoff, Razzball, The Hockey News, FantraxHQ, theScore, a multi-site consensus) were scored against what happened in this league's scoring to decide how far each kind of player moves toward the analysts (young/new-team/short-history skaters 35%, other skaters 20%, centers 5%, goalies 65%, rookies 60%). The 2026-27 consensus uses Daily Faceoff (Larkin, Seguin, Bondy), NHL.com, RotoBaller, Razzball, CBS, Apples & Ginos projections re-scored for this league, and Fantrax ADP. The ranking lists themselves are not in this repo.
- `news.py`: camp injuries (expected return dates) and short sourced notes, as of the date in the file (the refresh job adds newer injuries on top). Games before a return date are removed using the real schedule, and a hurt goalie's starts go to his teammates.
- Season length: 84 NHL games, but the Fantrax season ends Apr 5, so each team's count (80-82) comes from the schedule.

## Automatic in-season refresh
`.github/workflows/refresh.yml` runs `build/live.py` every 3 hours overnight and about hourly from late morning to evening Eastern (and on demand from the Actions tab). It pulls 2026-27 season-to-date stats from `api.nhle.com/stats/rest` and writes `docs/data/live.json`: per-player multipliers on the preseason points-per-game, breakout-chance inputs, and "not playing lately" flags.

Injuries (every run, preseason included): ESPN's public NHL injury report (`site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries`) is matched to board players by name (team breaks ties) and stored as `inj: {id: {s, ret, why, d}}` with s = out, dtd, ir, ltir or susp and ret = expected return (IR at least 7 days, LTIR 24 days from the report; a player still listed past his date is out through the next day). Only those facts are kept, not the report's write-ups. On the page, the return date is the later of this and `news.py`; players from `news.py` who have played a game since and are off the report are listed in `back` and cleared. A goalie hurt beyond the preseason list hands his share of starts to his healthy teammates on the nights he's out. A player on Fantrax IR opens a roster spot: pickups need no drop until he's back, and the gain counts the drop that his return forces. The page reads it from `raw.githubusercontent.com` (so it doesn't wait for a Pages build), falling back to `docs/data/live.json`. Don't hand-upload `live.json`; the job owns it.

How fast early numbers count was tuned on 2021-22..2025-26 (`build/fetch_splits.py`, `build/inseason_lab.py`, `build/inseason_goalies.py`): each stat's projection is worth K games of evidence (goals 82, assists 70, +/- 106, PIM 134, hits 18, blocks 35, faceoff wins 8), plus +0.043 points a game per extra minute of ice time and +0.033 per extra power-play minute. Goalies: starts share K = 23 team games, points per start K = 54 starts.

## Value and waiver level
A player's value on the board is his season projection minus today's waiver level at his best position: the average of the three best healthy free agents there, worked out in the browser from the live Fantrax rosters (so it moves as players are added and dropped). Next-season keeper and pick math keeps the preseason level (`meta.repl`, the Nth-best player at each position), since that is what next year's waivers look like. Pickup cards also say why a player helps your team: how many of his games would make your lineup, at which position, and whose starts he takes (a player who projects below the best free agents can still help most by playing two positions or filling nights your lineup is short).

## Trades (keeper league)
- League rules that drive it (rulebook + Fantrax settings): keep exactly 7 (1 C, 2 W, 2 D, 1 G, 1 more skater); 11-round draft, worst to best every round (no snake), round-1 lottery among the 5 non-playoff teams (30/25/20/15/10); 2027 picks tradeable (`getDraftPicks`); no adds in the playoffs; trade deadline Feb 23.
- Next-season value: points per team game x 82 x an age factor minus waiver level. `build/keeperlab.py` measured the factor on 2014-15..2024-25 (players with 20+ games the year before, next-year totals incl. zeros): quadratic in age for skaters (+4% at 21, -2% at 27, -8% at 30, -17% at 33), goalie bands (-11% at 26-31). Leave-one-season-out: MAE 68.7 -> 66.3, rank correlation 0.56 -> 0.63.
- Pick values: this year's draft, each pick's projected points above waiver level, fitted v(n) = A e^(-bn) + c (`build/keepers_meta.py`, into `meta.pickCurve`). Each 2027 pick is valued at its likely slot from 4,000 simulated final standings with the lottery; a team counts only its best 11 picks.
- A trade's value to a team = change in this season's night-by-night lineup points + w x (change in its best keeper group + change in its picks), w = 0.15 / 0.5 / 1 for This season / Both / Next season. Every team is first given up to three free-agent swaps it could make anyway (`effAll`), so trades only get credit for what waivers can't give.
- Name-value check is one way: the other team must get at least 80% of what it sends (experts' value above waiver level for the rest of this season plus half of next, to the power 1.5; picks at half their value).
- Deal desk: sell (who needs him, best packages from every team), buy (packages from your roster they'd take), analyze (ledger: this season / keepers / picks), to even it, market gaps.

## Breakouts
`build/breakoutlab2.py` / `build/breakout2.py` / `build/breakout2_inseason.py`: breakout = a skater beats his own projection by 30% or more and finishes at or above waiver level. Pool: projected 40+ and below 1.2x waiver level. Gradient-boosted trees on 9 seasons (leave-one-season-out AUC 0.72; top 30 a season broke out 26% vs a 12% base rate), stacked with the analysts' view (4 seasons), then recalibrated with a bend at 22% because the top end was overconfident (preseason, nobody tests much above 1 in 4). In season the odds move with the projection: logit(p) += 17.25 x ln(multiplier) x n/(n+5); tested on 5 seasons, players at 40%+ about 10 games in broke out 48% of the time (55% at 20 games) vs 32% (43%) for chasing a hot start. Run breakout2.py, then breakout2_inseason.py, then export.py.
