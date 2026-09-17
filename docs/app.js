/* ZamboniBoyz Draft Room. Read-only: this page only reads Fantrax's public league API. */
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
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fold = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const fmt = (x, d = 0) => (x == null || isNaN(x) ? "–" : Number(x).toFixed(d));
const sgn = (x) => (x == null ? "–" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(Math.round(x)));
const pct = (x) => Math.min(99, Math.max(1, Math.round(100 * x))) + "%";

const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

const TEAMS = {}; META.teams.forEach((t) => (TEAMS[t.id] = t));
const tname = (id) => (TEAMS[id] ? TEAMS[id].name : "Unknown team");
const PL = new Map(); B.players.forEach((p) => PL.set(p.id, p));
let EXTRA = null; // lazily loaded Fantrax name list for players not on the board

const S = {
  team: TEAMS[LS.get("zb-team", "")] ? LS.get("zb-team") : META.defaultTeam,
  tab: LS.get("zb-tab", "board"),
  pos: "ALL", q: "", hideTaken: LS.get("zb-hide", true), sort: "val", show: 60, open: null,
  stars: LS.get("zb-stars", {}),
  manual: LS.get("zb-manual", {}), // fantrax id -> overall pick number
  gsOv: LS.get("zb-gs", {}),       // goalie id -> starts
  leagueOpen: {},
  live: { picks: null, owners: null, at: null, err: null, rosAt: 0, fails: 0 },
  lastSig: "", wasOnClock: false, seenPicks: null,
};

/* ---------------- dates ---------------- */
function parseFx(s) {
  if (!s) return null;
  const m = String(s).match(/^(.*T\d\d:\d\d:\d\d)(?:\.\d+)?([+-]\d\d)(\d\d)$/);
  return new Date(m ? `${m[1]}${m[2]}:${m[3]}` : s);
}
const DRAFT_AT = parseFx(META.draftDate);
function whenText(d) {
  return d.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
function untilText(ms) {
  const m = Math.max(0, Math.round(ms / 60000));
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${mm}m`;
  return `${mm}m`;
}
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
  const stub = { id, n: nm, t: x && x.team && x.team !== "(N/A)" ? x.team : "", pos, slot: pos, pts: null, val: null, tier: 6, ch: [], slotpts: {}, unknown: true };
  return stub;
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
function valOf(p) {
  if (p.val == null) return null;
  if (p.slot === "G") return ptsOf(p) - REPL.G;
  return p.val;
}
function valAt(p, s) {
  if (s === "ALL" || !s) return valOf(p);
  const x = ptsAt(p, s);
  return x == null ? null : x - REPL[s];
}
function tierOf(v) { return v == null ? 6 : v >= 120 ? 1 : v >= 80 ? 2 : v >= 50 ? 3 : v >= 20 ? 4 : v >= 0 ? 5 : 6; }
function face(p, cls = "face") {
  const ini = esc((p.n || "?").split(" ").map((w) => w[0]).slice(0, 2).join(""));
  if (!p.pid) return `<div class="${cls} ph" aria-hidden="true">${ini}</div>`;
  return `<img class="${cls}" loading="lazy" alt="" src="https://assets.nhle.com/mugs/nhl/latest/${p.pid}.png" onerror="this.outerHTML='<div class=&quot;${cls} ph&quot;>${ini}</div>'">`;
}
function posBadge(p) { return `<span class="pos">${esc((p.pos || p.slot).replace(/,/g, "/"))}</span>`; }

/* ---------------- draft state ---------------- */
function basePicks() {
  const src = S.live.picks || META.picks.map((a) => ({ r: a[0], n: a[1], team: a[2], pid: a[3] || null }));
  return src.map((p) => ({ ...p })).sort((a, b) => a.n - b.n);
}
function getPicks() {
  const picks = basePicks();
  const liveIds = new Set(picks.filter((p) => p.pid).map((p) => p.pid));
  const byPick = {};
  for (const [fid, n] of Object.entries(S.manual)) {
    if (liveIds.has(fid)) continue; // Fantrax has it now
    byPick[n] = fid;
  }
  for (const p of picks) {
    if (!p.pid && byPick[p.n]) { p.pid = byPick[p.n]; p.manual = true; }
  }
  return picks;
}
function ownersMap(picks) {
  const own = {};
  if (S.live.owners) Object.assign(own, S.live.owners);
  else B.players.forEach((p) => { if (p.own) own[p.id] = p.own; });
  const info = {};
  for (const [fid, t] of Object.entries(own)) info[fid] = { team: t, kept: true };
  for (const p of picks) if (p.pid) info[p.pid] = { team: p.team, pick: p.n, round: p.r, manual: !!p.manual, kept: false };
  // players marked by hand after the pick list ran out (or taken outside the draft)
  for (const [fid, n] of Object.entries(S.manual)) if (!info[fid]) info[fid] = { team: null, pick: n, manual: true };
  return info;
}
function draftState() {
  const picks = getPicks();
  const taken = ownersMap(picks);
  const cur = picks.find((p) => !p.pid) || null;
  const made = picks.filter((p) => p.pid).length;
  const next = cur ? picks.find((p) => !p.pid && p.team === S.team) : null;
  const onClock = !!(cur && next && cur.n === next.n);
  // horizon: the pick we are deciding "will he last until"
  const horizon = onClock ? picks.find((p) => !p.pid && p.team === S.team && p.n > cur.n) : next;
  const before = horizon ? picks.filter((p) => !p.pid && p.n < horizon.n).length : 0;
  const nextBefore = next ? picks.filter((p) => !p.pid && p.n < next.n).length : 0;
  // for "take him now or wait?": the pick after the one you're deciding on
  const after = next ? picks.find((p) => !p.pid && p.team === S.team && p.n > next.n) : null;
  const afterBefore = after ? picks.filter((p) => !p.pid && p.n < after.n).length : 0;
  return { picks, taken, cur, made, next, onClock, horizon, before, nextBefore, after, afterBefore, total: picks.length, done: !cur };
}
function available(st) { return B.players.filter((p) => !st.taken[p.id]); }

function Phi(z) { // standard normal cdf
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989423 * Math.exp((-z * z) / 2);
  const q = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return z > 0 ? 1 - q : q;
}
function lastOdds(avail, before) {
  const m = new Map();
  const sorted = avail.slice().sort((a, b) => (a.adp ?? 900 - (valOf(a) ?? -99) / 100) - (b.adp ?? 900 - (valOf(b) ?? -99) / 100));
  sorted.forEach((p, i) => {
    const r = i + 1, sd = 2 + 0.3 * r;
    m.set(p.id, 1 - Phi((before + 0.5 - r) / sd));
  });
  return m;
}

/* ---------------- rosters ---------------- */
function rosterOf(team, st) {
  const out = [];
  for (const [fid, t] of Object.entries(st.taken)) if (t.team === team) out.push(player(fid));
  return out;
}
function fillLineup(list) {
  const slots = { C: [], W: [], D: [], G: [] }, bench = [];
  const sorted = list.slice().sort((a, b) => (ptsOf(b) ?? 0) - (ptsOf(a) ?? 0));
  for (const p of sorted) {
    const opts = elig(p).slice().sort((a, b) => (ptsAt(p, b) - REPL[b]) - (ptsAt(p, a) - REPL[a]));
    const s = opts.find((s) => slots[s] && slots[s].length < CAP[s]);
    if (s) slots[s].push({ p, s }); else bench.push(p);
  }
  // repair: open slot that a starter elsewhere could take, freeing his slot for a bench player
  for (const open of ["C", "W", "D"]) {
    if (slots[open].length >= CAP[open]) continue;
    for (const other of ["C", "W", "D"]) {
      if (other === open) continue;
      const mover = slots[other].find((x) => elig(x.p).includes(open));
      const filler = bench.find((b) => elig(b).includes(other));
      if (mover && filler && slots[open].length < CAP[open]) {
        slots[other].splice(slots[other].indexOf(mover), 1);
        slots[open].push({ p: mover.p, s: open });
        bench.splice(bench.indexOf(filler), 1);
        slots[other].push({ p: filler, s: other });
      }
    }
  }
  const needs = {};
  for (const s of ["C", "W", "D", "G"]) needs[s] = CAP[s] - slots[s].length;
  let strength = 0;
  for (const s of ["C", "W", "D", "G"]) for (const x of slots[s]) strength += ptsAt(x.p, x.s) || 0;
  const benchPts = bench.slice(0, BENCH).reduce((a, p) => a + (ptsOf(p) || 0), 0);
  return { slots, bench, needs, strength: strength + 0.25 * benchPts, starters: strength };
}

/* ---------------- suggestions ---------------- */
function suggestions(st, avail, lu) {
  // can he be had at the pick being decided, and will he last to the pick after it?
  const oddsNow = lastOdds(avail, st.onClock ? 0 : st.nextBefore);
  const oddsAfter = st.after ? lastOdds(avail, st.afterBefore) : null;
  const pool = avail.filter((p) => valOf(p) != null && !p.nt);
  const bestVal = Math.max(...pool.map((p) => valOf(p)));
  const open = Object.values(lu.needs).reduce((a, b) => a + b, 0);
  const scored = pool.map((p) => {
    const fillS = elig(p).filter((s) => lu.needs[s] > 0).sort((a, b) => valAt(p, b) - valAt(p, a))[0];
    const v = fillS ? valAt(p, fillS) : valOf(p);
    const now = oddsNow.get(p.id) ?? 1;
    const later = oddsAfter ? oddsAfter.get(p.id) ?? 1 : 0;
    let score = v;
    if (open > 0 && !fillS) score -= 40;
    // a player who will very likely still be there next time is worth less to take now
    score *= 1 - 0.6 * later;
    // and a player who probably won't make it to your pick is less useful to plan around
    score *= 0.5 + 0.5 * now;
    return { p, score, v, fillS, now, later };
  }).sort((a, b) => b.score - a.score);
  return scored.slice(0, 3).map((x, i) => {
    const why = [];
    if (Math.round(valOf(x.p)) >= Math.round(bestVal)) why.push({ t: "Most value left on the board" });
    if (x.fillS) why.push({ t: `Fills an open ${POSNAME[x.fillS].toLowerCase()} spot (you need ${lu.needs[x.fillS]} more)` });
    else if (open > 0) why.push({ t: "Bench depth: your starting spots at his position are full", w: 1 });
    if (!st.onClock && st.next && x.now < 0.6) why.push({ t: `Only ${pct(x.now)} chance he makes it to #${st.next.n}`, w: 1 });
    if (st.after) {
      if (x.later < 0.35) why.push({ t: `Won't last: ${pct(1 - x.later)} chance he's gone by #${st.after.n}`, w: 1 });
      else if (x.later > 0.8) why.push({ t: `Could wait: likely still there at #${st.after.n} (${pct(x.later)})` });
    }
    if (!why.length) why.push({ t: `${TIER[tierOf(valOf(x.p))]} value at ${POSNAME[x.p.slot].toLowerCase()}` });
    return { ...x, why, label: i === 0 ? (st.onClock ? "Take him" : "Top target") : i === 1 ? "Next best" : "Also good" };
  });
}

/* ---------------- clock strip ---------------- */
function renderClock(st) {
  const el = $("#clock"), wrap = $("#clockWrap");
  const now = Date.now();
  let main = "", mine = "";
  if (st.done) {
    main = `<span class="big">Draft complete</span><span class="small">${st.made} of ${st.total} picks made</span>`;
  } else if (st.made === 0 && DRAFT_AT && now < DRAFT_AT.getTime()) {
    main = `<span class="big">Draft in ${untilText(DRAFT_AT - now)}</span><span class="small">${esc(whenText(DRAFT_AT))}</span>`;
  } else if (st.made === 0) {
    main = `<span class="big">Draft time</span><span class="small">Waiting for the first pick. ${esc(tname(st.cur.team))} is up.</span>`;
  } else {
    main = `<span class="big">Pick ${st.cur.n} · Round ${st.cur.r}</span><span class="small">On the clock: <b>${esc(tname(st.cur.team))}</b></span>`;
  }
  if (st.onClock) mine = `<span class="yourpick"><b>You're on the clock</b></span>`;
  else if (st.next) mine = `<span class="yourpick">Your next pick: <b>#${st.next.n}</b>${st.made ? ` · ${st.nextBefore} to go` : ` (round ${st.next.r})`}</span>`;
  else if (!st.done) mine = `<span class="yourpick">No picks left</span>`;
  const L = S.live;
  let cls = "live", txt;
  if (L.err && !L.at) { cls += " err"; txt = "Can't reach Fantrax"; }
  else if (L.err) { cls += " err"; txt = `Fantrax slow · last ${agoText(L.at)}`; }
  else if (L.at) { cls += " ok"; txt = `Live · ${agoText(L.at)}`; }
  else { cls += " busy"; txt = "Connecting…"; }
  el.innerHTML = `<div class="main">${main}</div><div class="mine">${mine}<button class="${cls}" id="liveBtn" title="Check Fantrax now">${txt}</button></div>`;
  wrap.className = st.onClock ? "onclock" : "";
  $("#liveBtn").onclick = () => sync(true);
  document.title = st.onClock ? "● YOU'RE UP · ZamboniBoyz Draft Room" : "ZamboniBoyz Draft Room";
  const tb = document.querySelector('nav.tabs button[data-tab="board"]');
  tb.innerHTML = "Draft board" + (st.onClock ? '<span class="dot">!</span>' : "");
}

/* ---------------- board tab ---------------- */
function boardShell() {
  const el = $("#tab-board");
  el.innerHTML = `
    <div id="boardBanner"></div>
    <h3 class="sectitle" id="sugTitle">Best for you right now</h3>
    <div class="suggest" id="sug"></div>
    <div class="controls">
      <div class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input id="q" type="search" placeholder="Find a player" autocomplete="off" aria-label="Find a player"><button class="clr" id="qclr" aria-label="Clear search" hidden>×</button></div>
      <div class="chips" id="posChips" role="group" aria-label="Position"></div>
      <select class="sel" id="sortSel" aria-label="Sort by">
        <option value="val">Best value</option><option value="pts">Most points</option><option value="adp">Where others draft him (ADP)</option>
      </select>
      <label class="chk"><input type="checkbox" id="hideTaken"> Hide taken</label>
    </div>
    <div class="list" id="list"></div>
    <button class="more" id="more" hidden>Show more</button>`;
  $("#q").addEventListener("input", (e) => { S.q = e.target.value; S.show = 60; $("#qclr").hidden = !S.q; renderBoardList(); });
  $("#qclr").onclick = () => { S.q = ""; $("#q").value = ""; $("#qclr").hidden = true; renderBoardList(); $("#q").focus(); };
  $("#sortSel").onchange = (e) => { S.sort = e.target.value; S.show = 60; renderBoardList(); };
  $("#hideTaken").checked = S.hideTaken;
  $("#hideTaken").onchange = (e) => { S.hideTaken = e.target.checked; LS.set("zb-hide", S.hideTaken); S.show = 60; renderBoardList(); };
  $("#more").onclick = () => { S.show += 60; renderBoardList(); };
  $("#list").addEventListener("click", onListClick);
  $("#sug").addEventListener("click", (e) => {
    const b = e.target.closest("[data-open]"); if (!b) return;
    S.open = b.dataset.open; S.q = ""; $("#q").value = ""; S.pos = "ALL"; S.sort = "val"; renderBoard();
    let c = document.querySelector(`.card[data-id="${CSS.escape(S.open)}"]`);
    if (!c) { S.q = player(S.open).n; $("#q").value = S.q; $("#qclr").hidden = false; renderBoardList(); c = document.querySelector(`.card[data-id="${CSS.escape(S.open)}"]`); }
    if (c) c.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}
function renderBoard() {
  const st = draftState();
  const avail = available(st);
  const odds = lastOdds(avail, st.before);
  const lu = fillLineup(rosterOf(S.team, st));
  // banner
  let ban = "";
  if (S.live.err && !S.live.at) ban = `<div class="banner err"><b>Can't reach Fantrax right now.</b> The board still works: open a player and tap <b>Mark as drafted</b> when someone takes him.</div>`;
  else if (!st.made && !st.done) ban = `<div class="banner">Each team already has its <b>${Object.keys(st.taken).length / 12 | 0} keepers</b>, so they're off the board. When the draft starts, players drop off by themselves as picks come in from Fantrax.</div>`;
  $("#boardBanner").innerHTML = ban;
  // suggestions
  const sg = st.done || !st.next ? [] : suggestions(st, avail, lu);
  $("#sugTitle").hidden = !sg.length;
  $("#sugTitle").textContent = st.onClock ? "You're up. Best picks right now" : st.next ? `Best targets for your pick at #${st.next.n}` : "Best available";
  $("#sug").innerHTML = sg.map((x) => `
    <button class="sug" data-open="${esc(x.p.id)}">
      ${face(x.p)}
      <div><div class="k">${x.label}</div><div class="nm">${esc(x.p.n)}</div></div>
      <div class="pts"><b>${fmt(ptsOf(x.p))}</b><small>proj pts</small></div>
      <div class="why">${posLine(x.p)}${x.why.map((w) => `<span class="${w.w ? "warn" : ""}">${esc(w.t)}</span>`).join("")}</div>
    </button>`).join("");
  // position chips with need badges
  const chips = [["ALL", "All"], ["C", "C"], ["W", "W"], ["D", "D"], ["G", "G"], ["STAR", "★"]];
  $("#posChips").innerHTML = chips.map(([k, l]) => `<button data-pos="${k}" aria-pressed="${S.pos === k}" ${k === "STAR" ? 'aria-label="Starred players"' : ""}>${l}${lu.needs[k] > 0 ? `<span class="need" title="Open starting spots">${lu.needs[k]}</span>` : ""}</button>`).join("");
  $("#posChips").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; S.pos = b.dataset.pos; S.show = 60; renderBoard(); };
  $("#sortSel").value = S.sort;
  renderBoardList(st, avail, odds);
}
function posLine(p) {
  return `<span class="nodot">${posBadge(p)} ${esc(p.t || "No team")}${p.age ? ` · age ${p.age}` : ""} · <span class="pill tier" style="--tc:var(--t${tierOf(valOf(p))})">${TIER[tierOf(valOf(p))]}</span></span>`;
}
function renderBoardList(st, avail, odds) {
  st = st || draftState();
  avail = avail || available(st);
  odds = odds || lastOdds(avail, st.before);
  const q = fold(S.q).trim();
  let rows = (S.hideTaken ? avail : B.players).slice();
  if (S.pos === "STAR") rows = rows.filter((p) => S.stars[p.id]);
  else if (S.pos !== "ALL") rows = rows.filter((p) => elig(p).includes(S.pos));
  if (q) {
    rows = (S.hideTaken ? B.players : rows).filter((p) => fold(p.n).includes(q) || fold(p.t) === q);
    if (S.pos !== "ALL" && S.pos !== "STAR") rows = rows.filter((p) => elig(p).includes(S.pos));
  }
  const key = S.pos === "ALL" || S.pos === "STAR" ? "ALL" : S.pos;
  const sorters = {
    val: (a, b) => (valAt(b, key) ?? -999) - (valAt(a, key) ?? -999),
    pts: (a, b) => ((key === "ALL" ? ptsOf(b) : ptsAt(b, key)) ?? -1) - ((key === "ALL" ? ptsOf(a) : ptsAt(a, key)) ?? -1),
    adp: (a, b) => (a.adp ?? 999) - (b.adp ?? 999),
  };
  rows.sort(sorters[S.sort]);
  const list = $("#list");
  if (!rows.length) {
    list.innerHTML = `<div class="empty">${S.pos === "STAR" ? "No starred players yet. Tap the star on any player to build your short list." : q ? "No player matches that search." : "Nobody left here."}</div>`;
    $("#more").hidden = true; return;
  }
  let availRank = 0;
  list.innerHTML = rows.slice(0, S.show).map((p) => {
    const t = st.taken[p.id];
    if (!t) availRank++;
    return cardHTML(p, t, t ? "" : availRank, odds.get(p.id), st, key);
  }).join("");
  $("#more").hidden = rows.length <= S.show;
  $("#more").textContent = `Show more (${rows.length - S.show} left)`;
}
function takenText(t) {
  if (!t) return "";
  if (t.kept) return `Kept by ${tname(t.team)}`;
  if (t.team) return `${t.manual ? "Marked taken" : "Drafted"} by ${tname(t.team)}, pick #${t.pick}`;
  return "Marked as taken";
}
function cardHTML(p, t, rank, odd, st, key) {
  const v = valAt(p, key);
  const tier = tierOf(v);
  const mine = t && t.team === S.team;
  const open = S.open === p.id;
  const tags = [];
  if (t) tags.push(`<span class="tag ${mine ? "warn" : ""}"><b>${esc(takenText(t))}</b></span>`);
  if (v != null) tags.push(`<span class="tag ${v >= 0 ? "good" : "bad"}" title="Points above the best player you could get on waivers at his position"><b>${sgn(v)}</b> value</span>`);
  if (p.adp != null) tags.push(`<span class="tag" title="Average draft position across Fantrax leagues">ADP <b>${fmt(p.adp)}</b></span>`);
  if (!t && odd != null && st.horizon && !st.done) {
    const c = odd >= 0.7 ? "var(--good)" : odd >= 0.4 ? "var(--gold)" : "var(--bad)";
    tags.push(`<span class="odds" title="Chance he is still available at your pick #${st.horizon.n}">Left at #${st.horizon.n} <i style="--w:${pct(odd)};--oc:${c}"></i><b>${pct(odd)}</b></span>`);
  }
  if (p.rk) tags.push(`<span class="pill gold">Rookie</span>`);
  if (p.nt) tags.push(`<span class="pill bad">No NHL contract</span>`);
  if (p.slot === "G" && S.gsOv[p.id] != null) tags.push(`<span class="pill gold">Your starts: ${S.gsOv[p.id]}</span>`);
  const star = !!S.stars[p.id];
  tags.push(`<button class="star" data-star="${esc(p.id)}" aria-pressed="${star}" aria-label="${star ? "Remove from" : "Add to"} short list"><svg viewBox="0 0 24 24" fill="${star ? "currentColor" : "none"}" stroke="currentColor" stroke-width="1.8"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/></svg></button>`);
  const shownPts = key === "ALL" ? ptsOf(p) : ptsAt(p, key);
  return `<div class="card ${t ? "taken" : ""} ${mine ? "mineP" : ""}" data-id="${esc(p.id)}" style="--tc:var(--t${tier})">
    <button class="row" data-toggle="${esc(p.id)}" aria-expanded="${open}">
      <div class="rank">${rank || ""}</div>
      ${face(p)}
      <div class="who"><div class="nm">${esc(p.n)}</div>
        <div class="mt">${posBadge(p)}<span>${esc(p.t || "No team")}${p.age ? ` · ${p.age}` : ""}</span><span class="pill tier">${TIER[tier]}</span></div></div>
      <div class="bigpts"><div class="p">${fmt(shownPts)}</div><div class="l">proj pts</div></div>
    </button>
    <div class="subrow">${tags.join("")}</div>
    ${open ? detailHTML(p, t, st) : ""}
  </div>`;
}
function detailHTML(p, t, st) {
  const parts = [];
  const why = (p.ch || []).map(([tone, txt]) => `<li class="${tone}">${esc(txt)}</li>`).join("");
  const v = valOf(p);
  let lead = "";
  if (v != null) lead = `<li class="info">${v >= 0 ? `About <b>${Math.round(v)}</b> more points than the best ${POSNAME[p.slot].toLowerCase()} you could grab off waivers.` : `Projects below a typical waiver-wire ${POSNAME[p.slot].toLowerCase()} in this league.`}</li>`;
  if (p.unknown) lead = `<li class="info">Not in this board's player list, so there's no projection for him.</li>`;
  parts.push(`<div><h4>Why</h4><ul class="why">${lead}${why}</ul></div>`);
  if (p.brk) {
    const vals = Object.entries(p.brk);
    const mx = Math.max(1, ...vals.map(([, x]) => Math.abs(x)));
    const scale = p.slot === "G" && S.gsOv[p.id] != null ? ptsOf(p) / p.pts : 1;
    parts.push(`<div><h4>Where his ${fmt(ptsOf(p))} points come from</h4><div class="brk">${vals.map(([k, x]) => {
      const y = x * scale;
      return `<div class="r"><span>${esc(k)}</span><span class="t"><i class="${y < 0 ? "neg" : ""}" style="left:0;width:${(100 * Math.abs(x)) / mx}%"></i></span><b>${sgn(y)}</b></div>`;
    }).join("")}</div>${p.slot !== "G" && Object.keys(p.slotpts).length > 1 ? `<p class="note" style="margin:8px 0 0">${Object.entries(p.slotpts).map(([s, x]) => `As a ${POSNAME[s].toLowerCase()}: ${fmt(x)} pts`).join(" · ")}. This league pays wingers and defensemen more per goal and assist, and pays centers for faceoffs.</p>` : ""}</div>`);
  }
  if (p.line) {
    const L = p.line;
    const kv = p.slot === "G"
      ? [["Starts", fmt(gsOf(p))], ["Wins", fmt(L.w * (ptsOf(p) / p.pts))], ["Saves", fmt(L.sv * (ptsOf(p) / p.pts))], ["Goals against", fmt(L.ga * (ptsOf(p) / p.pts))], ["Shutouts", fmt(L.so * (ptsOf(p) / p.pts), 1)], ["Save %", L.svp ? L.svp.toFixed(3).replace(/^0/, "") : "–"]]
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
  // actions
  const acts = [];
  if (!t && !st.done) acts.push(`<button class="btn" data-mark="${esc(p.id)}">Mark as drafted${st.cur ? ` (pick #${st.cur.n}, ${esc(TEAMS[st.cur.team]?.short || tname(st.cur.team))})` : ""}</button>`);
  if (t && t.manual) acts.push(`<button class="btn warn" data-unmark="${esc(p.id)}">Undo: he's still available</button>`);
  if (p.slot === "G" && p.gpg) {
    acts.push(`<span class="note">Know the depth chart? Set his starts:</span><span class="stepper"><button data-gs="${esc(p.id)}" data-d="-5" aria-label="5 fewer starts">−</button><span>${fmt(gsOf(p))}</span><button data-gs="${esc(p.id)}" data-d="5" aria-label="5 more starts">+</button></span>`);
    if (S.gsOv[p.id] != null) acts.push(`<button class="btn" data-gsreset="${esc(p.id)}">Back to our ${fmt(p.gs)}</button>`);
  }
  if (acts.length) parts.push(`<div class="acts">${acts.join("")}</div>`);
  return `<div class="detail">${parts.join("")}</div>`;
}
function onListClick(e) {
  const tg = e.target.closest("[data-toggle],[data-star],[data-mark],[data-unmark],[data-gs],[data-gsreset]");
  if (!tg) return;
  const d = tg.dataset;
  if (d.toggle) { S.open = S.open === d.toggle ? null : d.toggle; rerenderCard(d.toggle); return; }
  if (d.star) { if (S.stars[d.star]) delete S.stars[d.star]; else S.stars[d.star] = 1; LS.set("zb-stars", S.stars); rerenderCard(d.star); return; }
  if (d.mark) { markTaken(d.mark); return; }
  if (d.unmark) { delete S.manual[d.unmark]; LS.set("zb-manual", S.manual); renderAll(); return; }
  if (d.gs) {
    const p = PL.get(d.gs); const cur = gsOf(p);
    S.gsOv[d.gs] = Math.max(0, Math.min(82, Math.round((cur + Number(d.d)) / 5) * 5)); LS.set("zb-gs", S.gsOv); renderAll(); return;
  }
  if (d.gsreset) { delete S.gsOv[d.gsreset]; LS.set("zb-gs", S.gsOv); renderAll(); return; }
}
function rerenderCard(id) {
  // close any other open card, then redraw the affected ones in place
  const st = draftState(); const avail = available(st); const odds = lastOdds(avail, st.before);
  document.querySelectorAll(".card").forEach((c) => {
    const pid = c.dataset.id;
    if (pid !== id && !c.querySelector(".detail")) return;
    const p = player(pid); const t = st.taken[pid];
    const rank = c.querySelector(".rank").textContent;
    const key = S.pos === "ALL" || S.pos === "STAR" ? "ALL" : S.pos;
    const tmp = document.createElement("div");
    tmp.innerHTML = cardHTML(p, t, rank, odds.get(pid), st, key);
    c.replaceWith(tmp.firstElementChild);
  });
}
function markTaken(id) {
  const st = draftState();
  if (!st.cur) return;
  S.manual[id] = st.cur.n; LS.set("zb-manual", S.manual);
  const p = player(id);
  if (S.open === id) S.open = null;
  toast(`${p.n} marked as taken by ${tname(st.cur.team)}`, () => { delete S.manual[id]; LS.set("zb-manual", S.manual); renderAll(); });
  renderAll();
}

/* ---------------- my team ---------------- */
function renderTeam() {
  const st = draftState();
  const mine = rosterOf(S.team, st);
  const lu = fillLineup(mine);
  const avail = available(st);
  const all = META.teams.map((t) => ({ id: t.id, s: fillLineup(rosterOf(t.id, st)).strength })).sort((a, b) => b.s - a.s);
  const rank = all.findIndex((x) => x.id === S.team) + 1;
  const myPicks = st.picks.filter((p) => p.team === S.team);
  const left = myPicks.filter((p) => !p.pid).length;
  const openStarters = Object.values(lu.needs).reduce((a, b) => a + b, 0);
  const el = $("#tab-team");
  const slotRow = (x, s) => `<div class="slot">${face(x.p)}<div class="nm">${esc(x.p.n)}<small>${esc(x.p.t)} · ${keptOr(st.taken[x.p.id])}</small></div><b class="num">${fmt(ptsAt(x.p, s))}</b></div>`;
  const openRow = (s) => {
    const best = avail.filter((p) => elig(p).includes(s) && !p.nt && p.val != null).sort((a, b) => (valAt(b, s) ?? -999) - (valAt(a, s) ?? -999))[0];
    return `<div class="slot open"><div class="open-ic"></div><div class="nm">Open spot${best ? `<small>best left: ${esc(best.n)} (${fmt(ptsAt(best, s))})</small>` : ""}</div><button class="btn" data-goto="${s}">See ${POSPL[s]}</button></div>`;
  };
  const grp = (s, label) => `<div class="slotgrp"><h3>${label}<small>${lu.slots[s].length} of ${CAP[s]} filled</small></h3>${lu.slots[s].map((x) => slotRow(x, s)).join("")}${Array.from({ length: lu.needs[s] }, () => openRow(s)).join("")}</div>`;
  const benchRows = lu.bench.map((p) => `<div class="slot">${face(p)}<div class="nm">${esc(p.n)}<small>${posBadge(p)} ${esc(p.t)} · ${keptOr(st.taken[p.id])}</small></div><b class="num">${fmt(ptsOf(p))}</b></div>`).join("");
  const benchOpen = Math.max(0, BENCH - lu.bench.length);
  el.innerHTML = `
    <div class="lede"><h2>${esc(tname(S.team))}</h2><p>Your keepers and picks, placed in the best lineup. Open spots show the best player still out there.</p></div>
    <div class="hero">
      <div class="stat"><div class="k">Lineup strength</div><div class="v">${fmt(lu.strength)}</div><div class="s">Rank ${rank} of 12 · starters + a quarter of the bench</div></div>
      <div class="stat"><div class="k">Open starting spots</div><div class="v">${openStarters}</div><div class="s">${openStarters ? Object.entries(lu.needs).filter(([, n]) => n > 0).map(([s, n]) => `${n} ${s}`).join(", ") : "Every starting spot is filled"}</div></div>
      <div class="stat"><div class="k">Picks left</div><div class="v">${left}</div><div class="s">${st.next ? (st.onClock ? "You're on the clock" : `Next: #${st.next.n}, round ${st.next.r}`) : "None left"}</div></div>
      <div class="stat"><div class="k">Roster</div><div class="v">${mine.length}<span style="font-size:16px;color:var(--ink3)"> / ${META.roster.max}</span></div><div class="s">${mine.filter((p) => st.taken[p.id].kept).length} kept · ${mine.filter((p) => !st.taken[p.id].kept).length} drafted</div></div>
    </div>
    <h3 class="sectitle">Your picks</h3>
    <div class="picks">${myPicks.map((p) => {
      const pl = p.pid ? player(p.pid) : null;
      const nx = st.next && p.n === st.next.n;
      return `<div class="pk ${nx ? "next" : ""}"><div class="n">#${p.n} · Round ${p.r}${nx ? (st.onClock ? " · now" : " · next") : ""}</div><div class="p">${pl ? esc(pl.n) : '<span class="note">Not made yet</span>'}</div></div>`;
    }).join("") || '<span class="note">No picks in this draft.</span>'}</div>
    <h3 class="sectitle">Lineup</h3>
    <div class="rink">
      ${grp("C", "Centers")}${grp("W", "Wingers")}${grp("D", "Defense")}${grp("G", "Goalies")}
      <div class="slotgrp"><h3>Bench<small>${lu.bench.length} of ${BENCH}</small></h3>${benchRows}${benchOpen ? `<div class="slot open"><div class="open-ic"></div><div class="nm">${benchOpen} open bench spot${benchOpen > 1 ? "s" : ""}<small>Bench players fill in on nights your starters are off</small></div></div>` : ""}</div>
    </div>`;
  el.querySelectorAll("[data-goto]").forEach((b) => (b.onclick = () => { S.pos = b.dataset.goto; S.q = ""; setTab("board"); }));
}
function keptOr(t) { return t ? (t.kept ? "kept" : `pick #${t.pick}`) : ""; }

/* ---------------- pick by pick ---------------- */
function renderGrid() {
  const st = draftState();
  const rounds = {};
  st.picks.forEach((p) => (rounds[p.r] = rounds[p.r] || []).push(p));
  const el = $("#tab-grid");
  el.innerHTML = `<div class="lede"><h2>Pick by pick</h2><p>${st.made} of ${st.total} picks made. Your picks are outlined in gold${st.cur ? ", and the pick on the clock in blue" : ""}. Traded picks show the team that owns them now.</p></div>` +
    Object.keys(rounds).sort((a, b) => a - b).map((r) => `<div class="round"><h3>Round ${r}</h3><div class="cells">${rounds[r].map((p) => {
      const pl = p.pid ? player(p.pid) : null;
      const cls = ["cell", p.team === S.team ? "me" : "", st.cur && st.cur.n === p.n ? "now" : ""].join(" ");
      const T = TEAMS[p.team];
      const tm = T ? (T.name.length > 16 && T.short ? T.short : T.name) : "?";
      return `<div class="${cls}"><div class="h"><span>#${p.n}</span><span>${esc(tm)}</span></div>
        ${pl ? `<div class="pl"><span class="tb" style="--tc:var(--t${tierOf(valOf(pl))})"></span>${esc(pl.n)}</div><div class="pp">${esc((pl.pos || "").replace(/,/g, "/"))} · ${esc(pl.t)} · ${fmt(ptsOf(pl))} pts${p.manual ? " · marked by hand" : ""}</div>`
          : `<div class="pl none">${st.cur && st.cur.n === p.n ? "On the clock" : "—"}</div><div class="pp">&nbsp;</div>`}</div>`;
    }).join("")}</div></div>`).join("");
}

/* ---------------- league ---------------- */
function renderLeague() {
  const st = draftState();
  const rows = META.teams.map((t) => {
    const r = rosterOf(t.id, st); const lu = fillLineup(r);
    const picks = st.picks.filter((p) => p.team === t.id);
    return { t, r, lu, left: picks.filter((p) => !p.pid).length, first: picks.find((p) => !p.pid) };
  }).sort((a, b) => b.lu.strength - a.lu.strength);
  const mx = Math.max(...rows.map((x) => x.lu.strength), 1);
  const el = $("#tab-league");
  el.innerHTML = `<div class="lede"><h2>League</h2><p>Every team's projected lineup strength from its keepers and picks so far. Tap a team to see its roster.</p></div>
  <div class="teams">${rows.map((x, i) => {
    const open = !!S.leagueOpen[x.t.id];
    const lines = [];
    for (const s of ["C", "W", "D", "G"]) for (const y of x.lu.slots[s]) lines.push([s, y.p, ptsAt(y.p, s)]);
    for (const p of x.lu.bench) lines.push(["BN", p, ptsOf(p)]);
    return `<div class="tcard ${x.t.id === S.team ? "me" : ""}">
      <button class="th" data-team="${x.t.id}" aria-expanded="${open}"><div class="rk">${i + 1}</div>
        <div><div class="tn">${esc(x.t.name)}</div><div class="ts">${x.r.length} players · ${x.left} picks left${x.first ? ` · next #${x.first.n}` : ""}</div></div>
        <div class="tp"><b>${fmt(x.lu.strength)}</b><small>strength</small></div></button>
      <div class="meter"><i style="width:${(100 * x.lu.strength) / mx}%"></i></div>
      ${open ? `<div class="body">${lines.map(([s, p, pts]) => `<div class="mini"><span class="pos">${s}</span><span>${esc(p.n)} <span class="note">${esc(p.t)} · ${keptOr(st.taken[p.id])}</span></span><b>${fmt(pts)}</b></div>`).join("")}</div>` : ""}
    </div>`;
  }).join("")}</div>`;
  el.querySelectorAll("[data-team]").forEach((b) => (b.onclick = () => { S.leagueOpen[b.dataset.team] = !S.leagueOpen[b.dataset.team]; renderLeague(); }));
}

/* ---------------- how it works ---------------- */
function renderHow() {
  const sc = META.scoring, bt = META.backtest;
  const el = $("#tab-how");
  const row = (k, c, w, d) => `<tr><td>${k}</td><td>${c}</td><td>${w}</td><td>${d}</td></tr>`;
  el.innerHTML = `<div class="prose">
  <div class="lede"><h2>How it works</h2><p>Plain-English notes on where the numbers come from and how much to trust them.</p></div>
  <h3>This league's scoring</h3>
  <p>Head-to-head points, one matchup a week. ${META.periods - (META.periods - META.firstPlayoff + 1)} regular-season weeks, then ${META.playoffTeams} teams make the playoffs. Lineups: ${CAP.C} centers, ${CAP.W} wingers, ${CAP.D} defensemen, ${CAP.G} goalies, and ${BENCH} bench spots.</p>
  <div class="tablewrap"><table><thead><tr><th>Skater stat</th><th>Center</th><th>Wing</th><th>Defense</th></tr></thead><tbody>
    ${row("Goal", sc.C.g, sc.W.g, sc.D.g)}${row("Assist", sc.C.a, sc.W.a, sc.D.a)}${row("Faceoff win", sc.C.fow, sc.W.fow, sc.D.fow)}
    ${row("Hat trick (bonus)", sc.common.ht, sc.common.ht, sc.common.ht)}${row("Plus/minus", sc.common.pm, sc.common.pm, sc.common.pm)}${row("Penalty minute", sc.common.pim, sc.common.pim, sc.common.pim)}
    ${row("Hit", sc.common.hit, sc.common.hit, sc.common.hit)}${row("Blocked shot", sc.common.blk, sc.common.blk, sc.common.blk)}
  </tbody></table></div>
  <div class="tablewrap"><table><thead><tr><th>Goalie stat</th><th>Points</th></tr></thead><tbody>
    <tr><td>Win</td><td>${sc.goalie.w}</td></tr><tr><td>Save</td><td>${sc.goalie.sv}</td></tr><tr><td>Goal against</td><td>${sc.goalie.ga}</td></tr><tr><td>Shutout</td><td>${sc.goalie.so}</td></tr><tr><td>Goal / assist</td><td>${sc.goalie.g} / ${sc.goalie.a}</td></tr>
  </tbody></table></div>
  <p><b>What that means:</b> defensemen get 4 points for every goal and assist, so a defenseman who scores is worth more than almost any forward. Centers who take lots of faceoffs pile up points (a heavy-faceoff center wins 700+ a season, which is about 175 points). Shots on goal and power-play points aren't scored at all. Goalies earn about 5 points a game, so how many games they start matters most.</p>
  <p class="note">One assumption: a player who can play center or wing is scored at the position you play him in. His card shows both numbers.</p>

  <h3>Projected points</h3>
  <p>Every NHL player's last three seasons, from the NHL's own stats:</p>
  <ul>
    <li><b>Recent seasons count most.</b> Last season counts twice as much as the one before it, and four times as much as the one before that.</li>
    <li><b>Goals come from shots.</b> We project how often he shoots, then how often his shots go in, using his whole career. A player who scored on way more (or fewer) of his shots than usual last season is expected to come back toward his normal rate.</li>
    <li><b>Small samples get pulled toward a typical player</b> at his position, so 15 hot games don't make someone a star.</li>
    <li><b>Age.</b> Players 23 and younger are still getting better. Scoring usually starts slipping around 30 and drops faster after 33.</li>
    <li><b>Games played</b> come from how many games he's played the last three seasons.</li>
    <li><b>Goalies:</b> starts come mostly from last season's workload, shared out among the goalies on his current team. Wins, saves and shutouts are projected per start, with save percentage pulled hard toward league average because it jumps around so much year to year. If you know a team's depth chart better, open the goalie and set his starts yourself.</li>
    <li><b>Rookies and young players</b> without much NHL time lean on where Fantrax drafters are taking them.</li>
    <li><b>No NHL contract right now</b> means we cut the projection to a quarter, because most of those players won't play in the NHL this season.</li>
  </ul>

  <h3>Value and tiers</h3>
  <p><b>Value</b> is how many more points a player should score than the best player you could pick up off waivers at his position. With 12 teams, that waiver-level player is roughly the 36th-best center, the 72nd-best winger, the 72nd-best defenseman and the 36th-best goalie. Right now that's about ${Math.round(REPL.C)} points for a center, ${Math.round(REPL.W)} for a winger, ${Math.round(REPL.D)} for a defenseman and ${Math.round(REPL.G)} for a goalie. That's why a 350-point center can be worth less than a 250-point defenseman.</p>
  <p>Tiers by value: <span class="pill tier" style="--tc:var(--t1)">Elite</span> 120+ · <span class="pill tier" style="--tc:var(--t2)">Great</span> 80–119 · <span class="pill tier" style="--tc:var(--t3)">Very good</span> 50–79 · <span class="pill tier" style="--tc:var(--t4)">Solid</span> 20–49 · <span class="pill tier" style="--tc:var(--t5)">Depth</span> 0–19 · <span class="pill tier" style="--tc:var(--t6)">Waiver level</span> below 0.</p>

  <h3>“Left at your pick”</h3>
  <p>The chance a player is still there at your next pick. It uses his Fantrax ADP (average draft position across Fantrax leagues) compared with the other players still available, and how many picks happen before yours. Treat it as a guide. Your leaguemates don't all draft by ADP.</p>
  <p><b>Best for you right now</b> starts with value, gives a boost to players who fill an open starting spot, and adds a small nudge for players who probably won't last until your next pick.</p>

  <h3>Live picks</h3>
  <p>While the page is open, it checks Fantrax for new picks every few seconds during the draft (every couple of minutes otherwise). Players disappear from the board as soon as Fantrax lists them. If Fantrax is slow or down, open a player and tap <b>Mark as drafted</b>. Fantrax's list takes over again once it catches up. Your stars, hand-marked picks and goalie starts are saved only in this browser. This page only reads from Fantrax and can't change anything in your league.</p>

  <h3>How accurate is it?</h3>
  <p>We tested the method the honest way: projected each of the last three seasons (${esc(bt.seasons)}) using only the seasons before it, then compared the results with what actually happened. The comparison is simply using last season's numbers again.</p>
  <div class="tablewrap"><table><thead><tr><th></th><th>This model</th><th>Last season again</th></tr></thead><tbody>
    <tr><td>Skaters: points-per-game miss</td><td class="hl">${bt.skaters.model.ppg}</td><td>${bt.skaters.naive.ppg}</td></tr>
    <tr><td>Skaters: season-total miss, top 300</td><td class="hl">${bt.skaters.model.tot}</td><td>${bt.skaters.naive.tot}</td></tr>
    <tr><td>Skaters: ranking agreement, top 300 (1 = perfect)</td><td class="hl">${bt.skaters.model.rho}</td><td>${bt.skaters.naive.rho}</td></tr>
    <tr><td>Goalies: points-per-game miss</td><td class="hl">${bt.goalies.model.ppg}</td><td>${bt.goalies.naive.ppg}</td></tr>
    <tr><td>Goalies: season-total miss, top 60</td><td class="hl">${bt.goalies.model.tot}</td><td>${bt.goalies.naive.tot}</td></tr>
    <tr><td>Goalies: ranking agreement, top 60</td><td class="hl">${bt.goalies.model.rho}</td><td>${bt.goalies.naive.rho}</td></tr>
  </tbody></table></div>
  <p>A typical skater's season total is still off by about ${bt.skaters.model.tot} points, mostly from injuries and role changes nobody can see coming. Goalie totals are the hardest to predict because starting jobs change.</p>
  <h3>What it doesn't know</h3>
  <ul>
    <li>Line combinations, power-play units and depth charts for 2026-27. Players get credit for their past ice time.</li>
    <li>Injuries that happen after the season starts, and contract news after ${esc(META.built.slice(0, 10))}.</li>
    <li>How your leaguemates value players. ADP is the best general guide.</li>
  </ul>
  </div>`;
}

/* ---------------- tabs, theme, toast ---------------- */
function setTab(t) {
  S.tab = t; LS.set("zb-tab", t);
  document.querySelectorAll("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === t));
  document.querySelectorAll("main > section").forEach((s) => (s.hidden = s.id !== "tab-" + t));
  renderTab();
  window.scrollTo({ top: 0 });
}
function renderTab() {
  if (S.tab === "board") renderBoard();
  else if (S.tab === "team") renderTeam();
  else if (S.tab === "grid") renderGrid();
  else if (S.tab === "league") renderLeague();
  else if (S.tab === "how") renderHow();
}
function renderAll() {
  const st = draftState();
  renderClock(st);
  renderTab();
}
let toastTimer = null;
function toast(msg, undo) {
  const t = $("#toast");
  $("#toastMsg").textContent = msg;
  $("#toastBtn").hidden = !undo;
  $("#toastBtn").onclick = () => { t.hidden = true; if (undo) undo(); };
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 6000);
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

/* ---------------- live sync ---------------- */
async function fx(ep, qs) {
  const r = await fetch(`${FX}${ep}?${qs || "leagueId=" + META.leagueId}`, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
let syncing = false;
async function sync(forceRosters) {
  if (syncing) return;
  syncing = true;
  try {
    const d = await fx("getDraftResults");
    if (!d || !Array.isArray(d.draftPicks)) throw new Error("no picks");
    S.live.picks = d.draftPicks.map((p) => ({ r: p.round, n: p.pick, team: p.teamId, pid: p.playerId || null }));
    if (forceRosters || Date.now() - S.live.rosAt > 4 * 60 * 1000) {
      const rr = await fx("getTeamRosters");
      const own = {};
      for (const [tid, t] of Object.entries(rr.rosters || {})) for (const it of t.rosterItems || []) own[it.id] = tid;
      S.live.owners = own; S.live.rosAt = Date.now();
    }
    S.live.at = Date.now(); S.live.err = null; S.live.fails = 0;
    // clean up hand marks that Fantrax now covers
    const ids = new Set(S.live.picks.filter((p) => p.pid).map((p) => p.pid));
    let changed = false;
    for (const fid of Object.keys(S.manual)) if (ids.has(fid)) { delete S.manual[fid]; changed = true; }
    if (changed) LS.set("zb-manual", S.manual);
    const unknown = [...ids, ...Object.keys(S.live.owners || {})].some((id) => !PL.has(id));
    if (unknown && !EXTRA) loadExtra();
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
function signature(st) {
  return [st.picks.map((p) => p.pid || "").join(","), Object.keys(st.taken).length, JSON.stringify(S.gsOv), S.team, !!EXTRA].join("|");
}
function afterSync() {
  const st = draftState();
  renderClock(st);
  // announce new picks
  const made = st.picks.filter((p) => p.pid && !p.manual).map((p) => p.n + ":" + p.pid);
  if (S.seenPicks) {
    const fresh = made.filter((k) => !S.seenPicks.has(k));
    if (fresh.length === 1) {
      const [n, pid] = fresh[0].split(":"); const pk = st.picks.find((p) => p.n == n);
      toast(`#${n} ${tname(pk.team)} took ${player(pid).n}`);
    } else if (fresh.length > 1) toast(`${fresh.length} new picks in`);
  }
  S.seenPicks = new Set(made);
  if (st.onClock && !S.wasOnClock) {
    toast("You're on the clock!");
    try { if (navigator.vibrate && navigator.userActivation && navigator.userActivation.hasBeenActive) navigator.vibrate([200, 100, 200]); } catch (e) {}
  }
  S.wasOnClock = st.onClock;
  const sig = signature(st);
  if (sig !== S.lastSig) {
    S.lastSig = sig;
    const ae = document.activeElement;
    const keep = ae && ae.id === "q";
    if (S.tab === "board") { renderBoard(); if (keep) $("#q").focus(); }
    else renderTab();
  }
  schedule(st);
}
let timer = null;
function schedule(st) {
  clearTimeout(timer);
  if (document.hidden) return;
  const now = Date.now();
  const near = DRAFT_AT && now > DRAFT_AT.getTime() - 30 * 60000 && !st.done;
  const going = st.made > 0 && !st.done;
  let ms = near || going ? 8000 : 120000;
  if (S.live.fails) ms = Math.min(60000, 8000 * 2 ** Math.min(S.live.fails, 3));
  timer = setTimeout(() => sync(false), ms);
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) sync(false); else clearTimeout(timer); });
setInterval(() => renderClock(draftState()), 5000);

let resetArmed = 0;
function confirmReset() {
  // two taps within 4 seconds instead of a browser dialog
  if (Date.now() - resetArmed < 4000) { resetArmed = 0; return true; }
  resetArmed = Date.now(); toast("Tap again to clear your stars, hand marks and goalie starts"); return false;
}

/* ---------------- boot ---------------- */
function init() {
  initTheme();
  const sel = $("#teamSel");
  sel.innerHTML = META.teams.slice().sort((a, b) => a.name.localeCompare(b.name)).map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
  sel.value = S.team;
  sel.onchange = () => { S.team = sel.value; LS.set("zb-team", S.team); S.wasOnClock = false; S.lastSig = ""; renderAll(); };
  document.querySelectorAll("nav.tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  $("#subline").textContent = `${META.season} · ${B.players.length} players · built ${new Date(META.built).toLocaleDateString([], { month: "short", day: "numeric" })}`;
  $("#foot").innerHTML = `Stats from the NHL. League, keepers, picks and ADP from Fantrax (read-only). Projections built ${esc(new Date(META.built).toLocaleString())}. Not affiliated with the NHL or Fantrax. <button class="btn" id="resetBtn" style="margin-left:6px;padding:4px 10px;font-size:12.5px">Clear my stars and hand marks</button>`;
  $("#resetBtn").onclick = () => {
    if (!confirmReset()) return;
    S.stars = {}; S.manual = {}; S.gsOv = {};
    LS.set("zb-stars", {}); LS.set("zb-manual", {}); LS.set("zb-gs", {});
    S.lastSig = ""; renderAll(); toast("Cleared stars, hand marks and goalie starts");
  };
  boardShell();
  const hash = location.hash.replace("#", "");
  if (["board", "team", "grid", "league", "how"].includes(hash)) S.tab = hash;
  setTab(S.tab);
  renderClock(draftState());
  sync(true);
}
init();
})();
