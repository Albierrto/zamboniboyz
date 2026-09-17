# ZamboniBoyz Draft Room

Draft board for the ZamboniBoyz Fantrax hockey league (2026-27): projections built for this league's scoring, live pick tracking from Fantrax, and who to take next.

**Site:** https://albierrto.github.io/zamboniboyz/

- `docs/` is the website (GitHub Pages, branch `main`, folder `/docs`). `docs/data/board.js` holds the projections.
- The page reads Fantrax's public league API (`fxea/general/getDraftResults`, `getTeamRosters`, `getPlayerIds`) straight from the browser. It is read-only and needs no keys.
- `build/` rebuilds `board.js`:
  ```
  python build/fetch.py      # NHL stats 2021-22 to 2025-26 -> data/raw/nhl
  # Fantrax: save getLeagueInfo, getTeamRosters, getDraftResults, getStandings (leagueId=fbmei87xmo5yu9ni),
  #          getPlayerIds?sport=NHL (-> nhl_ids.json) and getAdp?sport=NHL (-> adp.json) into data/raw/
  python build/assemble.py
  python build/produce.py
  python build/export.py     # -> site/data/board.js (copy to docs/data/)
  ```
- `build/backtest.py` and `build/backtest_g.py` score the method on 2023-24, 2024-25 and 2025-26 using only earlier seasons.
