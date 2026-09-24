"""Camp news that changes projections, as of 2026-09-24 (sources in data/raw/experts/2026/news.md).

INJ: expected return date (first game he can play). Games his team plays before that date count as missed.
When the timeline is a range we use the middle. Day-to-day players are left out.
NOTES: short facts shown on player cards.
"""
AS_OF = "2026-09-24"

INJ = {
    # name: (return date, note)
    "Connor Bedard": ("2026-11-12", "Shoulder surgery in July. About 4 months, so back around mid-November (NHL.com)."),
    "Brad Marchand": ("2026-11-01", "Offseason surgery. Misses the start; RotoWire says November."),
    "Seth Jarvis": ("2026-11-20", "Shoulder surgery in June, 4-6 months. Ahead of schedule but not cleared (NHL.com, Sep 17)."),
    "Troy Terry": ("2026-11-15", "Hip surgery in June. Out until at least November."),
    "Yanni Gourde": ("2026-12-01", "Hip surgery. Out until December."),
    "Kevin Fiala": ("2026-10-28", "Leg fractures at the Olympics. Expected back before Nov 1."),
    "Tyler Seguin": ("2026-10-06", "Coming back from a torn ACL. May miss the opener."),
    "Frederik Andersen": ("2026-10-27", "Knee. Could be out until late October (TSN)."),
    "Matt Savoie": ("2026-10-25", "Training injury. Expected back in October."),
    "Filip Gustavsson": ("2026-10-14", "Hip surgery. Out at least the first couple of weeks."),
    "Thatcher Demko": ("2026-10-20", "Coming back from hip surgery. Limited in camp, no return date."),
    "Max Domi": ("2026-12-15", "Failed his physical after surgery. Out indefinitely."),
    "Mathew Barzal": ("2026-10-14", "Aggravated an old injury. Two weeks off skates."),
    "Nick Bjugstad": ("2027-02-01", "Torn pectoral. 4-6 months."),
    "Rasmus Sandin": ("2026-12-15", "ACL surgery in April. 6-9 months."),
    "Alex Pietrangelo": ("2027-04-06", "Hip. Listed injured with no timeline; we assume he doesn't play."),
    "Adam Sykora": ("2027-02-01", "Lower body. 4-5 months."),
    "Kaiden Guhle": ("2026-10-24", "Adductor surgery. 4-5 weeks."),
    "Jason Zucker": ("2026-10-15", "Sports hernia. Misses the start."),
    "Mattias Samuelsson": ("2026-10-12", "Lower body. Week to week."),
    "Artem Zub": ("2026-10-10", "Knee. About 1-2 weeks."),
    "Warren Foegele": ("2026-10-10", "Undisclosed. About 1-2 weeks."),
    "Dominic James": ("2026-10-08", "Broken hand. About 2 weeks."),
    "Elvis Merzlikins": ("2026-11-20", "Failed his physical. Not back in the near future."),
    "Connor Hellebuyck": ("2026-11-15", "Asked for a trade and is suspended for not reporting (TSN, Sep 17). We assume he misses about the first six weeks, wherever he ends up."),
    "Dan Vladar": ("2026-10-03", "Upper body, day to day. Opener not guaranteed."),
    "Olen Zellweger": ("2026-10-06", "Possible concussion in a preseason game."),
}

NOTES = {
    # Folsom Flyers
    "Jack Hughes": "Camp: 2nd-line center with Bratt and Mantha, top power play. Has played 61-62 games in each of the last three seasons (Daily Faceoff, Sep 23).",
    "William Nylander": "Camp: with Tavares and No. 1 pick McKenna, top power play (NHL.com, MLHS, Sep 17-19).",
    "Artemi Panarin": "Traded to LA in February. Camp: top line with Byfield and Kempe, top power play (LA Kings Insider, Sep 22).",
    "Brayden Point": "Top line with Kucherov, top power play. Scored on 14% of shots last season vs about 21% normally, so analysts expect more goals (RotoWire, Sep 15).",
    "MacKenzie Weegar": "Traded to Utah in March. Top pair with Sergachev, not on the top power play. Huge on hits, blocks and PIM, but was -33 last season.",
    "Matthew Knies": "Camp: top line with Matthews, but on the second power-play unit at the Sep 19 practice (THN, MLHS).",
    "Jacob Trouba": "Signed with San Jose. Top-four pair; rookie Cagnoni has the top power-play spot (NHL.com, Sep 22). His value is hits and blocks.",
    "Jordan Kyrou": "Traded to Washington. Camp: 3rd line with the Protas brothers and the 2nd power play, not with Ovechkin (RMNB, THN, Sep 17-19). Analysts still call him a bounce-back pick.",
    "Alex Lyon": "Buffalo plans to split the net with Luukkonen rather than name a starter (WGR via CBS, Sep 16).",
    "Seth Jones": "Broken foot has healed and he's practicing. 2nd pair; Ekblad has the top power play for now (CBS, Sep 17).",
    "Dylan Cozens": "Camp: 2nd-line center and the net-front man on the top power play, Brady Tkachuk's old job (THN, Sep 23). 215 hits last season.",
    "Igor Shesterkin": "Clear starter, but the Rangers look weaker, which limits wins (Daily Faceoff).",
    "Miro Heiskanen": "Top pair. Ran the top power play last season (28 PP points), but Harley is competing for it and it isn't confirmed yet.",
    "Logan Cooley": "Camp: 2nd-line center and on the top power play early in camp (Hockey Bangers, Sep 23). NHL.com calls him primed to break out.",
    "Brandon Montour": "2nd pair in Seattle; power-play role not confirmed. Was -21 last season.",
    "Trevor Zegras": "Listed as the 2nd-line center (NHL.com, Sep 23) and on the power-play unit being tested as the top one. Won only 34% of faceoffs last season.",
    "Travis Sanheim": "Top pair with Ristolainen; rotates on the power play. Blocks are his value (152 last season).",
    "Gabriel Vilardi": "Top line with Connor and Scheifele. Very few hits. Winnipeg's net is unsettled while Hellebuyck is out.",
    # goalies
    "Stuart Skinner": "Starting for Winnipeg while Hellebuyck is out.",
    "Sergei Bobrovsky": "Signed with Toronto as the starter.",
    "Jacob Markstrom": "Traded to Florida as the starter. Backup Schmid is a popular sleeper.",
    "Brandon Bussi": "Carolina's new starter. Kochetkov could push him into a split (RotoWire, Sep 24).",
    "Jesper Wallstedt": "Minnesota's starter to open the season with Gustavsson hurt; a popular breakout pick.",
    "Joel Hofer": "Listed as St. Louis's starter over Binnington (NHL.com).",
    "Scott Wedgewood": "Colorado is expected to split the net with Blackwood.",
    "Mackenzie Blackwood": "Colorado is expected to split the net with Wedgewood.",
    "Ukko-Pekka Luukkonen": "Buffalo plans to split the net with Lyon.",
    "Jake Allen": "New Jersey calls its net a '1a, 1b, 1c' with Daws and Rittich.",
    "Yaroslav Askarov": "Listed as San Jose's starter, but the Sharks may rotate goalies.",
    "Arturs Silovs": "Pittsburgh looks like a rotation with Murashov.",
    # skaters with new roles
    "Gavin McKenna": "No. 1 pick. On the Tavares-Nylander line, second power play to start.",
    "Porter Martone": "Top line and power play in Philadelphia; the consensus top rookie.",
    "Brady Tkachuk": "Traded to Florida, on Barkov's line.",
    "Chris Kreider": "Signed with Montreal; top line with Suzuki and Caufield in camp.",
    "Quinton Byfield": "Top-line center with Panarin and Kempe; one of the most-picked breakouts (NHL.com, RotoWire).",
    "Connor McDavid": "Coach Babcock has McDavid and Draisaitl on the same line in camp.",
    "Leon Draisaitl": "Coach Babcock has McDavid and Draisaitl on the same line in camp.",
    "John Carlson": "Signed with Tampa; expected to take the top power play from Hedman.",
    "Victor Hedman": "Expected to drop to the second power play behind Carlson (RotoWire, Sep 24).",
    "Darren Raddysh": "Toronto's top power-play quarterback. Analysts flag last season's shooting luck.",
    "Patrick Kane": "Back in Chicago, on a line with Nazar and Kantserov while Bedard is out.",
    "Dylan Larkin": "Asked for a trade in June; upper-body injury, progressing.",
    "Vincent Trocheck": "Traded to Utah; second power play early in camp.",
    "Mavrik Bourque": "Traded to Nashville; centering Forsberg and Wood. A popular breakout pick.",
    "Bowen Byram": "Traded to Chicago; top pair and top power play in preseason.",
    "Roman Kantserov": "Led the KHL with 36 goals; top line and top power play in Chicago's camp.",
}


# Camp roles that differ from last season (ice time and power-play minutes a game).
# name: (expected TOI, expected PP TOI, confidence 0-1, note). Confidence < 1 because camp lines move.
# Counting stats scale with the change: goals/assists 75% by ice time and 25% by power-play time;
# faceoffs, hits and blocks by ice time. Once games start, the refresh job uses real ice time instead.
ROLE = {
    "Anton Lundell": (16.0, 1.2, 0.8, "Barkov is healthy again, so Lundell drops back to third-line center (with Luostarinen and Vilmanis in camp, The Hockey News, Sep 18-20). Last season's top-line minutes came from Barkov's injury."),
    "Sam Bennett": (17.3, 2.4, 0.8, "With Barkov back, Bennett returns to second-line center (with Verhaeghe and Matthew Tkachuk in camp, The Hockey News, Sep 18-20)."),
    "Jordan Kyrou": (14.8, 1.4, 0.6, "Third line and second power-play unit in Washington's camp, not the top six (RMNB, THN, Sep 17-19)."),
    "Matthew Knies": (18.5, 1.4, 0.6, "Top line, but on the second power-play unit at the Sep 19 practice (THN, MLHS)."),
    "Victor Hedman": (21.0, 1.5, 0.6, "Expected to drop to the second power play behind John Carlson (RotoWire, Sep 24)."),
    "Dylan Cozens": (17.5, 3.0, 0.6, "Net-front man on Ottawa's top power play, Brady Tkachuk's old job (THN, Sep 23)."),
}
