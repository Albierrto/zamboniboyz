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
const TABS = ["team", "adds", "board", "league", "how"];
const S = {
  team: startTeam(),
  tab: TABS.includes(LS.get("zb-tab", "team")) ? LS.get("zb-tab", "team") : "team",
  pos: "ALL", q: "", faOnly: LS.get("zb-fa", false), sort: "ros", show: 60, open: null,
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
// points per team game at a slot (0 before he's back from injury)
function rateAt(p, s) { const x = ptsAt(p, s); return p.gm > 0 && x != null ? x / p.gm : 0; }
function bestRate(p) { return Math.max(0, ...elig(p).map((s) => rateAt(p, s))); }
function plays(p, day) { return !!p.t && day.teams.has(p.t) && (!p.ret || day.d >= p.ret); }
const GL = new Map();
function gamesLeft(p, from) {
  const k = p.t + "|" + (p.ret || "") + "|" + from;
  if (!GL.has(k)) GL.set(k, DAYS.reduce((a, x) => a + (x.d >= from && plays(p, x) ? 1 : 0), 0));
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
function nightLineup(list, want) {
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
    arr.map((p) => [p, rateAt(p, s)]).sort((a, b) => b[1] - a[1]).slice(0, n).forEach(([p, r]) => { total += r; if (start) start.set(p.id, s); });
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
    if (on.length) v += nightLineup(on).total;
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
function pickups(team, mode) {
  return memo("adds|" + mode + "|" + rosterKey(team) + "|" + fromDay() + "|" + JSON.stringify(S.gsOv), () => {
    const roster = rosterOf(team);
    const rosDays = windowDays("ros");
    const days = windowDays(mode);
    const baseRos = rangeValue(roster, rosDays);
    // drop candidates are always the players who add the least over the rest of the season,
    // so a one-week stream never costs you a regular
    const contrib = roster.map((p) => ({ p, c: baseRos - rangeValue(roster.filter((x) => x !== p), rosDays) })).sort((a, b) => a.c - b.c);
    const drops = contrib.slice(0, 4);
    const base = mode === "ros" ? baseRos : rangeValue(roster, days);
    const fa = freeAgents().map((p) => ({ p, e: bestRate(p) * gamesIn(p, days) })).filter((x) => x.e > 0);
    const pool = [];
    for (const s of ["C", "W", "D", "G"]) pool.push(...fa.filter((x) => elig(x.p)[0] === s).sort((a, b) => b.e - a.e).slice(0, s === "G" ? 20 : 40));
    const out = [];
    for (const { p } of pool) {
      let best = null;
      for (const d of drops) {
        const g = rangeValue(roster.filter((x) => x !== d.p).concat([p]), days) - base;
        if (!best || g > best.g) best = { g, drop: d.p, dc: d.c };
      }
      const item = { p, gain: best.g, drop: best.drop, dropC: best.dc, games: gamesIn(p, days) };
      out.push(item);
    }
    out.sort((a, b) => b.gain - a.gain);
    if (mode === "week") {  // what the swap does to the rest of your season
      for (const x of out.slice(0, 40)) x.rosDelta = rangeValue(roster.filter((y) => y !== x.drop).concat([x.p]), rosDays) - baseRos;
    }
    return { list: out, base, contrib, days };
  });
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
  else if (L.at) { cls += " ok"; txt = `Rosters live · ${agoText(L.at)}`; }
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
  const season = META.teams.map((t) => ({ id: t.id, v: memo("ros|" + rosterKey(t.id) + "|" + from + JSON.stringify(S.gsOv), () => rangeValue(rosterOf(t.id), daysIn(from, SEASON_END))) })).sort((a, b) => b.v - a.v);
  const rank = season.findIndex((x) => x.id === S.team) + 1;
  const mine = season.find((x) => x.id === S.team);
  const lu = fillLineup(roster);
  const adds = pickups(S.team, "ros").list.filter((x) => x.gain >= 3);
  const games = roster.reduce((a, p) => a + gamesIn(p, wk), 0), oppGames = opp ? rosterOf(opp).reduce((a, p) => a + gamesIn(p, wk), 0) : 0;

  // alerts
  const alerts = [];
  const inj = roster.filter(hurt);
  if (inj.length) alerts.push(`<b>Hurt:</b> ${inj.map((p) => `${esc(p.n)} (back ~${esc(dLabel(p.ret, { month: "short", day: "numeric" }))})`).join(", ")}. If Fantrax lists him as injured, an IR spot frees a roster spot for a pickup.`);
  const idle = roster.filter((p) => !hurt(p) && gamesIn(p, wk) === 0);
  if (idle.length && wk.length) alerts.push(`<b>No games ${started ? "left " : ""}this week:</b> ${idle.map((p) => esc(p.n)).join(", ")}.`);
  if (adds.length) {
    const d = adds[0].drop;
    alerts.push(`<b>Best pickup:</b> ${esc(adds[0].p.n)} for ${esc(d.n)}, about ${sgn(adds[0].gain)} points over the rest of the season.${analystsBacked(d) ? ` Analysts rank ${esc(d.n)} far higher than our stats do (${ordinal(d.mr)} ${esc(d.slot)} vs our ${ordinal(d.orank)}), so see what he gets you in a trade before dropping him.` : ""} <button class="linkbtn" data-tab="adds">See pickups</button>`);
  }

  // day by day for this week
  const dayRows = wk.map((day) => {
    const on = roster.filter((p) => plays(p, day));
    const nl = nightLineup(on, true);
    const sit = on.filter((p) => !nl.start.has(p.id));
    const cnt = { C: 0, W: 0, D: 0, G: 0 };
    for (const s of nl.start.values()) cnt[s]++;
    const empty = ["C", "W", "D", "G"].filter((s) => cnt[s] < CAP[s]).map((s) => `${CAP[s] - cnt[s]} ${s}`);
    return `<div class="day ${day.d === todayET() ? "today" : ""}"><div class="dd"><b>${esc(dLabel(day.d, { weekday: "short" }))}</b><span>${esc(dLabel(day.d, { month: "short", day: "numeric" }))}</span></div>
      <div class="di"><div><b>${on.length}</b> playing · <span class="num">${fmt(nl.total, 1)}</span> pts</div>
      ${sit.length ? `<div class="sit">Sits: ${sit.map((p) => esc(p.n)).join(", ")}</div>` : ""}
      ${empty.length && on.length ? `<div class="gap">Empty: ${empty.join(", ")}</div>` : ""}${!on.length ? `<div class="gap">Nobody plays</div>` : ""}</div></div>`;
  }).join("");

  const slotRow = (x, s) => rowMini(x.p, rosAt(x.p, s), s);
  const grp = (s, label) => `<div class="slotgrp"><h3>${label}<small>${lu.slots[s].length} of ${CAP[s]}</small></h3>${lu.slots[s].map((x) => slotRow(x, s)).join("")}${Array.from({ length: Math.max(0, lu.needs[s]) }, () => `<div class="slot open"><div class="open-ic"></div><div class="nm">Open spot<small>check Pickups</small></div><b></b></div>`).join("")}</div>`;
  el.innerHTML = `
    <div class="lede"><h2>${esc(tname(S.team))}</h2><p>${esc(started || todayET() >= SEASON_START ? "Rest-of-season projections, this week's games and who to pick up." : "Your roster going into the season: who starts, this week's games and who to pick up.")}</p></div>
    ${opp ? `<div class="matchup">
      <div class="mh"><span>${isPlayoffs(per.n) ? "Playoffs · " : ""}Week ${per.n} · ${esc(dLabel(per.s, { month: "short", day: "numeric" }))} to ${esc(dLabel(lastDayOf(per), { month: "short", day: "numeric" }))}</span><span>${started ? "rest of week" : "projected"}</span></div>
      <div class="side me"><div class="tn">${esc(tname(S.team))}<small>${games} games</small></div><b class="num">${fmt(myWk)}</b><div class="mbar"><i style="width:${(100 * myWk) / Math.max(myWk, oppWk, 1)}%"></i></div></div>
      <div class="side"><div class="tn">${esc(tname(opp))}<small>${oppGames} games</small></div><b class="num">${fmt(oppWk)}</b><div class="mbar"><i style="width:${(100 * oppWk) / Math.max(myWk, oppWk, 1)}%"></i></div></div>
      <div class="mf">${myWk >= oppWk ? `You're projected to win by about <b>${fmt(myWk - oppWk)}</b>.` : `You're projected to lose by about <b>${fmt(oppWk - myWk)}</b>. A pickup with extra games this week can close it.`} Assumes you set your best lineup every day.</div>
    </div>` : ""}
    <div class="hero">
      <div class="stat"><div class="k">Rest of season</div><div class="v">${fmt(mine.v)}</div><div class="s">Rank ${rank} of 12 in the league</div></div>
      <div class="stat"><div class="k">Roster</div><div class="v">${roster.length}<span style="font-size:16px;color:var(--ink3)"> / ${META.roster.max}</span></div><div class="s">${inj.length ? `${inj.length} hurt` : "Everyone healthy"}</div></div>
      <div class="stat"><div class="k">Games this week</div><div class="v">${games}</div><div class="s">${opp ? `${esc(tshort(opp))} has ${oppGames}` : "&nbsp;"}</div></div>
    </div>
    ${alerts.length ? `<div class="alerts">${alerts.map((a) => `<div class="banner soft">${a}</div>`).join("")}</div>` : ""}
    <h3 class="sectitle">This week, night by night</h3>
    <div class="days">${dayRows || '<div class="empty">No games left this week.</div>'}</div>
    <h3 class="sectitle">Your regular lineup</h3>
    <p class="note" style="margin:-2px 0 10px">Points are for the rest of the season. Tap a player for the full story.</p>
    <div class="rink">
      ${grp("C", "Centers")}${grp("W", "Wingers")}${grp("D", "Defense")}${grp("G", "Goalies")}
      <div class="slotgrp"><h3>Bench<small>${lu.bench.length} of ${BENCH}</small></h3>${lu.bench.map((p) => rowMini(p, rosOf(p))).join("")}</div>
    </div>`;
  el.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  el.querySelectorAll("[data-open]").forEach((b) => (b.onclick = () => openPlayer(b.dataset.open)));
}
function rowMini(p, pts, s) {
  const flags = [];
  if (hurt(p)) flags.push(`<span class="pill bad">Hurt</span>`);
  return `<button class="slot" data-open="${esc(p.id)}">${face(p)}<div class="nm">${esc(p.n)}<small>${s && s !== p.slot ? `as ${s} · ` : ""}${esc(p.t)}</small> ${flags.join(" ")}</div><b class="num">${fmt(pts)}</b></button>`;
}
function openPlayer(id) {
  S.open = id; S.q = player(id).n; S.pos = "ALL"; S.faOnly = false;
  setTab("board");
  const c = document.querySelector(`.card[data-id="${CSS.escape(id)}"]`);
  if (c) c.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------------- pickups tab ---------------- */
function renderAdds() {
  const el = $("#tab-adds");
  const mode = S.addMode;
  const res = pickups(S.team, mode);
  const per = periodOf(fromDay());
  let rows = res.list;
  if (S.addPos !== "ALL") rows = rows.filter((x) => elig(x.p).includes(S.addPos));
  const good = rows.filter((x) => x.gain >= 1);
  const chips = [["ALL", "All"], ["C", "C"], ["W", "W"], ["D", "D"], ["G", "G"]];
  const drops = res.contrib.slice(0, 4);
  el.innerHTML = `
    <div class="lede"><h2>Pickups</h2><p>Free agents who'd make <b>${esc(tname(S.team))}</b> better, and who to drop for them. Each one is tested in your real lineup, night by night, so games played and position crowding count. The league allows 3 claims a week ($2 a claim, $1 a drop).</p></div>
    <div class="controls">
      <div class="chips" role="group" aria-label="Time frame"><button data-mode="ros" aria-pressed="${mode === "ros"}">Rest of season</button><button data-mode="week" aria-pressed="${mode === "week"}">This week${per ? ` (wk ${per.n})` : ""}</button></div>
      <div class="chips" role="group" aria-label="Position">${chips.map(([k, l]) => `<button data-apos="${k}" aria-pressed="${S.addPos === k}">${l}</button>`).join("")}</div>
    </div>
    <div class="banner soft"><b>Easiest to drop right now:</b> ${drops.map((d) => `${esc(d.p.n)} (adds ${fmt(d.c)})`).join(", ")}. That's how many points each adds to your lineup over the rest of the season once your other players are counted, so these are the only players suggested as drops.</div>
    <div class="list" id="addList">${good.slice(0, S.addShow).map((x, i) => addCard(x, i + 1, mode)).join("") || `<div class="empty">No free agent beats your current roster ${mode === "week" ? "this week" : "right now"}. Check back as news comes in.</div>`}</div>
    <button class="more" id="addMore" ${good.length > S.addShow ? "" : "hidden"}>Show more</button>`;
  el.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => { S.addMode = b.dataset.mode; LS.set("zb-addmode", S.addMode); S.addShow = 25; renderAdds(); }));
  el.querySelectorAll("[data-apos]").forEach((b) => (b.onclick = () => { S.addPos = b.dataset.apos; S.addShow = 25; renderAdds(); }));
  $("#addMore").onclick = () => { S.addShow += 25; renderAdds(); };
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
  tags.push(`<span class="tag">Drop <b>${esc(x.drop.n)}</b></span>`);
  if (analystsBacked(x.drop)) tags.push(`<span class="pill gold" title="Analysts rank him much higher than our stats do">Analysts like ${esc(x.drop.n.split(" ").slice(-1)[0])}: try a trade first</span>`);
  tags.push(`<span class="tag">${x.games} game${x.games === 1 ? "" : "s"} ${mode === "week" ? "this week" : "left"}</span>`);
  if (x.rosDelta != null) tags.push(`<span class="tag ${x.rosDelta >= 0 ? "good" : "bad"}" title="What this swap does to your team over the whole rest of the season">Rest of season <b>${sgn(x.rosDelta)}</b></span>`);
  if (hurt(p)) tags.push(`<span class="pill bad">Hurt until ${esc(dLabel(p.ret, { month: "short", day: "numeric" }))}</span>`);
  if (p.rk) tags.push(`<span class="pill gold">Rookie</span>`);
  if (p.mr && p.orank && p.mr + 8 <= p.orank) tags.push(`<span class="pill good" title="Analysts rank him higher than our stats do">Analysts like him</span>`);
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
  if (hurt(p)) tags.push(`<span class="pill bad">Hurt until ${esc(dLabel(p.ret, { month: "short", day: "numeric" }))}</span>`);
  if (p.rk) tags.push(`<span class="pill gold">Rookie</span>`);
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
  if (acts.length) parts.push(`<div class="acts">${acts.join("")}</div>`);
  return `<div class="detail">${parts.join("")}</div>`;
}
function toggleStar(id) { if (S.stars[id]) delete S.stars[id]; else S.stars[id] = 1; LS.set("zb-stars", S.stars); }
function onListClick(e) {
  const tg = e.target.closest("[data-toggle],[data-star],[data-gs],[data-gsreset]");
  if (!tg) return;
  const d = tg.dataset;
  if (d.toggle) { S.open = S.open === d.toggle ? null : d.toggle; renderBoardList(); return; }
  if (d.star) { toggleStar(d.star); renderBoardList(); return; }
  if (d.gs) {
    const p = PL.get(d.gs); const cur = gsOf(p);
    S.gsOv[d.gs] = Math.max(0, Math.min(84, Math.round((cur + Number(d.d)) / 5) * 5)); LS.set("zb-gs", S.gsOv); MEMO.clear(); renderBoardList(); return;
  }
  if (d.gsreset) { delete S.gsOv[d.gsreset]; LS.set("zb-gs", S.gsOv); MEMO.clear(); renderBoardList(); }
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
  <div class="lede"><h2>How it works</h2><p>Plain-English notes on where the numbers come from and how much to trust them.</p></div>
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
  <p>The NHL plays 84 games this season, but Fantrax's last week ends ${esc(dLabel(SEASON_END, { month: "long", day: "numeric" }))}, so each team has 80 to 82 games that count here. Every projection uses the real schedule. Players known to be hurt as of ${esc(META.newsAsOf)} lose the games their team plays before their expected return, and a hurt goalie's starts go to his teammates. Camp news on each card (lines, power-play units, new teams) comes from beat writers and fantasy analysts, with the source named.</p>

  <h3>My team and pickups</h3>
  <ul>
    <li><b>Night by night.</b> Every night, your best lineup is picked from the players who have a game, respecting ${CAP.C} C, ${CAP.W} W, ${CAP.D} D and ${CAP.G} G. On busy nights some good players sit; on quiet nights slots stay empty. That's why games played and roster balance matter as much as raw points.</li>
    <li><b>The matchup</b> is the same calculation for both teams over this week's schedule. Goalies are counted at their chance of starting, so it assumes you don't know the starter in advance.</li>
    <li><b>Pickups</b> test every good free agent in your real lineup against your easiest drops, over the rest of the season or just this week. "Easiest to drop" means the player whose removal costs your lineup the fewest points.</li>
    <li><b>Rosters update from Fantrax</b> every few minutes while the page is open, so pickups and drops anywhere in the league show up on their own.</li>
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
    <li>Games already played. Projections were built ${esc(META.built.slice(0, 10))} and don't yet learn from this season's stats; rosters are live, the numbers aren't.</li>
    <li>Nightly starting goalies and late scratches.</li>
    <li>Injuries and trades after ${esc(META.newsAsOf)}.</li>
    <li>Keeper value for next season. Young players are worth a little more to you than they show here.</li>
  </ul>
  </div>`;
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
async function loadExtra() {
  try { EXTRA = await fx("getPlayerIds", "sport=NHL"); S.lastSig = ""; afterSync(); } catch (e) { /* names only */ }
}
function afterSync() {
  renderStrip();
  const sig = [JSON.stringify(S.live.owners), S.team, !!EXTRA, todayET()].join("|");
  if (sig !== S.lastSig) {
    const first = !S.lastSig;
    S.lastSig = sig;
    MEMO.clear();
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
  sel.onchange = () => { S.team = sel.value; LS.set("zb-team", S.team); S.lastSig = ""; S.addOpen = null; MEMO.clear(); renderAll(); };
  document.querySelectorAll("nav.tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  $("#subline").textContent = `${META.season} · projections ${new Date(META.built).toLocaleDateString([], { month: "short", day: "numeric" })} · news ${dLabel(META.newsAsOf, { month: "short", day: "numeric" })}`;
  $("#foot").innerHTML = `Stats and schedule from the NHL. League and rosters from Fantrax (read-only). Analyst rankings from ${META.experts.n} public sources, blended; no lists are reproduced here. Not affiliated with the NHL or Fantrax. <button class="btn" id="resetBtn" style="margin-left:6px;padding:4px 10px;font-size:12.5px">Clear my stars and goalie starts</button>`;
  $("#resetBtn").onclick = () => {
    if (!confirmReset()) return;
    S.stars = {}; S.gsOv = {}; LS.set("zb-stars", {}); LS.set("zb-gs", {});
    MEMO.clear(); S.lastSig = ""; renderAll(); toast("Cleared stars and goalie starts");
  };
  boardShell();
  const hash = location.hash.replace("#", "");
  if (TABS.includes(hash)) S.tab = hash;
  setTab(S.tab);
  renderStrip();
  sync();
}
init();
})();
