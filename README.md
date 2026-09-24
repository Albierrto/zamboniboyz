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
- `news.py`: camp injuries (expected return dates) and short sourced notes, as of the date in the file. Games before a return date are removed using the real schedule, and a hurt goalie's starts go to his teammates.
- Season length: 84 NHL games, but the Fantrax season ends Apr 5, so each team's count (80-82) comes from the schedule.
