/* ZamboniBoyz Hockey. Read-only: this page only reads Fantrax's public league API. */
(function () {
"use strict";
const B = window.BOARD, META = B.meta;
const FX = "https://www.fantrax.com/fxea/general/";
const REPL = META.repl;
const CAP = { C: META.roster.C, W: META.roster.W, D: META.roster.D, G: META.roster.G };
const BENCH = META.roster.bench;
const POSNAME = { C: "Center", W: "Wing", D: "Defense", G: "Goalie" };
const POSPL = { C: "centers", W: "wingers", D: "defensemen", G: "goalies" };
const TIER = { 1: "Elite", 2: "Great", 3: "Very good", 4: "Solid", 5: "Depth", 6: "Waiver level" };
const OLD_DEFAULT = "bx8lngpymo5yu9nq";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const fmt = (x, d = 0) => (x == null || isNaN(x) ? "–" : Number(x).toFixed(d));
const sgn = (x) => (x == null || isNaN(x) ? "–" : (Math.round(x) > 0 ? "+" : Math.round(x) < 0 ? "−" : "") + Math.abs(Math.round(x)));

const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

const TEAMS = {}; META.teams.forEach((t) => (TEAMS[t.id] = t));
const tname = (id) => (TEAMS[id] ? TEAMS[id].name : "Unknown team");
const tshort = (id) => (TEAMS[id] ? (TEAMS[id].name.length > 18 && TEAMS[id].short ? TEAMS[id].short : TEAMS[id].name) : "?");
const PL = new Map(); B.players.forEach((p) => PL.set(p.id, p));
let EXTRA = null; // Fantrax name list for rostered players who aren't on the board

// the draft is over: start everyone on the new default team once (the picker still switches teams)
function startTeam() {
  let t = LS.get("zb-team", "");
  if (!LS.get("zb-season", false)) { if (!t || t === OLD_DEFAULT) t = META.defaultTeam; LS.set("zb-season", true); LS.set("zb-team", t); }
  return TEAMS[t] ? t : META.defaultTeam;
}
const TABS = ["team", "trades", "adds", "board", "league", "how"];
function startTab() {  // everyone lands on My team once after the draft; after that the last tab is remembered
  if (!LS.get("zb-home1", false)) { LS.set("zb-home1", true); LS.set("zb-tab", "team"); return "team"; }
  const t = LS.get("zb-tab", "team"); return TABS.includes(t) ? t : "team";
}
const S = {
  team: startTeam(),
  tab: startTab(),
  pos: "ALL", q: "", faOnly: LS.get("zb-fa", false), sort: "ros", show: 60, open: null,
  tmode: ["both", "me", "yes", "weak"].includes(LS.get("zb-tmode", "both")) ? LS.get("zb-tmode", "both") : "both", tteam: "ALL",
  addMode: LS.get("zb-addmode", "ros"), addPos: "ALL", addOpen: null, addShow: 25,
  stars: LS.get("zb-stars", {}),
  gsOv: LS.get("zb-gs", {}),       // goalie id -> season starts
  leagueOpen: {},
  live: { owners: null, status: null, at: null, err: null, fails: 0 },
  lastSig: "",
};

/* ---------------- dates and schedule ---------------- */
const ET = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" });
const todayET = () => ET.format(new Date());
const dLabel = (d, o) => new Date(d + "T12:00:00").toLocaleDateString([], o || { weekday: "short", month: "short", day: "numeric" });
const SCH = META.sched.teams;
const DAYS = META.sched.days.map(([d, idx]) => ({ d, teams: new Set(idx.map((i) => SCH[i])) }));
const SEASON_START = DAYS[0].d, SEASON_END = DAYS[DAYS.length - 1].d;
const PERIODS = META.periodDates.map(([n, s, e]) => ({ n, s: s.slice(0, 10), e: e.slice(0, 10) }));
function periodOf(d) {
  for (let i = 0; i < PERIODS.length; i++) {
    const p = PERIODS[i], last = i === PERIODS.length - 1;
    if (d >= p.s && (d < p.e || (last && d <= p.e))) return p;
  }
  return d < PERIODS[0].s ? PERIODS[0] : PERIODS[PERIODS.length - 1];
}
function daysIn(from, to) { return DAYS.filter((x) => x.d >= from && x.d <= to); }
function periodDays(p) { const last = p.n === PERIODS[PERIODS.length - 1].n; return DAYS.filter((x) => x.d >= p.s && (x.d < p.e || (last && x.d <= p.e))); }
function lastDayOf(p) { const ds = periodDays(p); return ds.length ? ds[ds.length - 1].d : p.s; }
function fromDay() { const t = todayET(); return t < SEASON_START ? SEASON_START : t; }
function opponentOf(team, n) {
  const m = META.matchups.find((x) => x[0] === n);
  if (!m) return null;
  for (const [a, h] of m[1]) { if (a === team) return h; if (h === team) return a; }
  return null;
}
const isPlayoffs = (n) => n >= META.firstPlayoff;
function agoText(t) {
  if (!t) return "never";
  const s = Math.round((Date.now() - t) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

/* ---------------- players ---------------- */
function player(id) {
  if (PL.has(id)) return PL.get(id);
  const x = EXTRA && EXTRA[id];
  const nm = x ? (x.name.includes(", ") ? x.name.split(", ").reverse().join(" ") : x.name) : "Player " + id;
  const pos = x ? ({ LW: "W", RW: "W" }[x.position] || x.position || "W") : "W";
  return { id, n: nm, t: x && x.team && x.team !== "(N/A)" ? x.team : "", pos, slot: pos, pts: null, val: null, tier: 6, ch: [], slotpts: {}, gm: 0, unknown: true };
}
function elig(p) {
  let e = EC.get(p.id);
  if (!e) { e = elig0(p); EC.set(p.id, e); }
  return e;
}
function elig0(p) {
  if (p.slot === "G") return ["G"];
  const k = Object.keys(p.slotpts || {});
  if (!k.length) return [p.slot];
  return k.sort((a, b) => (p.slotpts[b] - REPL[b]) - (p.slotpts[a] - REPL[a]));
}
function gsOf(p) { return S.gsOv[p.id] != null ? S.gsOv[p.id] : p.gs; }
function ptsOf(p) {
  if (p.slot === "G" && S.gsOv[p.id] != null && p.gpg) return (p.gppg * S.gsOv[p.id]) / p.gpg;
  return p.pts;
}
function ptsAt(p, s) {
  if (s === "G") return ptsOf(p);
  return p.slotpts && p.slotpts[s] != null ? p.slotpts[s] : p.pts;
}
// points per team game at a slot (0 before he's back from injury).
// MKT.on = score players the way the analysts see them (used for "would they see it as fair?")
const MKT = { on: false };
let LIVE = null; // docs/data/live.json: season-to-date updates written by the refresh job
function liveOf(p) { return (LIVE && LIVE.players && LIVE.players[p.id]) || null; }
function liveMult(p) { const l = liveOf(p); if (!l || !l.m) return null; const v = l.m[p.slot] ?? Object.values(l.m)[0]; return v == null ? null : v; }
// breakout chance: preseason model, updated by how much his projection has moved since (tested on 5 past seasons)
function boP(p) {
  if (!p.bo) return null;
  const p0 = Math.min(0.97, Math.max(0.01, p.bo[0]));
  const l = liveOf(p), m = liveMult(p);
  let z = Math.log(p0 / (1 - p0));
  if (l && m && l.n) z += META.breakout.chg * Math.log(m) * (l.n / (l.n + 5));
  return 1 / (1 + Math.exp(-z));
}
function trendTag(p) {
  const l = liveOf(p), m = liveMult(p);
  if (!l || !m || !l.n || l.n < 3) return "";
  const why = [];
  if (l.dtoi >= 1) why.push(`+${l.dtoi.toFixed(1)} min ice time`);
  if (l.dpp >= 0.5) why.push(`+${l.dpp.toFixed(1)} min power play`);
  if (l.dtoi <= -1) why.push(`${l.dtoi.toFixed(1)} min ice time`);
  if (m >= 1.08) return `<span class="pill good" title="${esc(why.join(", ") || "Scoring above his projection so far")}">Trending up ${Math.round(100 * (m - 1))}%</span>`;
  if (m <= 0.92) return `<span class="pill bad" title="${esc(why.join(", ") || "Scoring below his projection so far")}">Trending down ${Math.round(100 * (1 - m))}%</span>`;
  return "";
}
function outTag(p) { const l = liveOf(p); return l && l.out ? `<span class="pill bad" title="His team played ${l.out} games in the last 10 days and he played none">Not playing lately</span>` : ""; }
const RC = new Map(), EC = new Map();
function clearCaches() { MEMO.clear(); RC.clear(); EC.clear(); GL.clear(); }
function rateAt(p, s) {
  const k = p.id + s + (MKT.on ? "m" : "");
  let r = RC.get(k);
  if (r === undefined) {
    const x = ptsAt(p, s);
    r = p.gm > 0 && x != null ? x / p.gm : 0;
    const lv = LIVE && LIVE.players && LIVE.players[p.id];
    if (lv && lv.m && lv.m[s] != null) r *= lv.m[s];
    if (MKT.on && p.mk != null && p.pts > 0 && !p.rk) r *= p.mk / p.pts;
    RC.set(k, r);
  }
  return r;
}
function bestRate(p) { return Math.max(0, ...elig(p).map((s) => rateAt(p, s))); }
function plays(p, day) { return !!p.t && day.teams.has(p.t) && (!p.ret || day.d >= p.ret); }
const GL = new Map();
function gamesLeft(p, from) {
  const k = p.t + "|" + (p.ret || "") + "|" + from + (GBM.has(p.id) ? "|" + p.id : "");
  if (!GL.has(k)) GL.set(k, DAYS.reduce((a, x) => a + (x.d >= from && plays(p, x) ? gMult(p, x) : 0), 0));
  return GL.get(k);
}
function gamesIn(p, days) { return days.reduce((a, x) => a + (plays(p, x) ? 1 : 0), 0); }
// rest-of-season points (the whole season before it starts)
function rosAt(p, s) { return rateAt(p, s) * gamesLeft(p, fromDay()); }
function rosOf(p) { return p.slot === "G" ? rosAt(p, "G") : Math.max(0, ...elig(p).map((s) => rosAt(p, s))); }
function valOf(p) {
  if (p.val == null) return null;
  if (p.slot === "G") return ptsOf(p) - REPL.G;
  return p.val;
}
function tierOf(v) { return v == null ? 6 : v >= 120 ? 1 : v >= 80 ? 2 : v >= 50 ? 3 : v >= 20 ? 4 : v >= 0 ? 5 : 6; }
function face(p, cls = "face") {
  const ini = esc((p.n || "?").split(" ").map((w) => w[0]).slice(0, 2).join(""));
  if (!p.pid) return `<div class="${cls} ph" aria-hidden="true">${ini}</div>`;
  return `<img class="${cls}" loading="lazy" alt="" src="https://assets.nhle.com/mugs/nhl/latest/${p.pid}.png" onerror="this.outerHTML='<div class=&quot;${cls} ph&quot;>${ini}</div>'">`;
}
function ordinal(n) { const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" })[n % 10] || "th"; return n + s; }
function posBadge(p) { return `<span class="pos">${esc((p.pos || p.slot).replace(/,/g, "/"))}</span>`; }
function hurt(p) { return !!(p.ret && todayET() < p.ret); }
// ESPN's NHL injury report, pulled by the refresh job several times a day (live.json "inj"): status, expected return, body part.
// It sits on top of the preseason news list; players from that list who have played since are cleared ("back").
const INJWORD = { out: "Out", dtd: "Day-to-day", ir: "Injured reserve", ltir: "Long-term injured reserve", susp: "Suspended" };
const IR_SLOTS = 4;
function injOf(p) { return (LIVE && LIVE.inj && LIVE.inj[p.id]) || null; }
function dtd(p) { const x = injOf(p); return !!(x && x.s === "dtd" && (!p.ret0 || p.ret === x.ret)); }
function injWhat(p) { const x = injOf(p); return x ? `${INJWORD[x.s] || "Out"}${x.why && x.why !== "Undisclosed" ? `, ${x.why.toLowerCase()}` : ""}` : "Hurt"; }
function missedGames(p) { return p.ret ? DAYS.filter((d) => d.d >= fromDay() && d.d < p.ret && d.teams.has(p.t)).length : 0; }
function injTag(p, short) {
  const when = p.ret ? dLabel(p.ret, { month: "short", day: "numeric" }) : "";
  const x = injOf(p), word = x && x.s === "susp" ? "Suspended" : "Hurt";
  if (dtd(p)) return `<span class="pill gold" title="${esc(injWhat(p))}: may miss a game${hurt(p) && missedGames(p) ? ` (the report expects him back ${esc(when)})` : ""}. Check the news before starting him.">Day-to-day</span>`;
  if (hurt(p)) return `<span class="pill bad" title="${esc(injWhat(p))}${when ? `. Expected back around ${esc(when)}` : ""}">${short ? word : `${word} until ${esc(when)}`}</span>`;
  return "";
}
function applyInjuries() {
  const inj = (LIVE && LIVE.inj) || {}, back = new Set((LIVE && LIVE.back) || []);
  for (const p of B.players) {
    if (p.ret0 === undefined) p.ret0 = p.ret || null;
    let r = back.has(p.id) ? null : p.ret0;
    const x = inj[p.id];
    if (x && x.ret && (!r || x.ret > r)) r = x.ret;
    if (r) p.ret = r; else delete p.ret;
  }
  buildGoalieBoost();
}
// a goalie hurt after the preseason build: on the nights he's out, his starts go to his healthy teammates
let GBM = new Map();
function buildGoalieBoost() {
  GBM = new Map();
  const byTeam = {};
  for (const p of B.players) if (p.slot === "G" && p.t && p.gm > 0 && p.gs > 0) (byTeam[p.t] = byTeam[p.t] || []).push(p);
  const t0 = todayET();
  for (const [t, gs] of Object.entries(byTeam)) {
    const late = gs.filter((g) => g.ret && (!g.ret0 || g.ret > g.ret0));
    if (!late.length) continue;
    for (const day of DAYS) {
      if (day.d < t0 || !day.teams.has(t)) continue;
      const lost = late.filter((g) => day.d < g.ret && (!g.ret0 || day.d >= g.ret0)).reduce((a, g) => a + g.gs / g.gm, 0);
      if (!lost) continue;
      const healthy = gs.filter((q) => plays(q, day));
      const tot = healthy.reduce((a, q) => a + q.gs / q.gm, 0);
      if (!tot) continue;
      for (const q of healthy) {
        const sh = q.gs / q.gm, nsh = Math.min(0.9, sh + (lost * sh) / tot);
        if (!GBM.has(q.id)) GBM.set(q.id, new Map());
        GBM.get(q.id).set(day.d, nsh / sh);
      }
    }
  }
}
function gMult(p, day) { const m = GBM.get(p.id); return (m && day && m.get(day.d)) || 1; }
function rateOn(p, s, day) { return s === "G" ? rateAt(p, s) * gMult(p, day) : rateAt(p, s); }
function gamesW(p, days) { return days.reduce((a, x) => a + (plays(p, x) ? gMult(p, x) : 0), 0); }

/* ---------------- rosters ---------------- */
function owners() {
  if (S.live.owners) return S.live.owners;
  const o = {}; B.players.forEach((p) => { if (p.own) o[p.id] = p.own; }); return o;
}
function rosterOf(team) {
  const own = owners(), out = [];
  for (const [fid, t] of Object.entries(own)) if (t === team) out.push(player(fid));
  return out;
}
function freeAgents() {
  const own = owners();
  return B.players.filter((p) => !own[p.id] && !p.nt && p.gm > 0);
}

/* ---------------- lineups ---------------- */
// best lineup for one night from the players who have a game: 2 C, 4 W, 4 D, 2 G.
// Forwards who can play C or W are placed by a small exact search.
function nightLineup(list, want, day) {
  const F = [], D = [], G = [];
  for (const p of list) {
    const e = elig(p);
    if (e.includes("G")) G.push(p);
    else if (e.includes("C") || e.includes("W")) F.push(p);
    else if (e.includes("D")) D.push(p);
  }
  let total = 0;
  const start = want ? new Map() : null;
  const pick = (arr, s, n) => {
    arr.map((p) => [p, rateOn(p, s, day)]).sort((a, b) => b[1] - a[1]).slice(0, n).forEach(([p, r]) => { total += r; if (start) start.set(p.id, s); });
  };
  pick(D, "D", CAP.D); pick(G, "G", CAP.G);
  // forwards: dp over (centers used, wingers used)
  const NC = CAP.C + 1, NW = CAP.W + 1;
  let dp = new Array(NC * NW).fill(-1); dp[0] = 0;
  const back = want ? [] : null;
  for (const p of F) {
    const e = elig(p), rc = e.includes("C") ? rateAt(p, "C") : -1, rw = e.includes("W") ? rateAt(p, "W") : -1;
    const nx = dp.slice(), ch = want ? new Array(NC * NW).fill(0) : null;
    for (let c = 0; c < NC; c++) for (let w = 0; w < NW; w++) {
      const v = dp[c * NW + w]; if (v < 0) continue;
      if (rc >= 0 && c + 1 < NC) { const k = (c + 1) * NW + w; if (v + rc > nx[k]) { nx[k] = v + rc; if (ch) ch[k] = 1; } }
      if (rw >= 0 && w + 1 < NW) { const k = c * NW + w + 1; if (v + rw > nx[k]) { nx[k] = v + rw; if (ch) ch[k] = 2; } }
    }
    if (back) back.push(ch);
    dp = nx;
  }
  let bi = 0; for (let k = 1; k < dp.length; k++) if (dp[k] > dp[bi]) bi = k;
  total += Math.max(0, dp[bi]);
  if (want) {
    let c = Math.floor(bi / NW), w = bi % NW;
    for (let i = F.length - 1; i >= 0; i--) {
      const x = back[i][c * NW + w];
      if (x === 1) { start.set(F[i].id, "C"); c--; } else if (x === 2) { start.set(F[i].id, "W"); w--; }
    }
  }
  return { total, start };
}
function rangeValue(roster, days) {
  let v = 0;
  for (const day of days) {
    const on = roster.filter((p) => plays(p, day));
    if (on.length) v += nightLineup(on, false, day).total;
  }
  return v;
}
// season-shape lineup (who your regular starters are), by rest-of-season points
function fillLineup(list) {
  const slots = { C: [], W: [], D: [], G: [] }, bench = [];
  const sorted = list.slice().sort((a, b) => rosOf(b) - rosOf(a));
  for (const p of sorted) {
    const opts = elig(p).slice().sort((a, b) => (rosAt(p, b) - REPL[b]) - (rosAt(p, a) - REPL[a]));
    const s = opts.find((x) => slots[x] && slots[x].length < CAP[x]);
    if (s) slots[s].push({ p, s }); else bench.push(p);
  }
  for (const open of ["C", "W"]) {
    if (slots[open].length >= CAP[open]) continue;
    const other = open === "C" ? "W" : "C";
    const mover = slots[other].find((x) => elig(x.p).includes(open));
    const filler = bench.find((b) => elig(b).includes(other));
    if (mover && filler) {
      slots[other].splice(slots[other].indexOf(mover), 1); slots[open].push({ p: mover.p, s: open });
      bench.splice(bench.indexOf(filler), 1); slots[other].push({ p: filler, s: other });
    }
  }
  const needs = {};
  for (const s of ["C", "W", "D", "G"]) needs[s] = CAP[s] - slots[s].length;
  return { slots, bench, needs };
}

/* ---------------- pickups ---------------- */
const MEMO = new Map();
function memo(key, fn) { if (!MEMO.has(key)) MEMO.set(key, fn()); return MEMO.get(key); }
function rosterKey(team) { return team + ":" + rosterOf(team).map((p) => p.id).sort().join(","); }
function windowDays(mode) {
  const from = fromDay();
  if (mode === "week") { const p = periodOf(from); return daysIn(from, lastDayOf(p)); }
  return daysIn(from, SEASON_END);
}
// an open roster spot (a player on IR, or fewer than 18 active): the first pickup needs no drop until the
// IR player whose return fills the roster again comes back
function openSpot(roster) {
  const open = META.roster.max - activeCount(roster);
  if (open <= 0) return null;
  const back = roster.filter((p) => onIR(p.id)).map((p) => ({ p, d: hurt(p) ? p.ret : fromDay() })).sort((a, b) => (a.d < b.d ? -1 : a.d > b.d ? 1 : 0));
  const closer = back[open - 1] || null;
  if (closer && closer.d <= fromDay()) return null;
  return { open, until: closer ? closer.d : null, who: closer ? closer.p : null };
}
// what adding p is worth over these days. With an open spot: free until the IR player is back, then he
// replaces your weakest player (or gets dropped again if he's not better than any of them).
function addGain(roster, p, days, drops, os, bases) {
  if (!os) {
    let best = null;
    for (const d of drops) {
      const g = rangeValue(roster.filter((x) => x !== d.p).concat([p]), days) - bases.all;
      if (!best || g > best.g) best = { g, drop: d.p, dc: d.c };
    }
    return best;
  }
  const g1 = bases.pre.length ? rangeValue(roster.concat([p]), bases.pre) - bases.preV : 0;
  if (!bases.post.length) return { g: g1, drop: null, dc: 0, free: true };
  let best = { g: 0, drop: p, dc: 0 };
  for (const d of drops) {
    const g = rangeValue(roster.filter((x) => x !== d.p).concat([p]), bases.post) - bases.postV;
    if (g > best.g) best = { g, drop: d.p, dc: d.c };
  }
  return { g: g1 + best.g, drop: best.drop, dc: best.dc, free: true };
}
function gainBases(roster, days, os, all) {
  if (!os) return { all };
  const pre = days.filter((d) => !os.until || d.d < os.until), post = os.until ? days.filter((d) => d.d >= os.until) : [];
  return { pre, post, preV: pre.length ? rangeValue(roster, pre) : 0, postV: post.length ? rangeValue(roster, post) : 0 };
}
function pickups(team, mode) {
  return memo("adds|" + mode + "|" + rosterKey(team) + "|" + fromDay() + "|" + JSON.stringify(S.gsOv) + "|" + JSON.stringify(S.live.status && rosterOf(team).map((p) => onIR(p.id) ? 1 : 0)), () => {
    const roster = rosterOf(team);
    const rosDays = windowDays("ros");
    const days = windowDays(mode);
    const baseRos = rangeValue(roster, rosDays);
    // drop candidates are always the players who add the least over the rest of the season,
    // so a one-week stream never costs you a regular (players on IR can't be the drop)
    const contrib = roster.map((p) => ({ p, c: baseRos - rangeValue(roster.filter((x) => x !== p), rosDays) })).sort((a, b) => a.c - b.c);
    const drops = contrib.filter((x) => !onIR(x.p.id)).slice(0, 4);
    const base = mode === "ros" ? baseRos : rangeValue(roster, days);
    const os = openSpot(roster);
    const bases = gainBases(roster, days, os, base), rosBases = mode === "ros" ? bases : gainBases(roster, rosDays, os, baseRos);
    const fa = freeAgents().map((p) => ({ p, e: bestRate(p) * gamesW(p, days) })).filter((x) => x.e > 0);
    const pool = [];
    for (const s of ["C", "W", "D", "G"]) pool.push(...fa.filter((x) => elig(x.p)[0] === s).sort((a, b) => b.e - a.e).slice(0, s === "G" ? 20 : 40));
    const out = [];
    for (const { p } of pool) {
      const best = addGain(roster, p, days, drops, os, bases);
      const item = { p, gain: best.g, drop: best.drop, dropC: best.dc, games: gamesIn(p, days), free: !!best.free };
      // upside: you can drop him if the breakout doesn't come, so part of a breakout's extra points counts
      const bp = boP(p);
      item.up = mode === "ros" && bp ? 0.25 * bp * META.breakout.uplift * Math.min(1, item.games / 82) : 0;
      out.push(item);
    }
    out.sort((a, b) => b.gain + b.up - (a.gain + a.up));
    if (mode === "week") {  // what the swap does to the rest of your season
      for (const x of out.slice(0, 40)) x.rosDelta = os ? addGain(roster, x.p, rosDays, drops, os, rosBases).g : rangeValue(roster.filter((y) => y !== x.drop).concat([x.p]), rosDays) - baseRos;
    }
    return { list: out, base, contrib: contrib.filter((x) => !onIR(x.p.id)), days, os };
  });
}

/* ---------------- team shape: where your points come from ---------------- */
const SLOTS = ["C", "W", "D", "G"];
function shapeOf(list, days) {
  const out = { C: 0, W: 0, D: 0, G: 0, total: 0 };
  for (const day of days) {
    const on = list.filter((p) => plays(p, day));
    if (!on.length) continue;
    const nl = nightLineup(on, true, day);
    for (const p of on) { const s = nl.start.get(p.id); if (s) { const r = rateOn(p, s, day); out[s] += r; out.total += r; } }
  }
  return out;
}
function rosDays() { return memo("rosdays|" + fromDay(), () => windowDays("ros")); }
function teamShape(team) { return memo("shape|" + rosterKey(team) + "|" + fromDay() + JSON.stringify(S.gsOv), () => shapeOf(rosterOf(team), rosDays())); }
function leagueShapes() {
  const all = META.teams.map((t) => ({ id: t.id, sh: teamShape(t.id) }));
  const rank = {};
  for (const s of [...SLOTS, "total"]) {
    const sorted = all.slice().sort((a, b) => b.sh[s] - a.sh[s]);
    sorted.forEach((x, i) => { (rank[x.id] = rank[x.id] || {})[s] = i + 1; });
  }
  const avg = {}; for (const s of [...SLOTS, "total"]) avg[s] = all.reduce((a, x) => a + x.sh[s], 0) / all.length;
  return { all, rank, avg };
}

/* ---------------- trades ---------------- */
const onIR = (id) => !!(S.live.status && S.live.status[id] === "INJURED_RESERVE");
function vOf(list) {
  const k = "v|" + (MKT.on ? "m|" : "") + list.map((p) => p.id).sort().join(",");
  return memo(k, () => rangeValue(list, rosDays()));
}
function activeCount(list) { return list.filter((p) => !onIR(p.id)).length; }
// for trades: a player on IR who's back within two weeks (or already healthy) still needs his roster spot
function soonBack(p) { if (!onIR(p.id) || !hurt(p)) return onIR(p.id); const d = new Date(fromDay() + "T12:00:00"); d.setDate(d.getDate() + 14); return p.ret <= d.toISOString().slice(0, 10); }
function tradeCount(list) { return list.filter((p) => !onIR(p.id) || soonBack(p)).length; }
// what a roster looks like after a trade: extra bodies are cut (least useful first), a freed spot takes the team's best free agent
function afterTrade(team, roster, out, inn) {
  const outIds = new Set(out.map((p) => p.id));
  let r = roster.filter((p) => !outIds.has(p.id)).concat(inn);
  const cap = Math.max(META.roster.max, tradeCount(roster));
  const dropped = [];
  let extra = tradeCount(r) - cap;
  while (extra-- > 0) {
    const cands = r.filter((p) => !inn.includes(p) && !onIR(p.id)).sort((a, b) => bestRate(a) * gamesLeft(a, fromDay()) - bestRate(b) * gamesLeft(b, fromDay())).slice(0, 3);
    let best = null;
    for (const c of cands) { const v = vOf(r.filter((x) => x !== c)); if (!best || v > best.v) best = { c, v }; }
    if (!best) break;
    r = r.filter((x) => x !== best.c); dropped.push(best.c);
  }
  let added = null;
  if (tradeCount(r) < cap && inn.length < out.length) {
    const fa = faFor(team, roster);
    if (fa) { r = r.concat([fa]); added = fa; }
  }
  return { v: vOf(r), r, dropped, added };
}
// best free agent for a team that has an open spot (computed once per team)
function faFor(team, roster) {
  return memo("fa|" + (MKT.on ? "m|" : "") + rosterKey(team), () => {
    const base = vOf(roster);
    const pool = [];
    const fa = freeAgents();
    for (const s of SLOTS) pool.push(...fa.filter((p) => elig(p)[0] === s).sort((a, b) => rosOf(b) - rosOf(a)).slice(0, 4));
    let best = null;
    for (const p of pool) { const g = vOf(roster.concat([p])) - base; if (!best || g > best.g) best = { p, g }; }
    return best && best.g > 0 ? best.p : null;
  });
}
// how the other manager is likely to see a deal: name value, with stars worth more than the sum of lesser players.
// Uses the analysts' view of each player in this league's scoring, above waiver level, to the power 1.5.
function mval(p) { const x = p.mk != null && !p.rk ? p.mk : p.pts; return Math.pow(Math.max(0, (x || 0) - (REPL[p.slot] || 0)), 1.5); }
function nameRatio(give, get) { // what they receive over what they send
  const a = give.reduce((t, p) => t + mval(p), 0), b = get.reduce((t, p) => t + mval(p), 0);
  return b > 0 ? a / b : a > 0 ? 9 : 1;
}
function evalTrade(me, them, give, get) {
  const A = rosterOf(me), Bt = rosterOf(them);
  const a = afterTrade(me, A, give, get), b = afterTrade(them, Bt, get, give);
  return { me: a.v - vOf(A), them: b.v - vOf(Bt), a, b };
}
function tradeView(me, them, give, get) { return { ...evalTrade(me, them, give, get), ratio: nameRatio(give, get) }; }
// search: one-for-one, two-for-one and one-for-two with every other team
function tradeSearch(me, onProgress) {
  const key = "deals|" + rosterKey(me) + "|" + META.teams.map((t) => rosterKey(t.id)).join(";") + JSON.stringify(S.gsOv) + fromDay();
  if (MEMO.has(key)) return Promise.resolve(MEMO.get(key));
  const A = rosterOf(me), vA = vOf(A);
  const others = META.teams.filter((t) => t.id !== me);
  const found = [];
  const contrib = (list, v0) => list.filter((p) => !onIR(p.id)).map((p) => ({ p, c: v0 - vOf(list.filter((x) => x !== p)) })).sort((a, b) => a.c - b.c);
  const myC = contrib(A, vA);
  const myWorst = myC[0] && myC[0].p;
  let i = 0;
  return new Promise((resolve) => {
    const step = () => {
      const T = others[i];
      if (!T) {
        for (const d of found) d.likely = d.them >= 0 && d.ratio >= 1.0;
        MEMO.set(key, found);
        resolve(found);
        return;
      }
      if (onProgress) onProgress(i, others.length, T);
      const Bt = rosterOf(T.id), vB = vOf(Bt);
      const thC = contrib(Bt, vB);
      const thWorst = thC[0] && thC[0].p;
      // their players who'd help me, and my players who'd help them
      const targets = Bt.filter((q) => !onIR(q.id)).sort((a, b) => rosOf(b) - rosOf(a)).slice(0, 12)
        .map((q) => ({ q, g: vOf(A.filter((x) => x !== myWorst).concat([q])) - vA })).filter((x) => x.g > 3).sort((a, b) => b.g - a.g).slice(0, 6).map((x) => x.q);
      const offers = A.filter((p) => !onIR(p.id))
        .map((p) => ({ p, g: vOf(Bt.filter((x) => x !== thWorst).concat([p])) - vB })).filter((x) => x.g > 3).sort((a, b) => b.g - a.g).slice(0, 7).map((x) => x.p);
      const tryDeal = (give, get) => {
        const ratio = nameRatio(give, get);
        if (ratio < 0.85 || ratio > 2.2) return;   // they'd laugh at it, or you'd be giving far too much
        const r = evalTrade(me, T.id, give, get);
        if (r.me > 0) found.push({ team: T.id, give, get, ratio, me: r.me, them: r.them, dropMe: r.a.dropped, addMe: r.a.added, dropThem: r.b.dropped, addThem: r.b.added });
      };
      for (const p of offers) for (const q of targets) tryDeal([p], [q]);
      const o5 = offers.slice(0, 5), t4 = targets.slice(0, 4), t5 = targets.slice(0, 5), o4 = offers.slice(0, 4);
      for (let x = 0; x < o5.length; x++) for (let y = x + 1; y < o5.length; y++) for (const q of t4) tryDeal([o5[x], o5[y]], [q]);
      for (const p of o4) for (let x = 0; x < t5.length; x++) for (let y = x + 1; y < t5.length; y++) tryDeal([p], [t5[x], t5[y]]);
      i++;
      setTimeout(step, 0);
    };
    setTimeout(step, 0);
  });
}
// plain-English reasons: which parts of each lineup get better or worse
// the same pool of deals, sorted for different goals
const TMODES = {
  both: { label: "Best for both", tip: "Deals that help both teams the most. The easiest ones to get done." },
  me: { label: "Best for me", tip: "The biggest boost for you that still looks fair enough to propose." },
  yes: { label: "Easiest yes", tip: "Deals they're most likely to accept: they gain in their lineup and in name value." },
  weak: { label: "Fix weak spot", tip: "Deals that bring in a player at your weakest position." },
};
function weakestSlot(team) { const r = leagueShapes().rank[team] || {}; return SLOTS.slice().sort((a, b) => (r[b] || 0) - (r[a] || 0))[0]; }
function pickDeals(all, mode, teamF, limit, exempt) {
  const weak = weakestSlot(S.team);
  let L = all.filter((d) => d.me >= 5 && (!teamF || teamF === "ALL" || d.team === teamF));
  const extra = (d) => 4 * (d.give.length + d.get.length - 2);
  if (mode === "both") { L = L.filter((d) => d.them >= 0 && d.ratio >= 0.9); L.sort((a, b) => Math.min(b.me, b.them) - extra(b) - (Math.min(a.me, a.them) - extra(a))); }
  else if (mode === "yes") { L = L.filter((d) => d.them >= 0 && d.ratio >= 1.0); const y = (d) => Math.min(d.them, 60) + 60 * Math.min(d.ratio - 1, 0.5) + 0.2 * d.me - extra(d); L.sort((a, b) => y(b) - y(a)); }
  else if (mode === "weak") { L = L.filter((d) => d.them >= -15 && d.ratio >= 0.85 && d.get.some((p) => elig(p).includes(weak))); L.sort((a, b) => b.me - extra(b) - (a.me - extra(a))); }
  else { L = L.filter((d) => d.them >= -15 && d.ratio >= 0.85); L.sort((a, b) => b.me - extra(b) + (b.likely ? 8 : 0) - (a.me - extra(a) + (a.likely ? 8 : 0))); }
  const perTeam = {}, perPl = {}, out = [];
  for (const d of L) {
    const ids = d.give.concat(d.get).map((p) => p.id);
    if (!teamF || teamF === "ALL") { if ((perTeam[d.team] || 0) >= 2) continue; }
    if (ids.some((id) => id !== exempt && (perPl[id] || 0) >= 2)) continue;
    perTeam[d.team] = (perTeam[d.team] || 0) + 1; ids.forEach((id) => (perPl[id] = (perPl[id] || 0) + 1));
    out.push(d);
    if (out.length >= (limit || 10)) break;
  }
  return out;
}
function tradeReasons(me, them, d) {
  const days = rosDays();
  const s0 = teamShape(me), s1 = shapeOf(d.a ? d.a.r : afterTrade(me, rosterOf(me), d.give, d.get).r, days);
  const t0 = teamShape(them), t1 = shapeOf(d.b ? d.b.r : afterTrade(them, rosterOf(them), d.get, d.give).r, days);
  const word = { C: "centers", W: "wingers", D: "defensemen", G: "goalies" };
  const lines = (a, b, who) => SLOTS.map((s) => [s, b[s] - a[s]]).filter(([, x]) => Math.abs(x) >= 6).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]))
    .map(([s, x]) => `${who} ${word[s]} ${x > 0 ? "get better" : "get worse"} (${sgn(x)})`);
  const dm = SLOTS.map((s) => [s, s1[s] - s0[s]]), dt = SLOTS.map((s) => [s, t1[s] - t0[s]]);
  const up = dm.filter(([, x]) => x >= 6).sort((a, b) => b[1] - a[1])[0], down = dm.filter(([, x]) => x <= -6).sort((a, b) => a[1] - b[1])[0];
  const tup = dt.filter(([, x]) => x >= 6).sort((a, b) => b[1] - a[1])[0];
  let lead = "";
  if (up && down) lead = `You turn depth at ${word[down[0]]} into help at ${word[up[0]]}.`;
  else if (up) lead = `Your ${word[up[0]]} get better without hurting anything else much.`;
  if (tup) lead += ` They get help at ${word[tup[0]]}, which is why they might say yes.`;
  return { me: lines(s0, s1, "Your"), them: lines(t0, t1, "Their"), lead: lead.trim() };
}

/* ---------------- status strip ---------------- */
function renderStrip() {
  const el = $("#clock");
  const t = todayET(), p = periodOf(fromDay());
  const opp = opponentOf(S.team, p.n);
  let main;
  if (t < SEASON_START) {
    const days = Math.round((new Date(SEASON_START + "T12:00:00") - new Date(t + "T12:00:00")) / 864e5);
    main = `<span class="big">Season starts in ${days} day${days === 1 ? "" : "s"}</span><span class="small">${esc(dLabel(SEASON_START))}${opp ? ` · week 1 vs <b>${esc(tname(opp))}</b>` : ""}</span>`;
  } else if (t > SEASON_END) {
    main = `<span class="big">Season over</span>`;
  } else {
    main = `<span class="big">${isPlayoffs(p.n) ? "Playoffs · " : ""}Week ${p.n}</span><span class="small">${esc(dLabel(p.s, { month: "short", day: "numeric" }))} to ${esc(dLabel(lastDayOf(p), { month: "short", day: "numeric" }))}${opp ? ` · vs <b>${esc(tname(opp))}</b>` : ""}</span>`;
  }
  const L = S.live;
  let cls = "live", txt;
  if (L.err && !L.at) { cls += " err"; txt = "Can't reach Fantrax"; }
  else if (L.err) { cls += " err"; txt = `Fantrax slow · ${agoText(L.at)}`; }
  else if (L.at) { cls += " ok"; txt = `Rosters live · ${agoText(L.at)}${LIVE && LIVE.generated ? ` · ${LIVE.started ? "stats and injuries" : "injuries"} ${agoText(Date.parse(LIVE.injAt || LIVE.generated))}` : ""}`; }
  else { cls += " busy"; txt = "Connecting…"; }
  el.innerHTML = `<div class="main">${main}</div><div class="mine"><button class="${cls}" id="liveBtn" title="Check Fantrax now">${txt}</button></div>`;
  $("#liveBtn").onclick = () => sync(true);
}

/* ---------------- my team ---------------- */
function renderTeam() {
  const el = $("#tab-team");
  const roster = rosterOf(S.team);
  const from = fromDay(), per = periodOf(from);
  const wk = daysIn(from, lastDayOf(per));
  const opp = opponentOf(S.team, per.n);
  const myWk = rangeValue(roster, wk);
  const oppWk = opp ? rangeValue(rosterOf(opp), wk) : null;
  const started = todayET() > per.s;
  const LSH = leagueShapes();
  const rk = LSH.rank[S.team] || {};
  const mine = LSH.all.find((x) => x.id === S.team).sh;
  const lu = fillLineup(roster);
  const adds = pickups(S.team, "ros").list.filter((x) => x.gain >= 5);
  const games = roster.reduce((a, p) => a + gamesIn(p, wk), 0), oppGames = opp ? rosterOf(opp).reduce((a, p) => a + gamesIn(p, wk), 0) : 0;
  const word = { C: "centers", W: "wingers", D: "defensemen", G: "goalies" };
  const weak = SLOTS.slice().sort((a, b) => rk[b] - rk[a]).filter((s) => rk[s] >= 7).slice(0, 2);
  const strong = SLOTS.filter((s) => rk[s] <= 4);
  const inj = roster.filter((p) => hurt(p) && !dtd(p));

  // the next night any of your players has a game
  const night = DAYS.find((x) => x.d >= todayET() && roster.some((p) => plays(p, x)));
  let lineupHTML = "";
  if (night) {
    const on = roster.filter((p) => plays(p, night));
    const nl = nightLineup(on, true, night);
    const bySlot = { C: [], W: [], D: [], G: [] };
    for (const p of on) { const s = nl.start.get(p.id); if (s) bySlot[s].push(p); }
    const sit = on.filter((p) => !nl.start.has(p.id));
    const hurtOut = roster.filter((p) => !plays(p, night) && night.teams.has(p.t) && p.ret && night.d < p.ret);
    const off = roster.filter((p) => !plays(p, night) && !hurtOut.includes(p));
    const slotLine = (s) => { const n = CAP[s] - bySlot[s].length; return `<div class="lgrp"><div class="lh">${POSNAME[s]}<small>${bySlot[s].length} of ${CAP[s]}${n ? ` · ${n} empty` : ""}</small></div>${bySlot[s].map((p) => `<button class="lp" data-open="${esc(p.id)}">${face(p)}<span>${esc(p.n)}${s !== p.slot ? `<small>put him in a ${s} spot</small>` : ""}${dtd(p) ? `<small class="bad">day-to-day: make sure he's playing</small>` : ""}</span><b class="num">${fmt(rateOn(p, s, night), 1)}</b></button>`).join("")}${!bySlot[s].length ? `<div class="lp empty"><span>None of your ${POSPL[s]} play this night</span></div>` : ""}</div>`; };
    const empties = SLOTS.reduce((a, s) => a + CAP[s] - bySlot[s].length, 0);
    lineupHTML = `<div class="tonight" id="tonight">
      <div class="th2"><div><div class="k">Set your lineup for</div><div class="d">${esc(dLabel(night.d, { weekday: "long", month: "short", day: "numeric" }))}</div></div><div class="tp"><b class="num">${fmt(nl.total, 1)}</b><small>expected pts</small></div></div>
      <p class="note">In Fantrax, put these players in your starting spots. Numbers are expected points that night.</p>
      <div class="lgrid">${SLOTS.map(slotLine).join("")}</div>
      <div class="benchline">${sit.length ? `<div><b>Bench these (they play, but your starters are better):</b> ${sit.map((p) => esc(p.n)).join(", ")}</div>` : ""}${hurtOut.length ? `<div class="bad"><b>Hurt, leave out:</b> ${hurtOut.map((p) => `${esc(p.n)} (back around ${esc(dLabel(p.ret, { month: "short", day: "numeric" }))})`).join(", ")}</div>` : ""}${off.length ? `<div><b>No game this night:</b> ${off.map((p) => esc(p.n)).join(", ")}</div>` : ""}${empties >= 3 ? `<div>${empties} starting spots are empty that night. A free agent who plays then is free points: see <button class="linkbtn" data-tab="adds">Pickups → This week</button>.</div>` : ""}</div>
      <p class="note">Goalies only score if they actually start. Starters are usually confirmed the morning of the game: check <a href="https://www.dailyfaceoff.com/starting-goalies/" target="_blank" rel="noopener">Daily Faceoff's starting goalies</a> and bench a goalie who's sitting.</p>
    </div>`;
  }

  // to-do list (the trade line fills in when the search finishes)
  const todo = [];
  if (night) todo.push(`<li><b>Set your lineup for ${esc(dLabel(night.d, { weekday: "long" }))}.</b> It's worked out for you below. Do it again each game day: only players with a game can score. <button class="linkbtn" data-scroll="tonight">Show me</button></li>`);
  todo.push(`<li id="todoTrade"><b>Trade for help at ${esc(weak.length ? word[weak[0]] : "your weakest spot")}.</b> <span class="note">Looking for fair deals…</span></li>`);
  const addPick = adds.find((x) => !(x.drop && x.drop !== x.p && analystsBacked(x.drop)));
  const os = pickups(S.team, "ros").os;
  if (addPick && addPick.free) {
    const back = os && os.until ? ` until he's back around ${esc(dLabel(os.until, { month: "short", day: "numeric" }))}` : "";
    const then = addPick.drop && addPick.drop !== addPick.p ? ` When he's back, drop ${esc(addPick.drop.n)}.` : addPick.drop === addPick.p ? ` When he's back, drop ${esc(addPick.p.n)} again.` : "";
    todo.push(`<li><b>Pick up ${esc(addPick.p.n)}</b> (${esc(addPick.p.t)}). ${os && os.who ? `${esc(os.who.n)} is on IR, so you` : "You"} have an open roster spot and don't need to drop anyone${back}.${then} About ${sgn(addPick.gain)} points for the rest of the season. <button class="linkbtn" data-tab="adds">All pickups</button></li>`);
  } else if (addPick) {
    todo.push(`<li><b>Pick up ${esc(addPick.p.n)}</b> (${esc(addPick.p.t)}) and drop ${esc(addPick.drop.n)}: about ${sgn(addPick.gain)} points for the rest of the season. <button class="linkbtn" data-tab="adds">All pickups</button></li>`);
  }
  const stash = breakouts(S.team)[0];
  if (stash && stash.b >= 0.3) todo.push(`<li><b>Keep an eye on ${esc(stash.p.n)}</b> (${esc(stash.p.t)}): the best breakout bet on waivers, ${Math.round(100 * stash.b)}% chance he becomes a regular fantasy starter. Worth a bench spot if you have a weak one. <button class="linkbtn" data-bo="1">Breakout list</button></li>`);
  const chip = roster.filter(analystsBacked).sort((a, b) => mval(b) - mval(a))[0];
  if (chip) todo.push(`<li><b>Shop ${esc(chip.n)} in trades.</b> The experts rank him ${ordinal(chip.mr)} among ${POSPL[chip.slot]}, but our numbers have him ${ordinal(chip.orank)} for this league's scoring, so other managers will likely value him more than he helps you. Use him to get what you need. <button class="linkbtn" data-shopid="${esc(chip.id)}">Find trades for him</button></li>`);
  todo.push(`<li><b>Check goalies each game day.</b> A goalie who doesn't start scores nothing, so swap him out if he's on the bench.</li>`);
  // injuries go first: they come from the injury report, checked several times a day
  const injTodo = [], irUsed = roster.filter((p) => onIR(p.id)).length;
  for (const p of inj) {
    const n = missedGames(p), when = esc(dLabel(p.ret, { month: "short", day: "numeric" })), what = esc(injWhat(p).toLowerCase());
    const miss = n ? `, misses about ${n} game${n === 1 ? "" : "s"}` : ", shouldn't miss any games";
    if (onIR(p.id)) injTodo.push(`<li class="bad"><b>${esc(p.n)} is hurt and on your IR</b> (${what}, back around ${when}${miss}). He's left out of your lineups until then.</li>`);
    else if (n >= 2 && irUsed < IR_SLOTS) injTodo.push(`<li class="bad"><b>Move ${esc(p.n)} to IR in Fantrax</b> (${what}, back around ${when}${miss}). That opens a roster spot, so you can pick someone up without dropping anyone. He's already left out of your lineups here.</li>`);
    else injTodo.push(`<li class="bad"><b>${esc(p.n)} is hurt</b> (${what}, back around ${when}${miss}). Keep him on your bench until then; he's already left out of your lineups here.</li>`);
  }
  for (const p of roster.filter(dtd)) { const x = injOf(p), n = missedGames(p); injTodo.push(`<li><b>${esc(p.n)} is day-to-day</b>${x.why && x.why !== "Undisclosed" ? ` (${esc(x.why.toLowerCase())})` : ""}. ${n ? `The report expects him to miss about ${n} game${n === 1 ? "" : "s"}, so he's left out of your lineups until ${esc(dLabel(p.ret, { month: "short", day: "numeric" }))}. ` : ""}Check the news before his next game and bench him if he's ruled out.</li>`); }
  const easy = pickups(S.team, "ros").contrib[0];
  for (const p of roster.filter((q) => onIR(q.id) && !hurt(q) && !dtd(q))) injTodo.push(`<li><b>${esc(p.n)} is on your IR but isn't on the injury report anymore.</b> Once he's cleared, move him back to your active roster. You'll need to drop someone to make room${easy ? `: your easiest drop is ${esc(easy.p.n)}` : ""}.</li>`);
  todo.unshift(...injTodo);

  const shapeRows = SLOTS.map((s) => {
    const r = rk[s], pct = Math.min(100, (100 * mine[s]) / Math.max(...LSH.all.map((x) => x.sh[s])));
    const tone = r <= 4 ? "good" : r >= 9 ? "bad" : "";
    return `<div class="shp"><span>${POSNAME[s] === "Defense" ? "Defense" : POSPL[s][0].toUpperCase() + POSPL[s].slice(1)}</span><span class="t"><i class="${tone}" style="width:${pct}%"></i></span><b class="${tone}">${ordinal(r)}</b></div>`;
  }).join("");

  const dayRows = wk.map((day) => {
    const on = roster.filter((p) => plays(p, day));
    const nl = nightLineup(on, true, day);
    const sit = on.filter((p) => !nl.start.has(p.id));
    const cnt = { C: 0, W: 0, D: 0, G: 0 };
    for (const s of nl.start.values()) cnt[s]++;
    const empty = SLOTS.filter((s) => cnt[s] < CAP[s]).map((s) => `${CAP[s] - cnt[s]} ${s}`);
    return `<div class="day ${day.d === todayET() ? "today" : ""}"><div class="dd"><b>${esc(dLabel(day.d, { weekday: "short" }))}</b><span>${esc(dLabel(day.d, { month: "short", day: "numeric" }))}</span></div>
      <div class="di"><div><b>${on.length}</b> playing · <span class="num">${fmt(nl.total, 1)}</span> pts</div>
      ${sit.length ? `<div class="sit">Bench: ${sit.map((p) => esc(p.n)).join(", ")}</div>` : ""}
      ${empty.length && on.length ? `<div class="gap">Empty spots: ${empty.join(", ")}</div>` : ""}${!on.length ? `<div class="gap">Nobody plays</div>` : ""}</div></div>`;
  }).join("");

  const slotRow = (x, s) => rowMini(x.p, rosAt(x.p, s), s);
  const grp = (s, label) => `<div class="slotgrp"><h3>${label}<small>${lu.slots[s].length} of ${CAP[s]}</small></h3>${lu.slots[s].map((x) => slotRow(x, s)).join("")}${Array.from({ length: Math.max(0, lu.needs[s]) }, () => `<div class="slot open"><div class="open-ic"></div><div class="nm">Open spot<small>check Pickups</small></div><b></b></div>`).join("")}</div>`;
  const summary = `Projected <b>${ordinal(rk.total)} of 12</b> for the season.${weak.length ? ` Weakest spot: <b>${word[weak[0]]}</b> (${ordinal(rk[weak[0]])} in the league)${weak[1] ? `, then ${word[weak[1]]} (${ordinal(rk[weak[1]])})` : ""}.` : ""}${strong.length ? ` You're strong at ${strong.map((s) => word[s]).join(" and ")}.` : ""} The list below is how to climb.`;
  el.innerHTML = `
    <div class="lede"><h2>${esc(tname(S.team))}</h2><p>${summary}</p></div>
    <div class="todo"><h3>What to do</h3><ol>${todo.join("")}</ol></div>
    ${opp ? `<div class="matchup">
      <div class="mh"><span>${isPlayoffs(per.n) ? "Playoffs · " : ""}Week ${per.n} matchup · ${esc(dLabel(per.s, { month: "short", day: "numeric" }))} to ${esc(dLabel(lastDayOf(per), { month: "short", day: "numeric" }))}</span><span>${started ? "rest of week" : "projected"}</span></div>
      <div class="side me"><div class="tn">${esc(tname(S.team))}<small>${games} player-games</small></div><b class="num">${fmt(myWk)}</b><div class="mbar"><i style="width:${(100 * myWk) / Math.max(myWk, oppWk, 1)}%"></i></div></div>
      <div class="side"><div class="tn">${esc(tname(opp))}<small>${oppGames} player-games</small></div><b class="num">${fmt(oppWk)}</b><div class="mbar"><i style="width:${(100 * oppWk) / Math.max(myWk, oppWk, 1)}%"></i></div></div>
      <div class="mf">Whoever scores more points this week wins. ${myWk >= oppWk ? `You're projected to win by about <b>${fmt(myWk - oppWk)}</b>.` : `You're projected to lose by about <b>${fmt(oppWk - myWk)}</b>. A pickup whose team plays a lot this week can close it (Pickups → This week).`}</div>
    </div>` : ""}
    ${lineupHTML}
    <div class="shape"><h3>Where you stand</h3><p class="note">Your rank in the league at each position for the rest of the season (1st is best).</p>${shapeRows}<div class="shp tot"><span>Overall</span><span></span><b>${ordinal(rk.total)}</b></div></div>
    <h3 class="sectitle">This week, night by night</h3>
    <div class="days">${dayRows || '<div class="empty">No games left this week.</div>'}</div>
    <h3 class="sectitle">Your roster</h3>
    <p class="note" style="margin:-2px 0 10px">Your usual starters and bench. Points are for the rest of the season. Tap a player for the full story.</p>
    <div class="rink">
      ${grp("C", "Centers")}${grp("W", "Wingers")}${grp("D", "Defense")}${grp("G", "Goalies")}
      <div class="slotgrp"><h3>Bench<small>${lu.bench.length} of ${BENCH}</small></h3>${lu.bench.map((p) => rowMini(p, rosOf(p))).join("")}</div>
    </div>`;
  el.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  el.querySelectorAll("[data-open]").forEach((b) => (b.onclick = () => openPlayer(b.dataset.open)));
  el.querySelectorAll("[data-shopid]").forEach((b) => (b.onclick = () => shopPlayer(b.dataset.shopid)));
  el.querySelectorAll("[data-bo]").forEach((b) => (b.onclick = () => { S.addMode = "bo"; LS.set("zb-addmode", "bo"); setTab("adds"); }));
  el.querySelectorAll("[data-scroll]").forEach((b) => (b.onclick = () => { const t = document.getElementById(b.dataset.scroll); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); }));
  const team = S.team;
  tradeSearch(team).then((all) => {
    const li = $("#todoTrade");
    if (!li || S.team !== team) return;
    const d = pickDeals(all, "both")[0] || pickDeals(all, "me")[0];
    li.innerHTML = d ? `<b>Propose a trade to ${esc(tname(d.team))}:</b> give ${d.give.map((p) => esc(p.n)).join(" + ")}, get ${d.get.map((p) => esc(p.n)).join(" + ")}. About ${sgn(d.me)} points for you this season${d.them >= 1 ? `, and it helps them too (${sgn(d.them)})` : d.them > -1 ? `, and it's about even for them` : ""}. <button class="linkbtn" data-tab="trades">All trade ideas</button>`
      : `<b>Trades:</b> no deal found that clearly helps both teams right now. <button class="linkbtn" data-tab="trades">Try the trade checker</button>`;
    li.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  });
}
function rowMini(p, pts, s) {
  const flags = [];
  { const it = injTag(p, true); if (it) flags.push(it); }
  return `<button class="slot" data-open="${esc(p.id)}">${face(p)}<div class="nm">${esc(p.n)}<small>${s && s !== p.slot ? `as ${s} · ` : ""}${esc(p.t)}</small> ${flags.join(" ")}</div><b class="num">${fmt(pts)}</b></button>`;
}
function openPlayer(id) {
  S.open = id; S.q = player(id).n; S.pos = "ALL"; S.faOnly = false;
  setTab("board");
  const c = document.querySelector(`.card[data-id="${CSS.escape(id)}"]`);
  if (c) c.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------------- pickups tab ---------------- */
// free agents most likely to break out, each tested in your lineup like any pickup
function breakouts(team) {
  return memo("bo|" + rosterKey(team) + "|" + fromDay() + "|" + (LIVE ? LIVE.generated : ""), () => {
    const roster = rosterOf(team), days = windowDays("ros");
    const base = rangeValue(roster, days);
    const drops = roster.filter((p) => !onIR(p.id)).map((p) => ({ p, c: base - rangeValue(roster.filter((x) => x !== p), days) })).sort((a, b) => a.c - b.c).slice(0, 4);
    const os = openSpot(roster), bases = gainBases(roster, days, os, base);
    // ranked by upside: how much more likely than a typical player projected like him (projection alone already shows the rest)
    const cands = freeAgents().filter((p) => p.bo).map((p) => ({ p, b: boP(p) })).filter((x) => x.b >= 0.2).sort((a, b) => (b.b - b.p.bo[1]) - (a.b - a.p.bo[1])).slice(0, 30);
    return cands.map(({ p, b }) => {
      const best = addGain(roster, p, days, drops, os, bases);
      return { p, b, gain: best.g, drop: best.drop, free: !!best.free, games: gamesIn(p, days), up: 0.25 * b * META.breakout.uplift * Math.min(1, gamesIn(p, days) / 82) };
    });
  });
}
function boCard(x, rank) {
  const p = x.p, open = S.addOpen === p.id;
  const tags = [];
  tags.push(`<span class="tag">Typical for his projection: <b>${Math.round(100 * p.bo[1])}%</b></span>`);
  if (x.free) tags.push(x.gain >= 1 ? `<span class="tag">Fits your open roster spot: <b class="gainv">${sgn(x.gain)}</b> pts</span>` : `<span class="tag">Only helps while your open spot lasts: watch him</span>`);
  else tags.push(x.gain >= 1 ? `<span class="tag">Already better than ${esc(x.drop.n)}: <b class="gainv">${sgn(x.gain)}</b> pts</span>`
    : `<span class="tag" title="Adding him now in place of ${esc(x.drop.n)} would cost about ${Math.round(-x.gain)} points unless he breaks out">Not better than your weakest player yet: watch him</span>`);
  const tt = trendTag(p); if (tt) tags.push(tt);
  const ot = outTag(p); if (ot) tags.push(ot);
  { const it = injTag(p); if (it) tags.push(it); }
  tags.push(starBtn(p));
  const why = (p.bw || []).map((t) => `<li class="good">${esc(t)}</li>`).join("");
  return `<div class="card" data-id="${esc(p.id)}" style="--tc:var(--t${tierOf(valOf(p))})">
    <button class="row" data-atoggle="${esc(p.id)}" aria-expanded="${open}">
      <div class="rank">${rank}</div>${face(p)}
      <div class="who"><div class="nm">${esc(p.n)}</div><div class="mt">${posBadge(p)}<span>${esc(p.t)}${p.age ? ` · ${p.age}` : ""}</span></div></div>
      <div class="bigpts"><div class="p">${Math.round(100 * x.b)}%</div><div class="l">breakout chance</div></div>
    </button>
    <div class="subrow">${tags.join("")}</div>
    ${why ? `<ul class="why bwhy">${why}</ul>` : ""}
    ${open ? detailHTML(p) : ""}
  </div>`;
}
function renderAdds() {
  const el = $("#tab-adds");
  const mode = S.addMode;
  if (mode === "bo") return renderBreakouts(el);
  const res = pickups(S.team, mode);
  const per = periodOf(fromDay());
  let rows = res.list;
  if (S.addPos !== "ALL") rows = rows.filter((x) => elig(x.p).includes(S.addPos));
  const good = rows.filter((x) => x.gain >= 1);
  const chips = [["ALL", "All"], ["C", "C"], ["W", "W"], ["D", "D"], ["G", "G"]];
  const drops = res.contrib.slice(0, 4);
  el.innerHTML = `
    <div class="lede"><h2>Pickups</h2><p>Free agents (players nobody owns) who'd make <b>${esc(tname(S.team))}</b> better, and who to drop for each. Each one is tested in your real lineup night by night, so games and crowded positions count. You get 3 pickups a week ($2 a claim, $1 a drop). Use <b>This week</b> to chase a close matchup.</p></div>
    <div class="controls">
      <div class="chips" role="group" aria-label="Time frame"><button data-mode="ros" aria-pressed="${mode === "ros"}">Rest of season</button><button data-mode="week" aria-pressed="${mode === "week"}">This week${per ? ` (wk ${per.n})` : ""}</button><button data-mode="bo" aria-pressed="${mode === "bo"}">Breakouts</button></div>
      <div class="chips" role="group" aria-label="Position">${chips.map(([k, l]) => `<button data-apos="${k}" aria-pressed="${S.addPos === k}">${l}</button>`).join("")}</div>
    </div>
    ${res.os ? `<div class="banner"><b>You have an open roster spot</b>${res.os.who ? ` because ${esc(res.os.who.n)} is on IR` : ""}, so your next pickup doesn't need a drop${res.os.until ? ` until he's back (around ${esc(dLabel(res.os.until, { month: "short", day: "numeric" }))}). After that you'll have to drop someone, and the points below already count that` : ""}.</div>` : ""}
    <div class="banner soft"><b>Easiest to drop right now:</b> ${drops.map((d) => `${esc(d.p.n)} (adds ${fmt(d.c)})`).join(", ")}. That's how many points each adds to your lineup over the rest of the season once your other players are counted, so these are the only players suggested as drops.</div>
    <div class="list" id="addList">${good.slice(0, S.addShow).map((x, i) => addCard(x, i + 1, mode)).join("") || `<div class="empty">No free agent beats your current roster ${mode === "week" ? "this week" : "right now"}. Check back as news comes in.</div>`}</div>
    <button class="more" id="addMore" ${good.length > S.addShow ? "" : "hidden"}>Show more</button>`;
  el.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => { S.addMode = b.dataset.mode; LS.set("zb-addmode", S.addMode); S.addShow = 25; renderAdds(); }));
  el.querySelectorAll("[data-apos]").forEach((b) => (b.onclick = () => { S.addPos = b.dataset.apos; S.addShow = 25; renderAdds(); }));
  $("#addMore").onclick = () => { S.addShow += 25; renderAdds(); };
  $("#addList").onclick = (e) => {
    const sh = e.target.closest("[data-shop]"); if (sh) { shopPlayer(sh.dataset.shop); return; }
    const b = e.target.closest("[data-atoggle],[data-star]"); if (!b) return;
    if (b.dataset.star) { toggleStar(b.dataset.star); renderAdds(); return; }
    S.addOpen = S.addOpen === b.dataset.atoggle ? null : b.dataset.atoggle; renderAdds();
  };
}
function renderBreakouts(el) {
  const list = breakouts(S.team).filter((x) => S.addPos === "ALL" || elig(x.p).includes(S.addPos));
  const chips = [["ALL", "All"], ["C", "C"], ["W", "W"], ["D", "D"]];
  const t = META.breakout.test;
  el.innerHTML = `
    <div class="lede"><h2>Pickups</h2><p>Free agents with the most <b>breakout</b> upside: players whose chance of becoming a regular fantasy starter this season is well above what their projection alone suggests. Stash one on your bench when you have a spare spot; if it doesn't happen, drop him.</p></div>
    <div class="controls">
      <div class="chips" role="group" aria-label="Time frame"><button data-mode="ros" aria-pressed="false">Rest of season</button><button data-mode="week" aria-pressed="false">This week</button><button data-mode="bo" aria-pressed="true">Breakouts</button></div>
      <div class="chips" role="group" aria-label="Position">${chips.map(([k, l]) => `<button data-apos="${k}" aria-pressed="${S.addPos === k}">${l}</button>`).join("")}</div>
    </div>
    <div class="banner soft">${LIVE && LIVE.started ? `Chances update with this season's stats ${LIVE.generated ? `(last checked ${agoText(Date.parse(LIVE.generated))})` : ""}: more ice time or a bigger power-play role pushes a player up.` : `Before the season, chances come from last season's ice time, age, games missed, on-ice numbers and where the analysts rank him. Once games start, this season's ice time and scoring move them several times a day.`} In testing, the top 30 each year broke out ${Math.round(100 * t.top30)}% of the time, against ${Math.round(100 * t.base_rate)}% for a typical waiver-level player.</div>
    <div class="list" id="addList">${list.map((x, i) => boCard(x, i + 1)).join("") || `<div class="empty">No breakout candidates on waivers right now.</div>`}</div>`;
  el.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => { S.addMode = b.dataset.mode; LS.set("zb-addmode", S.addMode); S.addShow = 25; renderAdds(); }));
  el.querySelectorAll("[data-apos]").forEach((b) => (b.onclick = () => { S.addPos = b.dataset.apos; renderAdds(); }));
  $("#addList").onclick = (e) => {
    const b = e.target.closest("[data-atoggle],[data-star]"); if (!b) return;
    if (b.dataset.star) { toggleStar(b.dataset.star); renderAdds(); return; }
    S.addOpen = S.addOpen === b.dataset.atoggle ? null : b.dataset.atoggle; renderAdds();
  };
}
// a drop the analysts would argue with: they rank him well above where our stats do
function analystsBacked(p) { return !!(p && p.mr && p.orank && p.mr + 12 <= p.orank && !p.rk); }
function addCard(x, rank, mode) {
  const p = x.p, open = S.addOpen === p.id;
  const tags = [];
  if (x.free) {
    const os = pickups(S.team, "ros").os;
    tags.push(`<span class="tag good" title="You have an open roster spot">No drop needed${os && os.who ? ` until ${esc(os.who.n.split(" ").slice(-1)[0])} is back` : ""}</span>`);
    if (x.drop && x.drop !== p) tags.push(`<span class="tag">Then drop <b>${esc(x.drop.n)}</b></span>`);
    else if (x.drop === p) tags.push(`<span class="tag" title="Once the roster is full again he isn't better than anyone you have">Then drop him again</span>`);
  } else tags.push(`<span class="tag">Drop <b>${esc(x.drop.n)}</b></span>`);
  if (x.drop && x.drop !== p && analystsBacked(x.drop)) tags.push(`<button class="pill gold pbtn" data-shop="${esc(x.drop.id)}" title="Analysts rank him much higher than our stats do">Analysts like ${esc(x.drop.n.split(" ").slice(-1)[0])}: find a trade first →</button>`);
  tags.push(`<span class="tag">${x.games} game${x.games === 1 ? "" : "s"} ${mode === "week" ? "this week" : "left"}</span>`);
  if (x.rosDelta != null) tags.push(`<span class="tag ${x.rosDelta >= 0 ? "good" : "bad"}" title="What this swap does to your team over the whole rest of the season">Rest of season <b>${sgn(x.rosDelta)}</b></span>`);
  { const it = injTag(p); if (it) tags.push(it); }
  if (p.rk) tags.push(`<span class="pill gold">Rookie</span>`);
  if (p.mr && p.orank && p.mr + 8 <= p.orank) tags.push(`<span class="pill good" title="Analysts rank him higher than our stats do">Analysts like him</span>`);
  const bp = boP(p); if (bp && bp >= 0.25) tags.push(`<span class="pill gold" title="Chance he plays like a regular fantasy starter this season">Breakout ${Math.round(100 * bp)}%</span>`);
  const tt = trendTag(p); if (tt) tags.push(tt);
  const ot = outTag(p); if (ot) tags.push(ot);
  tags.push(starBtn(p));
  return `<div class="card" data-id="${esc(p.id)}" style="--tc:var(--t${tierOf(valOf(p))})">
    <button class="row" data-atoggle="${esc(p.id)}" aria-expanded="${open}">
      <div class="rank">${rank}</div>${face(p)}
      <div class="who"><div class="nm">${esc(p.n)}</div><div class="mt">${posBadge(p)}<span>${esc(p.t)}${p.age ? ` · ${p.age}` : ""}</span></div></div>
      <div class="bigpts"><div class="p gainv">${sgn(x.gain)}</div><div class="l">pts ${mode === "week" ? "this wk" : "gained"}</div></div>
    </button>
    <div class="subrow">${tags.join("")}</div>
    ${open ? detailHTML(p) : ""}
  </div>`;
}

/* ---------------- trades tab ---------------- */
function plist(ps) { return ps.map((p) => `<span class="tpl">${face(p, "face sm")}<span><b>${esc(p.n)}</b><small>${esc((p.pos || p.slot).replace(/,/g, "/"))} · ${esc(p.t)}${p.age ? ` · ${p.age}` : ""}</small></span></span>`).join(""); }
function keeperNotes(give, get) {
  const n = [];
  for (const p of give) if (p.age && p.age <= 24 && (p.val ?? 0) > 0) n.push(`${p.n} is ${p.age}: young players are worth more to you next year as keepers.`);
  for (const p of get) if (p.age && p.age >= 33) n.push(`${p.n} is ${p.age}: good for this season, little keeper value.`);
  return n;
}
function mkLine(d) {
  const x = d.ratio;
  if (x == null) return "";
  if (x >= 1.1) return "By name value (how the experts rank these players) they get more than they give, so it should look good to them.";
  if (x >= 0.9) return "By name value (how the experts rank these players) it's about even, so it should look fair to them.";
  return "By name value they give up a little more, so they may ask for a small extra.";
}
function dealCard(d, i, key) {
  key = key || "deals";
  const open = S.tradeOpen === key + ":" + i;
  let body = "";
  if (open) {
    const r = tradeReasons(S.team, d.team, d);
    const notes = [];
    if (d.dropMe && d.dropMe.length) notes.push(`You'd need to drop ${d.dropMe.map((p) => esc(p.n)).join(", ")} to make room.`);
    if (d.addMe) notes.push(`You'd have an open roster spot: pick up ${esc(d.addMe.n)} (${esc(d.addMe.t)}). That's counted in your number.`);
    if (d.dropThem && d.dropThem.length) notes.push(`They'd have to drop ${d.dropThem.map((p) => esc(p.n)).join(", ")}.`);
    keeperNotes(d.give, d.get).forEach((t) => notes.push(esc(t)));
    body = `<div class="dbody">${r.lead ? `<p class="lead">${esc(r.lead)}</p>` : ""}<ul class="why">${r.me.map((t) => `<li class="${/better/.test(t) ? "good" : "bad"}">${esc(t)}</li>`).join("")}${r.them.map((t) => `<li class="info">${esc(t)}</li>`).join("")}${notes.map((t) => `<li class="info">${t}</li>`).join("")}<li class="info">${mkLine(d)}</li></ul>
      <button class="btn" data-check="${key}:${i}">Open in the trade checker</button></div>`;
  }
  return `<div class="deal ${d.likely ? "likely" : ""}">
    <button class="dh" data-deal="${key}:${i}" aria-expanded="${open}">
      <div class="dt"><span>Trade with <b>${esc(tname(d.team))}</b></span><span class="pill ${d.me < 0 ? "bad" : d.them >= 0 && d.ratio >= 0.9 ? "good" : "gold"}">${d.me < 0 ? "Doesn't help you" : d.likely ? "Likely yes" : d.them >= 0 && d.ratio >= 0.9 ? "Good for both" : d.them >= 0 ? "They may want a bit more" : "Better for you"}</span></div>
      <div class="sides"><div><div class="k">You give</div>${plist(d.give)}</div><div class="arrow">⇄</div><div><div class="k">You get</div>${plist(d.get)}</div></div>
      <div class="dn"><span>You <b class="${d.me >= 0 ? "gainv" : "lossv"}">${sgn(d.me)}</b> pts this season</span><span>Them <b class="${d.them >= 0 ? "gainv" : "lossv"}">${sgn(d.them)}</b></span><span class="tog">${open ? "Hide" : "Why?"}</span></div>
    </button>${body}</div>`;
}
function renderTrades() {
  const el = $("#tab-trades");
  const teamsOpt = META.teams.filter((t) => t.id !== S.team).sort((a, b) => a.name.localeCompare(b.name));
  if (!S.ckTeam || S.ckTeam === S.team) S.ckTeam = teamsOpt[0].id;
  const mine = rosterOf(S.team).sort((a, b) => a.n.localeCompare(b.n));
  if (S.shopId && !mine.some((p) => p.id === S.shopId)) S.shopId = null;
  el.innerHTML = `
    <div class="lede"><h2>Trades</h2><p>Deals that make <b>${esc(tname(S.team))}</b> better for the rest of the season. Each one is tested night by night in both teams' real lineups, so it counts positions, games and who'd sit. <b>Likely yes</b> means it also helps them, by our numbers and by the experts' rankings they probably go by.</p></div>
    <div class="shop">
      <label for="shopSel"><b>Shop one of your players</b><span class="note">Find the best deals built around him</span></label>
      <select class="sel" id="shopSel"><option value="">Pick a player…</option>${mine.map((p) => `<option value="${p.id}" ${p.id === S.shopId ? "selected" : ""}>${esc(p.n)} (${esc((p.pos || p.slot).replace(/,/g, "/"))}, ${fmt(rosOf(p))} pts)</option>`).join("")}</select>
    </div>
    <div class="tctl">
      <div class="chips" role="group" aria-label="Sort deals">${Object.entries(TMODES).map(([k, m]) => `<button data-tmode="${k}" aria-pressed="${S.tmode === k}">${k === "weak" ? `Fix ${POSPL[weakestSlot(S.team)]}` : m.label}</button>`).join("")}</div>
      <select class="sel" id="tteam" aria-label="Trade partner"><option value="ALL">All teams</option>${teamsOpt.map((t) => `<option value="${t.id}" ${t.id === S.tteam ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select>
    </div>
    <p class="note" id="tmodeTip" style="margin:-4px 0 10px">${esc(S.tmode === "weak" ? `Deals that bring in ${POSPL[weakestSlot(S.team)]}, your weakest position.` : TMODES[S.tmode].tip)}</p>
    <div id="shopBox"></div>
    <div id="dealsBox"><div class="empty" id="dealProg">Looking for fair deals across the league…</div></div>
    <h3 class="sectitle" style="margin-top:22px">Trade checker</h3>
    <p class="note" style="margin:-2px 0 10px">Got an offer, or have an idea? Pick the team, tap the players on each side, and see who wins.</p>
    <div class="checker">
      <select class="sel" id="ckTeam" aria-label="Trade partner">${teamsOpt.map((t) => `<option value="${t.id}" ${t.id === S.ckTeam ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select>
      <div class="ckcols"><div><div class="k">You give</div><div id="ckGive" class="cklist"></div></div><div><div class="k">You get</div><div id="ckGet" class="cklist"></div></div></div>
      <div id="ckOut" class="ckout"></div>
    </div>`;
  $("#ckTeam").onchange = (e) => { S.ckTeam = e.target.value; S.ckGive = new Set(); S.ckGet = new Set(); renderChecker(); };
  $("#shopSel").onchange = (e) => { S.shopId = e.target.value || null; S.tradeOpen = null; renderShop(); renderDealList(); };
  el.querySelectorAll("[data-tmode]").forEach((b) => (b.onclick = () => { S.tmode = b.dataset.tmode; LS.set("zb-tmode", S.tmode); S.tradeOpen = null; renderTrades(); }));
  $("#tteam").onchange = (e) => { S.tteam = e.target.value; S.tradeOpen = null; renderShopList(); renderDealList(); };
  renderChecker();
  const lists = { deals: () => S.deals || [], shop: () => S.shopDeals || [] };
  const onDeals = (e) => {
    const c = e.target.closest("[data-check]");
    if (c) {
      const [k, j] = c.dataset.check.split(":"); const d = lists[k]()[+j];
      S.ckTeam = d.team; S.ckGive = new Set(d.give.map((p) => p.id)); S.ckGet = new Set(d.get.map((p) => p.id)); $("#ckTeam").value = d.team; renderChecker(); $(".checker").scrollIntoView({ behavior: "smooth", block: "start" }); return;
    }
    const b = e.target.closest("[data-deal]"); if (!b) return;
    S.tradeOpen = S.tradeOpen === b.dataset.deal ? null : b.dataset.deal;
    const k = b.dataset.deal.split(":")[0];
    if (k === "shop") renderShopList(); else renderDealList();
  };
  $("#dealsBox").onclick = onDeals; $("#shopBox").onclick = onDeals;
  renderShop();
  const team = S.team;
  tradeSearch(team, (i, n, T) => { const pg = $("#dealProg"); if (pg) pg.textContent = `Looking for fair deals… checking ${T.name} (${i + 1} of ${n})`; }).then((all) => {
    if (S.team !== team || S.tab !== "trades") return;
    S.dealPool = all;
    renderDealList();
  });
  if (S.shopId) setTimeout(() => { const x = $("#shopBox"); if (x) x.scrollIntoView({ behavior: "smooth", block: "start" }); }, 50);
}
function renderDealList() {
  const box = $("#dealsBox"); if (!box || !S.dealPool) return;
  if (S.shopId) { box.innerHTML = ""; return; }   // shopping one player: his list is shown instead
  S.deals = pickDeals(S.dealPool, S.tmode, S.tteam);
  const who = S.tteam && S.tteam !== "ALL" ? ` with ${esc(tname(S.tteam))}` : "";
  box.innerHTML = S.deals.length ? `<div class="deals">${S.deals.map((d, i) => dealCard(d, i, "deals")).join("")}</div>`
    : `<div class="empty">No deal${who} fits "${esc(S.tmode === "weak" ? "Fix weak spot" : TMODES[S.tmode].label)}" right now. Try another view, or build your own in the checker below.</div>`;
}
function renderShop() {
  const box = $("#shopBox"); if (!box) return;
  if (!S.shopId) { box.innerHTML = ""; S.shopDeals = null; S.shopPool = null; return; }
  S.shopPool = null;
  const p = player(S.shopId), team = S.team, id = S.shopId;
  box.innerHTML = `<div class="empty" id="shopProg">Searching every team for deals built around ${esc(p.n)}…</div>`;
  shopSearch(team, id, (i, n, T) => { const pg = $("#shopProg"); if (pg) pg.textContent = `Searching for ${p.n}… checking ${T.name} (${i + 1} of ${n})`; }).then((deals) => {
    if (S.team !== team || S.shopId !== id || S.tab !== "trades") return;
    S.shopPool = deals;
    renderShopList();
    renderDealList();
  });
}
function renderShopList() {
  const box = $("#shopBox"); if (!box) return;
  if (!S.shopId || !S.shopPool) { box.innerHTML = S.shopId ? box.innerHTML : ""; return; }
  const p = player(S.shopId);
  let deals = pickDeals(S.shopPool, S.tmode, S.tteam, 8, S.shopId);
  if (!deals.length) deals = S.shopPool.filter((d) => !S.tteam || S.tteam === "ALL" || d.team === S.tteam).sort((a, b) => b.me - a.me).slice(0, 5);
  S.shopDeals = deals;
  const helps = deals.filter((d) => d.me > 0);
  const lead = !deals.length ? `No team has a fair deal for ${esc(p.n)} right now.`
    : helps.length ? `Best deals for ${esc(p.n)}, most helpful to you first.${analystsBacked(p) ? ` The experts rate him higher than our numbers do, so other managers should value him.` : ""}`
    : `Every fair deal for ${esc(p.n)} makes your team a bit worse, so keeping him is the better move. Here are the closest ones anyway.`;
  box.innerHTML = `<div class="shophead"><b>Deals for ${esc(p.n)}</b><button class="linkbtn" id="shopClear">Back to all deals</button></div><p class="note shoplead">${lead}</p>${deals.length ? `<div class="deals">${deals.map((d, i) => dealCard(d, i, "shop")).join("")}</div>` : ""}`;
  const c = $("#shopClear"); if (c) c.onclick = () => { S.shopId = null; S.tradeOpen = null; $("#shopSel").value = ""; renderShopList(); renderDealList(); };
}
// every deal that sends this player out: him for one, him for two, or him plus a spare part for one
function shopSearch(me, pid, onProgress) {
  const key = "shop|" + pid + "|" + rosterKey(me) + "|" + META.teams.map((t) => rosterKey(t.id)).join(";") + JSON.stringify(S.gsOv) + fromDay() + (LIVE ? LIVE.generated : "");
  if (MEMO.has(key)) return Promise.resolve(MEMO.get(key));
  const A = rosterOf(me), vA = vOf(A), P = player(pid);
  const spare = A.filter((x) => x.id !== pid && !onIR(x.id)).map((x) => ({ x, c: vA - vOf(A.filter((y) => y !== x)) })).sort((a, b) => a.c - b.c).slice(0, 3).map((o) => o.x);
  const others = META.teams.filter((t) => t.id !== me);
  const found = [];
  let i = 0;
  return new Promise((resolve) => {
    const step = () => {
      const T = others[i];
      if (!T) {
        for (const d of found) d.likely = d.them >= 0 && d.ratio >= 1.0 && d.me > 0;
        const out = found;
        MEMO.set(key, out); resolve(out); return;
      }
      if (onProgress) onProgress(i, others.length, T);
      const Bt = rosterOf(T.id);
      const targets = Bt.filter((q) => !onIR(q.id)).sort((a, b) => rosOf(b) - rosOf(a)).slice(0, 14);
      const tryDeal = (give, get) => {
        const ratio = nameRatio(give, get);
        if (ratio < 0.85 || ratio > 2.2) return;
        const r = evalTrade(me, T.id, give, get);
        if (r.them < -15) return;
        found.push({ team: T.id, give, get, ratio, me: r.me, them: r.them, dropMe: r.a.dropped, addMe: r.a.added, dropThem: r.b.dropped, addThem: r.b.added });
      };
      for (const q of targets) tryDeal([P], [q]);
      const t8 = targets.slice(0, 8);
      for (let x = 0; x < t8.length; x++) for (let y = x + 1; y < t8.length; y++) tryDeal([P], [t8[x], t8[y]]);
      for (const sp of spare) for (const q of t8) tryDeal([P, sp], [q]);
      i++;
      setTimeout(step, 0);
    };
    setTimeout(step, 0);
  });
}
function shopPlayer(id) { S.shopId = id; S.tradeOpen = null; setTab("trades"); }
function renderChecker() {
  S.ckGive = S.ckGive || new Set(); S.ckGet = S.ckGet || new Set();
  const mine = rosterOf(S.team).sort((a, b) => rosOf(b) - rosOf(a));
  const theirs = rosterOf(S.ckTeam).sort((a, b) => rosOf(b) - rosOf(a));
  const item = (p, set, side) => `<button class="ckp ${set.has(p.id) ? "on" : ""}" data-side="${side}" data-id="${esc(p.id)}" aria-pressed="${set.has(p.id)}"><span class="box"></span><span class="nm">${esc(p.n)}<small>${esc((p.pos || p.slot).replace(/,/g, "/"))} · ${esc(p.t)}${hurt(p) ? " · hurt" : ""}</small></span><b class="num">${fmt(rosOf(p))}</b></button>`;
  $("#ckGive").innerHTML = mine.map((p) => item(p, S.ckGive, "give")).join("");
  $("#ckGet").innerHTML = theirs.map((p) => item(p, S.ckGet, "get")).join("");
  $(".ckcols").onclick = (e) => {
    const b = e.target.closest(".ckp"); if (!b) return;
    const set = b.dataset.side === "give" ? S.ckGive : S.ckGet;
    if (set.has(b.dataset.id)) set.delete(b.dataset.id); else set.add(b.dataset.id);
    renderChecker();
  };
  const out = $("#ckOut");
  const give = mine.filter((p) => S.ckGive.has(p.id)), get = theirs.filter((p) => S.ckGet.has(p.id));
  if (!give.length && !get.length) { out.innerHTML = `<div class="note">Tap players on both sides. Numbers next to names are points for the rest of the season.</div>`; return; }
  const v = tradeView(S.team, S.ckTeam, give, get);
  const d = { team: S.ckTeam, give, get, me: v.me, them: v.them, ratio: v.ratio, a: v.a, b: v.b };
  const r = tradeReasons(S.team, S.ckTeam, d);
  let verdict, tone;
  if (v.me >= 5 && v.them >= 0 && v.ratio >= 0.9) { verdict = "Good for both teams. Worth proposing."; tone = "good"; }
  else if (v.me >= 5 && v.them >= 0) { verdict = "Good for both lineups, but by name value they give up more, so expect them to ask for a bit extra."; tone = "good"; }
  else if (v.me >= 5 && v.ratio >= 1) { verdict = "Good for you. It hurts their lineup a bit, but by name value they win, so they might take it."; tone = "good"; }
  else if (v.me >= 5) { verdict = "Good for you, but it hurts them, so they'll probably say no."; tone = "good"; }
  else if (v.me > -5) { verdict = "About even for you. Only do it if you like the players you're getting."; tone = ""; }
  else { verdict = `This makes your team worse by about ${Math.round(-v.me)} points. Pass, unless they add more.`; tone = "bad"; }
  const notes = [];
  if (v.a.dropped.length) notes.push(`You'd need to drop ${v.a.dropped.map((p) => esc(p.n)).join(", ")} to stay at ${META.roster.max} players.`);
  if (v.a.added) notes.push(`You'd have an open spot for ${esc(v.a.added.n)} off waivers (included).`);
  keeperNotes(give, get).forEach((t) => notes.push(esc(t)));
  out.innerHTML = `<div class="verdict ${tone}"><b>${verdict}</b>
    <div class="vn"><span>You <b class="${v.me >= 0 ? "gainv" : "lossv"}">${sgn(v.me)}</b> pts this season</span><span>Them <b class="${v.them >= 0 ? "gainv" : "lossv"}">${sgn(v.them)}</b></span></div>
    ${r.lead ? `<p class="lead">${esc(r.lead)}</p>` : ""}<ul class="why">${r.me.map((t) => `<li class="${/better/.test(t) ? "good" : "bad"}">${esc(t)}</li>`).join("")}${r.them.map((t) => `<li class="info">${esc(t)}</li>`).join("")}${notes.map((t) => `<li class="info">${t}</li>`).join("")}<li class="info">${mkLine(d)}</li></ul></div>`;
}

/* ---------------- players tab ---------------- */
function boardShell() {
  const el = $("#tab-board");
  el.innerHTML = `
    <div class="lede"><h2>Players</h2><p>Every player's projection for this league's scoring, blended with ${META.experts.n} analyst sources. Tap anyone for the full story.</p></div>
    <div class="controls">
      <div class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input id="q" type="search" placeholder="Find a player or team" autocomplete="off" aria-label="Find a player"><button class="clr" id="qclr" aria-label="Clear search" hidden>×</button></div>
      <div class="chips" id="posChips" role="group" aria-label="Position"></div>
      <select class="sel" id="sortSel" aria-label="Sort by">
        <option value="ros">Most points, rest of season</option><option value="val">Most value</option><option value="week">Most points this week</option><option value="exp">Analysts' favorites</option>
      </select>
      <label class="chk"><input type="checkbox" id="faOnly"> Free agents only</label>
    </div>
    <div class="list" id="list"></div>
    <button class="more" id="more" hidden>Show more</button>`;
  $("#q").addEventListener("input", (e) => { S.q = e.target.value; S.show = 60; $("#qclr").hidden = !S.q; renderBoardList(); });
  $("#qclr").onclick = () => { S.q = ""; $("#q").value = ""; $("#qclr").hidden = true; renderBoardList(); $("#q").focus(); };
  $("#sortSel").onchange = (e) => { S.sort = e.target.value; S.show = 60; renderBoardList(); };
  $("#faOnly").onchange = (e) => { S.faOnly = e.target.checked; LS.set("zb-fa", S.faOnly); S.show = 60; renderBoardList(); };
  $("#more").onclick = () => { S.show += 60; renderBoardList(); };
  $("#list").addEventListener("click", onListClick);
}
function renderBoard() {
  const chips = [["ALL", "All"], ["C", "C"], ["W", "W"], ["D", "D"], ["G", "G"], ["STAR", "★"]];
  $("#posChips").innerHTML = chips.map(([k, l]) => `<button data-pos="${k}" aria-pressed="${S.pos === k}" ${k === "STAR" ? 'aria-label="Starred players"' : ""}>${l}</button>`).join("");
  $("#posChips").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.pos = b.dataset.pos; S.show = 60; renderBoard(); };
  $("#sortSel").value = S.sort;
  $("#faOnly").checked = S.faOnly;
  $("#q").value = S.q; $("#qclr").hidden = !S.q;
  renderBoardList();
}
function renderBoardList() {
  const own = owners();
  const q = fold(S.q).trim();
  const key = S.pos === "ALL" || S.pos === "STAR" ? "ALL" : S.pos;
  let rows = B.players.slice();
  if (S.faOnly && !q) rows = rows.filter((p) => !own[p.id]);
  if (S.pos === "STAR") rows = rows.filter((p) => S.stars[p.id]);
  else if (key !== "ALL") rows = rows.filter((p) => elig(p).includes(key));
  if (q) rows = rows.filter((p) => fold(p.n).includes(q) || fold(p.t) === q);
  const wk = windowDays("week");
  const ros = (p) => (key === "ALL" ? rosOf(p) : rosAt(p, key));
  const sorters = {
    ros: (a, b) => ros(b) - ros(a),
    val: (a, b) => (valOf(b) ?? -999) - (valOf(a) ?? -999),
    week: (a, b) => bestRate(b) * gamesIn(b, wk) - bestRate(a) * gamesIn(a, wk),
    exp: (a, b) => (a.mr ?? 999) - (b.mr ?? 999) || ros(b) - ros(a),
  };
  rows.sort(sorters[S.sort] || sorters.ros);
  const list = $("#list");
  if (!rows.length) {
    list.innerHTML = `<div class="empty">${S.pos === "STAR" ? "No starred players yet. Tap the star on any player to build a watch list." : q ? "No player matches that search." : "Nobody here."}</div>`;
    $("#more").hidden = true; return;
  }
  list.innerHTML = rows.slice(0, S.show).map((p, i) => cardHTML(p, i + 1, key, own[p.id], wk)).join("");
  $("#more").hidden = rows.length <= S.show;
  $("#more").textContent = `Show more (${rows.length - S.show} left)`;
}
function starBtn(p) {
  const star = !!S.stars[p.id];
  return `<button class="star" data-star="${esc(p.id)}" aria-pressed="${star}" aria-label="${star ? "Remove from" : "Add to"} watch list"><svg viewBox="0 0 24 24" fill="${star ? "currentColor" : "none"}" stroke="currentColor" stroke-width="1.8"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/></svg></button>`;
}
function cardHTML(p, rank, key, owner, wk) {
  const v = valOf(p), tier = tierOf(v), mine = owner === S.team, open = S.open === p.id;
  const tags = [];
  tags.push(owner ? `<span class="tag ${mine ? "warn" : ""}"><b>${mine ? "Your team" : esc(tshort(owner))}</b></span>` : `<span class="tag good"><b>Free agent</b></span>`);
  if (v != null) tags.push(`<span class="tag ${v >= 0 ? "good" : "bad"}" title="Season points above the best player usually on waivers at his position"><b>${sgn(v)}</b> value</span>`);
  const g = gamesIn(p, wk);
  tags.push(`<span class="tag">${g} game${g === 1 ? "" : "s"} this week</span>`);
  if (p.mr) tags.push(`<span class="tag" title="Where the analyst consensus ranks him among ${POSPL[p.slot]}">Analysts: <b>${ordinal(p.mr)} ${esc(p.slot)}</b></span>`);
  { const it = injTag(p); if (it) tags.push(it); }
  if (p.rk) tags.push(`<span class="pill gold">Rookie</span>`);
  const bp2 = boP(p); if (bp2 && bp2 >= 0.25) tags.push(`<span class="pill gold" title="Chance he plays like a regular fantasy starter this season">Breakout ${Math.round(100 * bp2)}%</span>`);
  const tt2 = trendTag(p); if (tt2) tags.push(tt2);
  const ot2 = outTag(p); if (ot2) tags.push(ot2);
  if (p.nt) tags.push(`<span class="pill bad">No NHL contract</span>`);
  if (p.slot === "G" && S.gsOv[p.id] != null) tags.push(`<span class="pill gold">Your starts: ${S.gsOv[p.id]}</span>`);
  tags.push(starBtn(p));
  const shown = key === "ALL" ? rosOf(p) : rosAt(p, key);
  return `<div class="card ${mine ? "mineP" : ""}" data-id="${esc(p.id)}" style="--tc:var(--t${tier})">
    <button class="row" data-toggle="${esc(p.id)}" aria-expanded="${open}">
      <div class="rank">${rank}</div>${face(p)}
      <div class="who"><div class="nm">${esc(p.n)}</div>
        <div class="mt">${posBadge(p)}<span>${esc(p.t || "No team")}${p.age ? ` · ${p.age}` : ""}</span><span class="pill tier">${TIER[tier]}</span></div></div>
      <div class="bigpts"><div class="p">${fmt(shown)}</div><div class="l">${todayET() < SEASON_START ? "season pts" : "pts left"}</div></div>
    </button>
    <div class="subrow">${tags.join("")}</div>
    ${open ? detailHTML(p) : ""}
  </div>`;
}
function detailHTML(p) {
  const parts = [];
  const why = (p.ch || []).map(([tone, txt]) => `<li class="${tone}">${esc(txt)}</li>`).join("");
  const v = valOf(p);
  let lead = "";
  if (v != null) lead = `<li class="info">${v >= 0 ? `About <b>${Math.round(v)}</b> more season points than the best ${POSNAME[p.slot].toLowerCase()} usually on waivers.` : `Projects below a typical waiver-wire ${POSNAME[p.slot].toLowerCase()} in this league.`}</li>`;
  if (p.mp != null && p.mk != null && !p.rk) {
    const pn = POSNAME[p.slot].toLowerCase();
    const w = p.wx != null ? Math.round(100 * (1 - p.wx)) : null;
    lead += `<li class="info">Our stats say <b>${fmt(p.mp)}</b> points. The analysts' consensus (${p.mr ? ordinal(p.mr) + " " + pn : "unranked"}) works out to about <b>${fmt(p.mk)}</b> in this scoring. His number, <b>${fmt(ptsOf(p))}</b>, is ${w != null ? `${w}% ours` : "a blend"}.</li>`;
  }
  const bpd = boP(p);
  if (bpd != null) lead += `<li class="good">Breakout chance: <b>${Math.round(100 * bpd)}%</b> that he plays like a regular fantasy starter this season (typical for a player projected like him: ${Math.round(100 * p.bo[1])}%).${p.bw && p.bw.length ? " Why: " + p.bw.map(esc).join("; ") + "." : ""}</li>`;
  const lv = liveOf(p);
  if (lv && lv.n) lead += `<li class="info">This season so far: ${lv.n} game${lv.n === 1 ? "" : "s"}, ${fmt(lv.fp)} fantasy points${lv.toi ? `, ${fmt(lv.toi, 1)} min a game` : ""}${lv.pp ? ` (${fmt(lv.pp, 1)} on the power play)` : ""}. His projection has moved ${sgn(100 * ((liveMult(p) || 1) - 1))}% since the season started.</li>`;
  const ij = injOf(p);
  if (hurt(p) || dtd(p)) lead = `<li class="bad">${esc(injWhat(p))}${hurt(p) && !(dtd(p) && !missedGames(p)) ? `: expected back around <b>${esc(dLabel(p.ret, { month: "short", day: "numeric" }))}</b>${missedGames(p) ? `, so he misses about ${missedGames(p)} of his team's games` : ""}` : ": he might miss a game"}.${ij ? ` From ESPN's NHL injury report (${esc(dLabel(ij.d, { month: "short", day: "numeric" }))}), checked several times a day; every projection on this site already counts it.` : ""}</li>` + lead;
  if (lv && lv.out) lead += `<li class="bad">His team has played ${lv.out} games in the last 10 days and he hasn't played in any. He may be hurt or scratched: check the news before starting him.</li>`;
  if (p.unknown) lead = `<li class="info">Not in this site's player list, so there's no projection for him.</li>`;
  parts.push(`<div><h4>Why</h4><ul class="why">${lead}${why}</ul></div>`);
  if (p.brk) {
    const vals = Object.entries(p.brk);
    const mx = Math.max(1, ...vals.map(([, x]) => Math.abs(x)));
    const scale = p.slot === "G" && S.gsOv[p.id] != null ? ptsOf(p) / p.pts : 1;
    parts.push(`<div><h4>Where his ${fmt(ptsOf(p))} season points come from</h4><div class="brk">${vals.map(([k, x]) => {
      const y = x * scale;
      return `<div class="r"><span>${esc(k)}</span><span class="t"><i class="${y < 0 ? "neg" : ""}" style="left:0;width:${(100 * Math.abs(x)) / mx}%"></i></span><b>${sgn(y)}</b></div>`;
    }).join("")}</div>${p.slot !== "G" && Object.keys(p.slotpts).length > 1 ? `<p class="note" style="margin:8px 0 0">${Object.entries(p.slotpts).map(([s, x]) => `As a ${POSNAME[s].toLowerCase()}: ${fmt(x)} pts`).join(" · ")}. This league pays wingers and defensemen more per goal and assist, and pays centers for faceoffs.</p>` : ""}</div>`);
  }
  if (p.line) {
    const L = p.line, r = p.slot === "G" ? ptsOf(p) / p.pts : 1;
    const kv = p.slot === "G"
      ? [["Starts", fmt(gsOf(p))], ["Wins", fmt(L.w * r)], ["Saves", fmt(L.sv * r)], ["Goals against", fmt(L.ga * r)], ["Shutouts", fmt(L.so * r, 1)], ["Save %", L.svp ? L.svp.toFixed(3).replace(/^0/, "") : "–"]]
      : [["Games", fmt(p.gp)], ["Goals", fmt(L.g)], ["Assists", fmt(L.a)], ["Plus/minus", sgn(L.pm)], ["Penalty minutes", fmt(L.pim)], ["Hits", fmt(L.hit)], ["Blocked shots", fmt(L.blk)], ["Faceoff wins", fmt(L.fow)], ["Shots on goal", fmt(L.sog)], ["Ice time a game", L.toi ? `${fmt(L.toi, 1)} min` : "–"], ["Power-play time", L.pptoi ? `${fmt(L.pptoi, 1)} min` : "–"]];
    parts.push(`<div><h4>2026-27 projection</h4><div class="kv">${kv.map(([a, b]) => `<span>${a}</span><span>${b}</span>`).join("")}</div></div>`);
  }
  if (p.hist && p.hist.length) {
    const G = p.slot === "G";
    const head = G ? ["Season", "Team", "Fantasy pts", "GP", "Starts", "W", "Saves", "GA", "SO", "Save %"]
      : ["Season", "Team", "Fantasy pts", "GP", "G", "A", "+/-", "PIM", "Hits", "Blocks", "FO wins", "Ice time", "PP time", "Shots"];
    const body = p.hist.map((h0) => {
      const h = [h0[0], h0[1], h0[h0.length - 1], ...h0.slice(2, -1)];
      return `<tr>${h.map((x, i) => {
        let y = x;
        if (G && i === 9 && x != null) y = x.toFixed(3).replace(/^0/, "");
        if (!G && i === 6) y = sgn(x);
        return `<td class="${i === 2 ? "hl" : ""}">${esc(y ?? "–")}</td>`;
      }).join("")}</tr>`;
    }).join("");
    parts.push(`<div class="histwrap"><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`);
  }
  const acts = [];
  if (p.slot === "G" && p.gpg) {
    acts.push(`<span class="note">Know the depth chart better? Set his season starts:</span><span class="stepper"><button data-gs="${esc(p.id)}" data-d="-5" aria-label="5 fewer starts">−</button><span>${fmt(gsOf(p))}</span><button data-gs="${esc(p.id)}" data-d="5" aria-label="5 more starts">+</button></span>`);
    if (S.gsOv[p.id] != null) acts.push(`<button class="btn" data-gsreset="${esc(p.id)}">Back to our ${fmt(p.gs)}</button>`);
  }
  if (owners()[p.id] === S.team) acts.unshift(`<button class="btn primary" data-shop="${esc(p.id)}">Find trades for ${esc(p.n.split(" ").slice(-1)[0])}</button>`);
  if (acts.length) parts.push(`<div class="acts">${acts.join("")}</div>`);
  return `<div class="detail">${parts.join("")}</div>`;
}
function toggleStar(id) { if (S.stars[id]) delete S.stars[id]; else S.stars[id] = 1; LS.set("zb-stars", S.stars); }
function onListClick(e) {
  const sh = e.target.closest("[data-shop]"); if (sh) { shopPlayer(sh.dataset.shop); return; }
  const tg = e.target.closest("[data-toggle],[data-star],[data-gs],[data-gsreset]");
  if (!tg) return;
  const d = tg.dataset;
  if (d.toggle) { S.open = S.open === d.toggle ? null : d.toggle; renderBoardList(); return; }
  if (d.star) { toggleStar(d.star); renderBoardList(); return; }
  if (d.gs) {
    const p = PL.get(d.gs); const cur = gsOf(p);
    S.gsOv[d.gs] = Math.max(0, Math.min(84, Math.round((cur + Number(d.d)) / 5) * 5)); LS.set("zb-gs", S.gsOv); clearCaches(); renderBoardList(); return;
  }
  if (d.gsreset) { delete S.gsOv[d.gsreset]; LS.set("zb-gs", S.gsOv); clearCaches(); renderBoardList(); }
}

/* ---------------- league ---------------- */
function renderLeague() {
  const from = fromDay(), per = periodOf(from);
  const wk = daysIn(from, lastDayOf(per));
  const rows = META.teams.map((t) => {
    const r = rosterOf(t.id);
    return { t, r, v: memo("ros|" + rosterKey(t.id) + "|" + from + JSON.stringify(S.gsOv), () => rangeValue(r, daysIn(from, SEASON_END))), w: rangeValue(r, wk) };
  }).sort((a, b) => b.v - a.v);
  const W = {}; rows.forEach((x) => (W[x.t.id] = x.w));
  const mx = Math.max(...rows.map((x) => x.v), 1);
  const m = META.matchups.find((x) => x[0] === per.n);
  const el = $("#tab-league");
  el.innerHTML = `<div class="lede"><h2>League</h2><p>This week's matchups and every team's projected points for the rest of the season, with each team setting its best lineup every night. Tap a team to see its roster.</p></div>
  ${m ? `<h3 class="sectitle">${isPlayoffs(per.n) ? "Playoffs · " : ""}Week ${per.n}${todayET() > per.s ? " · rest of week" : ""}</h3>
  <div class="mups">${m[1].map(([a, h]) => {
    const fav = W[a] >= W[h] ? a : h;
    return `<div class="mup ${a === S.team || h === S.team ? "me" : ""}"><div class="${fav === a ? "fav" : ""}"><span>${esc(tname(a))}</span><b class="num">${fmt(W[a])}</b></div><div class="${fav === h ? "fav" : ""}"><span>${esc(tname(h))}</span><b class="num">${fmt(W[h])}</b></div></div>`;
  }).join("")}</div>` : ""}
  <h3 class="sectitle">Rest of season</h3>
  <div class="teams">${rows.map((x, i) => {
    const open = !!S.leagueOpen[x.t.id];
    const lu = fillLineup(x.r);
    const lines = [];
    for (const s of ["C", "W", "D", "G"]) for (const y of lu.slots[s]) lines.push([s, y.p, rosAt(y.p, s)]);
    for (const p of lu.bench) lines.push(["BN", p, rosOf(p)]);
    return `<div class="tcard ${x.t.id === S.team ? "me" : ""}">
      <button class="th" data-team="${x.t.id}" aria-expanded="${open}"><div class="rk">${i + 1}</div>
        <div><div class="tn">${esc(x.t.name)}</div><div class="ts">${x.r.length} players · ${x.r.filter(hurt).length} hurt</div></div>
        <div class="tp"><b>${fmt(x.v)}</b><small>proj pts</small></div></button>
      <div class="meter"><i style="width:${(100 * x.v) / mx}%"></i></div>
      ${open ? `<div class="body">${lines.map(([s, p, pts]) => `<div class="mini"><span class="pos">${s}</span><span>${esc(p.n)} <span class="note">${esc(p.t)}${hurt(p) ? " · hurt" : ""}</span></span><b>${fmt(pts)}</b></div>`).join("")}</div>` : ""}
    </div>`;
  }).join("")}</div>`;
  el.querySelectorAll("[data-team]").forEach((b) => (b.onclick = () => { S.leagueOpen[b.dataset.team] = !S.leagueOpen[b.dataset.team]; renderLeague(); }));
}

/* ---------------- how it works ---------------- */
function renderHow() {
  const sc = META.scoring, bt = META.backtest, ex = META.expTest;
  const el = $("#tab-how");
  const row = (k, c, w, d) => `<tr><td>${k}</td><td>${c}</td><td>${w}</td><td>${d}</td></tr>`;
  el.innerHTML = `<div class="prose">
  <div class="lede"><h2>Help</h2><p>Hockey in plain English, then how this site's numbers are made and how much to trust them.</p></div>
  <h3>Hockey in two minutes</h3>
  <ul>
    <li>Each team has six players on the ice: a <b>goalie (G)</b> who stops shots, two <b>defensemen (D)</b> who guard their own net, and three forwards: a <b>center (C)</b> in the middle and two <b>wingers (W)</b> on the sides. Players rotate in short shifts.</li>
    <li>An NHL team plays about 3 or 4 games a week, 84 games a season. <b>Your players only score on nights their team plays.</b></li>
  </ul>
  <h3>Your job in this league</h3>
  <ol>
    <li><b>Set your lineup every game day.</b> Fill ${CAP.C} C, ${CAP.W} W, ${CAP.D} D and ${CAP.G} G spots with players who play that night; the ${BENCH} on your bench score nothing. My team works it out for you.</li>
    <li><b>Win your weekly matchup.</b> Each week (Monday to Sunday) you face one team. Most total points wins.</li>
    <li><b>Improve the roster.</b> Up to 3 free-agent pickups a week ($2 a claim, $1 a drop), and trades any time. Pickups and Trades show the best moves.</li>
  </ol>
  <h3>How players score here</h3>
  <ul>
    <li><b>Goals and assists</b> (an assist is a pass that leads to a goal): worth more for wingers and much more for defensemen, 4 points each.</li>
    <li><b>Faceoff wins</b> (centers only): every stoppage restarts with a puck drop between two centers. A busy center wins 8 to 12 a game, a quarter point each, so they add up.</li>
    <li><b>Hits and blocked shots</b>: a quarter point each. Tough, physical players pile these up.</li>
    <li><b>Penalty minutes</b>: half a point a minute. <b>Plus/minus</b>: +1 when you're on the ice for a goal by your team, −1 for one against.</li>
    <li><b>Goalies</b>: 3 for a win, a quarter point per save, −1 per goal allowed, 4 for a shutout. Only the goalie who starts gets anything, which is why starts matter so much.</li>
  </ul>
  <p><b>What wins here:</b> defensemen who score, centers who take lots of faceoffs, physical players who hit and block, and goalies who start most nights.</p>
  <h3>Which positions matter most</h3>
  <p>What counts is how much better a player is than what you could get for free on waivers at the same position. Season points above waiver level:</p>
  <div class="tablewrap"><table><thead><tr><th>Position</th><th>Best</th><th>12th best</th><th>24th best</th><th>You start</th></tr></thead><tbody>${posValueRows()}</tbody></table></div>
  <ol>
    <li><b>Defensemen are the most valuable.</b> Every goal and assist is worth 4 points, so a scoring defenseman scores like a top forward, and there are few of them: the gap from the best to the 12th best is the biggest of any position. Assists are most of a defenseman's points, so the ones who run the power play are gold. You start 4.</li>
    <li><b>Elite centers are next.</b> Centers score the most raw points because faceoff wins are about 40% of their total. But the center you can grab on waivers is also good, so only the top dozen or so really set you apart, and you only start 2. A center who rarely takes faceoffs loses most of that edge.</li>
    <li><b>Wingers are the deepest position.</b> The 24th-best winger is still well above waiver level and lots of them look alike. They're the easiest to find in trades and on waivers, so don't pay a premium except for true stars. You start 4.</li>
    <li><b>Goalies</b> have the smallest gap between a top starter and a waiver goalie over a season. What matters is starts: a goalie only scores when he plays. With 2 goalie spots a night, carry 3 so both spots are filled on most nights.</li>
  </ol>
  <h3>Breakouts and in-season updates</h3>
  <ul>
    <li><b>Breakout chance</b> is the chance a player projected below waiver level ends the season playing like a regular fantasy starter. Before the season it comes from last season's ice time, age, games missed, on-ice numbers and where the analysts rank him. Tested on nine past seasons, the model's top 30 each year broke out ${Math.round(100 * META.breakout.test.top30)}% of the time, against ${Math.round(100 * META.breakout.test.base_rate)}% for a typical waiver-level player. Honest caveat: most of that skill is knowing who's close to the line already; the extra signals sharpen it a bit.</li>
    <li><b>Once games start</b>, a refresh job pulls this season's stats from the NHL several times a day and moves every projection. How fast depends on the stat, tested on five past seasons: faceoffs and hits settle within a couple of weeks; goals barely count early because hot shooting streaks don't last. More ice time or a bigger power-play role adds on top. Chasing hot starts alone was right only ${esc(META.breakout.test.hot_hold)} of the time; players this update flags as breaking out held up about ${Math.round(100 * META.breakout.test.flag_hold)}% of the time.</li>
    <li><b>Pickups</b> give a small bonus for breakout upside (a quarter of the extra points a breakout usually brings, since you can drop him if it doesn't happen), so between two similar free agents the one with more upside ranks first.</li>
    <li><b>Not playing lately</b> means his team played 3 or more games in the last 10 days and he didn't play: usually an injury or healthy scratch.</li>
  </ul>
  <h3>Words you'll see</h3>
  <ul>
    <li><b>Power play (PP1, PP2):</b> when the other team has a player in the penalty box. The top unit (PP1) gets the best scoring chances.</li>
    <li><b>Top line / 3rd line:</b> forwards play in groups of three. The top line plays the most and scores the most.</li>
    <li><b>Starter vs backup goalie:</b> starters play roughly 55 to 65 games; backups play the rest.</li>
    <li><b>IR (injured reserve):</b> 4 extra roster spots for injured players that don't count toward your 18.</li>
    <li><b>Keepers:</b> this league lets each team keep 7 players for next season, so young players are worth a little extra to you.</li>
  </ul>
  <h3>This league's scoring</h3>
  <p>Head-to-head points, one matchup a week. ${META.firstPlayoff - 1} regular-season weeks, then ${META.playoffTeams} teams make the playoffs (the last round runs two weeks). Lineups: ${CAP.C} centers, ${CAP.W} wingers, ${CAP.D} defensemen, ${CAP.G} goalies, and ${BENCH} bench spots, set every day.</p>
  <div class="tablewrap"><table><thead><tr><th>Skater stat</th><th>Center</th><th>Wing</th><th>Defense</th></tr></thead><tbody>
    ${row("Goal", sc.C.g, sc.W.g, sc.D.g)}${row("Assist", sc.C.a, sc.W.a, sc.D.a)}${row("Faceoff win", sc.C.fow, sc.W.fow, sc.D.fow)}
    ${row("Hat trick (bonus)", sc.common.ht, sc.common.ht, sc.common.ht)}${row("Plus/minus", sc.common.pm, sc.common.pm, sc.common.pm)}${row("Penalty minute", sc.common.pim, sc.common.pim, sc.common.pim)}
    ${row("Hit", sc.common.hit, sc.common.hit, sc.common.hit)}${row("Blocked shot", sc.common.blk, sc.common.blk, sc.common.blk)}
  </tbody></table></div>
  <div class="tablewrap"><table><thead><tr><th>Goalie stat</th><th>Points</th></tr></thead><tbody>
    <tr><td>Win</td><td>${sc.goalie.w}</td></tr><tr><td>Save</td><td>${sc.goalie.sv}</td></tr><tr><td>Goal against</td><td>${sc.goalie.ga}</td></tr><tr><td>Shutout</td><td>${sc.goalie.so}</td></tr><tr><td>Goal / assist</td><td>${sc.goalie.g} / ${sc.goalie.a}</td></tr>
  </tbody></table></div>
  <p><b>What that means:</b> defensemen get 4 points for every goal and assist. Centers who take lots of faceoffs pile up points (a heavy-faceoff center wins 700+ a season, about 175 points). Shots on goal and power-play points aren't scored. Goalies earn about 5 points a game, so starts matter most.</p>

  <h3>Projected points</h3>
  <p>Built in two steps from the NHL's own stats, going back to 2010-11.</p>
  <ul>
    <li><b>Step 1, a base projection</b> from the last three seasons: recent seasons count most, goals come from shot volume times career finishing, small samples get pulled toward a typical player, and age matters (still improving at 23 and under, slipping after 30).</li>
    <li><b>Step 2, a learning model</b> trained on 13 seasons of "what we projected vs. what happened." It catches shooting luck, ice time and power-play time, and unrepeatable on-ice scoring rates.</li>
    <li><b>Goalies:</b> starts come from recent workload and how many goalies on his team want the same net. Then totals are pulled toward the middle, because top projected goalies kept coming in lower in testing.</li>
  </ul>

  <h3>The ${META.experts.n} analyst sources</h3>
  <p>On top of our stats, every player's number is pulled toward a consensus of these sources: ${META.experts.sources.map(esc).join("; ")}. The consensus sets <i>who</i> is better than whom at each position. Our model still decides how much each position is worth in this league's scoring, because none of those rankings use this league's rules (faceoffs, hits and 4-point defensemen).</p>
  <p><b>How far each player moves toward the analysts was tested, not guessed.</b> We lined up four seasons of preseason expert rankings (2022-23 to 2025-26: Daily Faceoff, Razzball, The Hockey News, FantraxHQ, theScore and a multi-site consensus) against what actually happened in this league's scoring. "Rank match" is 1 for a perfect ranking; "miss" is the average season-total miss in points.</p>
  <div class="tablewrap"><table><thead><tr><th>4 past seasons</th><th>Rank match</th><th>Miss</th></tr></thead><tbody>
    <tr><td>Skaters: analysts</td><td>${ex.cons.rho}</td><td>${ex.cons.mae}</td></tr>
    <tr><td>Skaters: our model</td><td>${ex.model.rho}</td><td>${ex.model.mae}</td></tr>
    <tr><td>Skaters: blend used here</td><td class="hl">${ex.blend.rho}</td><td class="hl">${ex.blend.mae}</td></tr>
    <tr><td>Goalies: analysts</td><td>${ex.goalies.cons.rho}</td><td>${ex.goalies.cons.mae}</td></tr>
    <tr><td>Goalies: our model</td><td>${ex.goalies.model.rho}</td><td>${ex.goalies.model.mae}</td></tr>
    <tr><td>Goalies: blend used here</td><td class="hl">${ex.goalies.blend.rho}</td><td class="hl">${ex.goalies.blend.mae}</td></tr>
  </tbody></table></div>
  <p>So the analysts add something, but less than you'd think for this league: their rankings are built for category leagues. The pull is bigger where they know more than stats can:</p>
  <ul>
    <li><b>Young players, short track records and players on new teams:</b> 35% of the way toward the analysts.</li>
    <li><b>Most other skaters:</b> 20%.</li>
    <li><b>Centers:</b> 5%. Their faceoff points are invisible to category rankings, and in testing the analysts' view of centers added almost nothing.</li>
    <li><b>Goalies:</b> 65%. Analysts know depth charts and new starters, and for goalies they beat our stats (best mix was mostly analysts).</li>
    <li><b>Rookies:</b> 60%. There's little NHL data to go on.</li>
  </ul>
  <p>Each player's card shows our number, the analysts' number and the blend.</p>

  <h3>The 84-game season and injuries</h3>
  <p>The NHL plays 84 games this season, but Fantrax's last week ends ${esc(dLabel(SEASON_END, { month: "long", day: "numeric" }))}, so each team has 80 to 82 games that count here. Every projection uses the real schedule. Hurt players lose the games their team plays before their expected return, and a hurt goalie's starts go to his teammates. The list starts from camp news as of ${esc(META.newsAsOf)} and is updated several times a day from ESPN's NHL injury report (status, body part and expected return), so lineups, pickups, trades and the matchup adjust on their own when someone gets hurt or comes back. Camp news on each card (lines, power-play units, new teams) comes from beat writers and fantasy analysts, with the source named.</p>

  <h3>My team, trades and pickups</h3>
  <ul>
    <li><b>Night by night.</b> Every night, your best lineup is picked from the players who have a game, respecting ${CAP.C} C, ${CAP.W} W, ${CAP.D} D and ${CAP.G} G. On busy nights some good players sit; on quiet nights slots stay empty. That's why games played and roster balance matter as much as raw points.</li>
    <li><b>The matchup</b> is the same calculation for both teams over this week's schedule. Goalies are counted at their chance of starting, so it assumes you don't know the starter in advance.</li>
    <li><b>Pickups</b> test every good free agent in your real lineup against your easiest drops, over the rest of the season or just this week. "Easiest to drop" means the player whose removal costs your lineup the fewest points.</li>
    <li><b>Trades</b> are found by trying every one-for-one, two-for-one and one-for-two swap with each team, then replaying the rest of the season night by night for both rosters (a team that ends up a player short picks up its best free agent; a team with one too many drops its least useful player). A deal is shown only if it helps you and doesn't look lopsided to them. "Name value" is how the other manager will probably see it: the experts' view of each player, with stars worth more than two lesser players added together (value above waiver level to the power 1.5), because nobody trades a star for two fillers.</li>
    <li><b>Where you stand</b> ranks each position by the points your starters there are projected to score the rest of the season.</li>
    <li><b>Rosters update from Fantrax</b> every few minutes while the page is open, so pickups and drops anywhere in the league show up on their own.</li>
    <li><b>Injuries.</b> When one of your players gets hurt, he's left out of your lineups until his expected return and the to-do list tells you what to do (move him to IR, who to pick up). A player on IR opens a roster spot: pickups then need no drop until he's back, and the points shown count the drop you'll have to make when he returns. The site never changes anything in Fantrax; you make the moves there.</li>
  </ul>

  <h3>How accurate is it?</h3>
  <p>Every number below comes from projecting past seasons using only the seasons before them, then checking against what happened, in this league's scoring. Lower "miss" is better; for "ranking agreement," 1 would be perfect.</p>
  <div class="tablewrap"><table><thead><tr><th></th><th>This model</th><th>Step 1 only</th><th>Last season again</th></tr></thead><tbody>
    <tr><td>Skaters: points-per-game miss</td><td class="hl">${bt.skaters.model.ppg}</td><td>${bt.skaters.v1.ppg}</td><td>${bt.skaters.naive.ppg}</td></tr>
    <tr><td>Skaters: season-total miss, top 300</td><td class="hl">${bt.skaters.model.tot}</td><td>${bt.skaters.v1.tot}</td><td>${bt.skaters.naive.tot}</td></tr>
    <tr><td>Skaters: ranking agreement, top 300</td><td class="hl">${bt.skaters.model.rho}</td><td>${bt.skaters.v1.rho}</td><td>${bt.skaters.naive.rho}</td></tr>
    <tr><td>Goalies: points-per-game miss</td><td class="hl">${bt.goalies.model.ppg}</td><td>${bt.goalies.v1.ppg}</td><td>${bt.goalies.naive.ppg}</td></tr>
    <tr><td>Goalies: season-total miss, top 60</td><td class="hl">${bt.goalies.model.tot}</td><td>${bt.goalies.v1.tot}</td><td>${bt.goalies.naive.tot}</td></tr>
  </tbody></table></div>
  <p>Skaters were tested on ${bt.skaters.n_seasons} seasons (${esc(bt.seasons)}) and goalies on ${bt.goalies.n_seasons}. Hockey is noisy: a typical top-300 skater's season total is still off by about ${Math.round(bt.skaters.model.tot)} points, mostly from injuries and role changes nobody sees coming.</p>

  <h3>What it doesn't know</h3>
  <ul>
    <li>Nightly starting goalies and late scratches.</li>
    <li>Line and power-play changes after ${esc(META.newsAsOf)} until they show up in ice time, and NHL trades after that date.</li>
    <li>Exact return dates. The injury report's dates are estimates; a player still listed after his date is treated as out one more day at a time.</li>
    <li>Keeper value for next season. Young players are worth a little more to you than they show here.</li>
  </ul>
  </div>`;
}

function posValueRows() {
  return SLOTS.map((s) => {
    const xs = B.players.filter((p) => (s === "G" ? p.slot === "G" : p.slotpts && p.slotpts[s] != null) && p.pts).map((p) => (s === "G" ? p.pts : p.slotpts[s])).sort((a, b) => b - a);
    const v = (k) => (xs.length >= k ? sgn(xs[k - 1] - REPL[s]) : "–");
    return `<tr><td>${POSNAME[s]}</td><td>${v(1)}</td><td>${v(12)}</td><td>${v(24)}</td><td>${CAP[s]}</td></tr>`;
  }).join("");
}

/* ---------------- tabs, theme, toast ---------------- */
function setTab(t) {
  if (!TABS.includes(t)) t = "team";
  S.tab = t; LS.set("zb-tab", t);
  document.querySelectorAll("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === t));
  document.querySelectorAll("main > section").forEach((s) => (s.hidden = s.id !== "tab-" + t));
  renderTab();
  window.scrollTo({ top: 0 });
}
function renderTab() {
  if (S.tab === "team") renderTeam();
  else if (S.tab === "trades") renderTrades();
  else if (S.tab === "adds") renderAdds();
  else if (S.tab === "board") renderBoard();
  else if (S.tab === "league") renderLeague();
  else if (S.tab === "how") renderHow();
}
function renderAll() { renderStrip(); renderTab(); }
let toastTimer = null;
function toast(msg) {
  const t = $("#toast");
  $("#toastMsg").textContent = msg; $("#toastBtn").hidden = true;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 5000);
}
function initTheme() {
  const saved = LS.get("zb-theme", null);
  if (saved) document.documentElement.dataset.theme = saved;
  $("#themeBtn").onclick = () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const nx = cur === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = nx; LS.set("zb-theme", nx);
  };
}

/* ---------------- live rosters ---------------- */
async function fx(ep, qs) {
  const r = await fetch(`${FX}${ep}?${qs || "leagueId=" + META.leagueId}`, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
let syncing = false;
async function sync() {
  if (syncing) return;
  syncing = true;
  try {
    const rr = await fx("getTeamRosters");
    if (!rr || !rr.rosters) throw new Error("no rosters");
    const own = {}, status = {};
    for (const [tid, t] of Object.entries(rr.rosters)) for (const it of t.rosterItems || []) { own[it.id] = tid; status[it.id] = it.status; }
    if (JSON.stringify(status) !== JSON.stringify(S.live.status || {})) clearCaches();
    S.live.owners = own; S.live.status = status;
    S.live.at = Date.now(); S.live.err = null; S.live.fails = 0;
    if (Object.keys(own).some((id) => !PL.has(id)) && !EXTRA) loadExtra();
  } catch (e) {
    S.live.err = String(e.message || e); S.live.fails++;
  } finally {
    syncing = false;
  }
  afterSync();
}
async function loadLive() {
  liveAt = Date.now();
  for (const url of [META.live.raw + "?t=" + Math.floor(Date.now() / 300000), META.live.local + "?t=" + Math.floor(Date.now() / 300000)]) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) continue;
      const d = await r.json();
      if (!d || !d.players) continue;
      if (!LIVE || d.generated !== LIVE.generated) { LIVE = d; applyInjuries(); clearCaches(); S.lastSig = ""; afterSync(); }
      return;
    } catch (e) { /* try the next copy */ }
  }
}
setInterval(loadLive, 30 * 60 * 1000);
let liveAt = 0;
document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() - liveAt > 10 * 60 * 1000) loadLive(); });
async function loadExtra() {
  try { EXTRA = await fx("getPlayerIds", "sport=NHL"); S.lastSig = ""; afterSync(); } catch (e) { /* names only */ }
}
function afterSync() {
  renderStrip();
  const sig = [JSON.stringify(S.live.owners), JSON.stringify(S.live.status), S.team, !!EXTRA, todayET(), LIVE ? LIVE.generated : ""].join("|");
  if (sig !== S.lastSig) {
    const first = !S.lastSig;
    S.lastSig = sig;
    const ae = document.activeElement;
    if (!(ae && ae.id === "q") || first) renderTab(); else renderBoardList();
  }
  schedule();
}
let timer = null;
function schedule() {
  clearTimeout(timer);
  if (document.hidden) return;
  let ms = 3 * 60 * 1000;
  if (S.live.fails) ms = Math.min(5 * 60 * 1000, 15000 * 2 ** Math.min(S.live.fails, 4));
  timer = setTimeout(sync, ms);
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) sync(); else clearTimeout(timer); });
setInterval(renderStrip, 30000);

let resetArmed = 0;
function confirmReset() {
  if (Date.now() - resetArmed < 4000) { resetArmed = 0; return true; }
  resetArmed = Date.now(); toast("Tap again to clear your stars and goalie starts"); return false;
}

/* ---------------- boot ---------------- */
function init() {
  initTheme();
  const sel = $("#teamSel");
  sel.innerHTML = META.teams.slice().sort((a, b) => a.name.localeCompare(b.name)).map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
  sel.value = S.team;
  sel.onchange = () => { S.team = sel.value; LS.set("zb-team", S.team); S.lastSig = ""; S.addOpen = null; clearCaches(); renderAll(); };
  document.querySelectorAll("nav.tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  $("#subline").textContent = `${META.season} · projections ${new Date(META.built).toLocaleDateString([], { month: "short", day: "numeric" })} · news ${dLabel(META.newsAsOf, { month: "short", day: "numeric" })}`;
  $("#foot").innerHTML = `Stats and schedule from the NHL. League and rosters from Fantrax (read-only). Injury statuses from ESPN's NHL injury report. Analyst rankings from ${META.experts.n} public sources, blended; no lists are reproduced here. Not affiliated with the NHL or Fantrax. <button class="btn" id="resetBtn" style="margin-left:6px;padding:4px 10px;font-size:12.5px">Clear my stars and goalie starts</button>`;
  $("#resetBtn").onclick = () => {
    if (!confirmReset()) return;
    S.stars = {}; S.gsOv = {}; LS.set("zb-stars", {}); LS.set("zb-gs", {});
    clearCaches(); S.lastSig = ""; renderAll(); toast("Cleared stars and goalie starts");
  };
  boardShell();
  const hash = location.hash.replace("#", "");
  if (TABS.includes(hash)) S.tab = hash;
  setTab(S.tab);
  renderStrip();
  sync();
  loadLive();
}
init();
})();
