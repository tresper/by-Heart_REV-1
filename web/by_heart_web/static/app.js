"use strict";
// By Heart web trainer — client. Drives the existing ADK graphs via the FastAPI API and
// paints each node transition (streamed over SSE) onto two hand-drawn SVG graphs. No CDN,
// no framework: the graphs are tiny and fixed, so a little inline SVG is all it takes.

const SVG_NS = "http://www.w3.org/2000/svg";

// Fixed left-to-right layouts, keyed by the real node names from /api/graphs.
const LAYOUT = {
  build: {
    "__START__":        { x: 55,  y: 120 },
    "provenance_gate":  { x: 205, y: 120 },
    "prosody_analysis": { x: 410, y: 58  },
    "refuse":           { x: 410, y: 192 },
    "curriculum_plan":  { x: 625, y: 58  },
  },
  recall: {
    "__START__":            { x: 50,  y: 120 },
    "present_masked_line":  { x: 205, y: 120 },
    "adjudicate":           { x: 395, y: 120 },
    "advance":              { x: 575, y: 58  },
    "scaffold":             { x: 575, y: 192 },
    "memory_update":        { x: 735, y: 120 },
  },
};
const LABELS = { "__START__": "START" };

// Friendly names for the reasoning log, and which graph node each LLM sub-step belongs
// to (deletion_rationale + adaptive_planner run *inside* curriculum_plan via ctx.run_node,
// so they have no circle of their own — we pulse their parent and log them as sub-steps).
const NODE_LABELS = {
  "__START__": "Start",
  "provenance_gate": "Provenance gate",
  "prosody_analysis": "Prosody analysis (LLM + MCP)",
  "deletion_rationale": "Deletion Rationale (LLM)",
  "adaptive_planner": "Adaptive re-plan (LLM)",
  "curriculum_plan": "Curriculum plan",
  "refuse": "Refused (not public-domain)",
  "present_masked_line": "Present masked line",
  "adjudicate": "Adjudicator — semantic grade (LLM)",
  "scaffold": "Scaffolding Coach — minimum hint (LLM)",
  "advance": "Advance (mastered)",
  "memory_update": "Memory update",
};
const SUBSTEP_PARENT = { "deletion_rationale": "curriculum_plan", "adaptive_planner": "curriculum_plan" };

// ---- session/app state ----
let WSID = null;
let POEM_ID = "frost-stopping-by-woods";
let TOPO = { build: null, recall: null };
let currentSessionIndex = 0;
let currentTargets = [];
let currentTargetIdx = 0;
let currentTargetBlank = null;   // the DOM <span> for the blank currently being quizzed
let solvedWords = {};            // "stanza:line:word" -> {word, earned} — kept filled across re-renders
let currentHintLevel = 0;        // strongest scaffold hint reached on this word (climbs on each retry)
let prevFirstStrip = null;   // {crutch: sessionIndex} from the previous build (for the re-plan diff)
let hasBuilt = false;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const keyOf = (t) => `${t.stanza_idx}:${t.line_idx}:${t.word_idx}`;

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
async function boot() {
  const sess = await fetch("/api/session", { method: "POST" }).then((r) => r.json());
  WSID = sess.web_session_id;
  POEM_ID = sess.default_poem_id || POEM_ID;

  TOPO = await fetch("/api/graphs").then((r) => r.json());
  drawGraph("build", TOPO.build);
  drawGraph("recall", TOPO.recall);

  openStream(sess.stream_url);
  wireButtons();
}

function openStream(url) {
  const es = new EventSource(url);
  es.onmessage = (e) => {
    let m;
    try { m = JSON.parse(e.data); } catch { return; }
    if (m && m.kind) applyTransition(m);
  };
  es.onerror = () => { /* browser auto-reconnects; heartbeats keep it warm */ };
}

// ---------------------------------------------------------------------------
// SVG drawing
// ---------------------------------------------------------------------------
function drawGraph(graph, topo) {
  if (!topo) return;
  const content = document.querySelector(`#svg-${graph} .content`);
  content.innerHTML = "";
  const layout = LAYOUT[graph];

  // edges first (so nodes paint on top)
  topo.edges.forEach((e) => {
    const a = layout[e.from], b = layout[e.to];
    if (!a || !b) return;
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
    line.setAttribute("class", "edge");
    line.setAttribute("marker-end", `url(#arrow-${graph})`);
    line.id = edgeId(graph, e.from, e.to);
    if (e.route) line.dataset.route = e.route;
    content.appendChild(line);
    if (e.route) {
      const t = document.createElementNS(SVG_NS, "text");
      t.setAttribute("x", (a.x + b.x) / 2 + 4);
      t.setAttribute("y", (a.y + b.y) / 2 - 3);
      t.setAttribute("class", "routelabel");
      t.id = `routelabel-${graph}-${e.from}-${e.route}`;
      t.textContent = e.route;
      content.appendChild(t);
    }
  });

  // nodes
  topo.nodes.forEach((name) => {
    const p = layout[name];
    if (!p) return;
    const label = LABELS[name] || name;
    const w = Math.max(46, label.length * 6.2 + 16), h = 26;
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "node");
    g.id = nodeId(graph, name);
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", p.x - w / 2); rect.setAttribute("y", p.y - h / 2);
    rect.setAttribute("width", w); rect.setAttribute("height", h);
    rect.setAttribute("rx", 7);
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", p.x); text.setAttribute("y", p.y + 4);
    text.setAttribute("text-anchor", "middle");
    text.textContent = label;
    g.appendChild(rect); g.appendChild(text);
    content.appendChild(g);
  });
}

const nodeId = (g, n) => `node-${g}-${n}`;
const edgeId = (g, f, t) => `edge-${g}-${f}-${t}`;
const nodeEl = (g, n) => document.getElementById(nodeId(g, n));

function clearGraph(graph) {
  document.querySelectorAll(`#svg-${graph} .node`).forEach((n) =>
    n.classList.remove("active", "done", "waiting"));
  document.querySelectorAll(`#svg-${graph} .edge`).forEach((e) => e.classList.remove("routed"));
  document.querySelectorAll(`#svg-${graph} .routelabel`).forEach((e) => e.classList.remove("routed"));
}

function setActive(graph, name) {
  document.querySelectorAll(`#svg-${graph} .node`).forEach((n) => n.classList.remove("active"));
  const el = nodeEl(graph, name);
  if (el) el.classList.add("active", "done");
}

function markRoute(graph, fromName, route) {
  const topo = TOPO[graph];
  if (!topo) return;
  const edge = topo.edges.find((e) => e.from === fromName && e.route === route);
  if (!edge) return;
  const el = document.getElementById(edgeId(graph, edge.from, edge.to));
  if (el) el.classList.add("routed");
  const lbl = document.getElementById(`routelabel-${graph}-${edge.from}-${route}`);
  if (lbl) lbl.classList.add("routed");
}

// ---------------------------------------------------------------------------
// Collapse / expand a graph. Graph A auto-collapses once a recall session starts
// (it's static after the build) so the reasoning log grows into the freed space;
// it auto-expands again on Build / Re-plan so you can watch the pipeline run.
// ---------------------------------------------------------------------------
function setGraphCollapsed(graph, collapsed) {
  const wrap = $(`gw-${graph}`);
  if (!wrap) return;
  wrap.classList.toggle("collapsed", collapsed);
  const btn = wrap.querySelector(".graphtitle");
  if (btn) btn.setAttribute("aria-expanded", String(!collapsed));
  // Only Graph A's height is handed to the log — it's the one that auto-collapses.
  if (graph === "build") $("agents-panel").classList.toggle("graphA-collapsed", collapsed);
}

function toggleGraph(graph) {
  const wrap = $(`gw-${graph}`);
  if (wrap) setGraphCollapsed(graph, !wrap.classList.contains("collapsed"));
}

// ---------------------------------------------------------------------------
// Live transitions (from SSE)
// ---------------------------------------------------------------------------
function applyTransition(m) {
  const graph = m.graph || "recall";
  if (m.kind === "tool") {
    logItem(`Prosody MCP · ${m.tool}`, "tool");
    const n = nodeEl("build", "prosody_analysis");
    if (n) n.classList.add("active", "done");
    return;
  }
  const label = NODE_LABELS[m.node] || m.node;

  // An LLM sub-step (e.g. deletion_rationale) has no circle of its own — light its
  // parent node instead and log it as an indented reasoning sub-step.
  const parent = SUBSTEP_PARENT[m.node];
  if (parent) {
    const pe = nodeEl(graph, parent);
    if (pe) pe.classList.add("active", "done");
    logItem(`↳ ${label}`, "substep");
    return;
  }

  const known = nodeEl(graph, m.node);
  if (known) setActive(graph, m.node);
  logItem(label + (m.waiting ? "  — waiting for you" : ""), "node");
  if (m.route) {
    markRoute(graph, m.node, m.route);
    logItem(`↳ routed: ${m.route}`, "route");
  }
  if (m.waiting && known) known.classList.add("waiting");
}

function logItem(text, kind) {
  const ul = $("log");
  const li = document.createElement("li");
  if (kind) li.className = kind;
  li.textContent = text;
  ul.appendChild(li);
  while (ul.children.length > 50) ul.removeChild(ul.firstChild);
  ul.scrollTop = ul.scrollHeight;
}

// ---------------------------------------------------------------------------
// Build (Graph A) + re-plan
// ---------------------------------------------------------------------------
async function build() {
  $("btn-build").disabled = true;
  $("btn-replan").disabled = true;
  $("build-status").textContent = "running Graph A…";
  $("build-notice").classList.add("hidden");
  clearGraph("build");
  setGraphCollapsed("build", false);     // expand Graph A so you can watch the pipeline run
  $("gt-status-build").textContent = "";

  const res = await fetch("/api/course/build", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ web_session_id: WSID, poem_id: POEM_ID }),
  }).then((r) => r.json());

  $("btn-build").disabled = false;
  $("btn-replan").disabled = false;

  if (!res.ok) {
    $("build-status").textContent = "";
    const notice = $("build-notice");
    notice.classList.remove("hidden");
    if (res.needs_key) {
      notice.innerHTML = "The provenance gate admitted the poem, but building the course " +
        "needs a Gemini API key (set <code>GOOGLE_API_KEY</code> or " +
        "<code>GEMINI_API_KEY</code> in <code>.env</code>). The gate and graph wiring ran key-free.";
    } else {
      notice.textContent = `Not built: ${res.reason || res.error || "unknown"}`;
    }
    return;
  }

  $("build-status").textContent = "course ready.";
  $("gt-status-build").textContent = "✓ complete";
  renderCourse(res.course);
  await loadTargetsAndDiff();
  $("btn-replan").classList.remove("hidden");
  hasBuilt = true;
}

// Start over as a fresh learner: rotate the learner cookie server-side, then reload so
// boot() re-initializes against the clean (empty-history) learner — the base schedule,
// ready to adapt from scratch, so the re-plan before/after is unambiguous each run.
async function resetProgress() {
  if (!confirm("Reset and start over as a fresh learner? This clears your recorded progress so the re-plan starts from a clean slate.")) return;
  await fetch("/api/session/reset", { method: "POST" });
  location.reload();
}

function renderCourse(course) {
  const list = $("rationale-list");
  list.innerHTML = "";
  course.sessions.forEach((s) => {
    const div = document.createElement("div");
    div.className = "rationale";
    div.innerHTML = `<b>Session ${s.index} · rung ${s.rung}</b> — ${esc(s.rationale || "(no rationale)")}`;
    list.appendChild(div);
  });
  const pick = $("session-pick");
  pick.innerHTML = "";
  course.sessions.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.index;
    opt.textContent = `Session ${s.index} (rung ${s.rung}, ${s.new_masks} new)`;
    pick.appendChild(opt);
  });
  $("course").classList.remove("hidden");
}

// Compute the first session that strips each crutch; show what the re-plan pulled earlier.
async function loadTargetsAndDiff() {
  const data = await fetch(`/api/course?web_session_id=${WSID}&poem_id=${POEM_ID}`).then((r) => r.json());
  if (!data.ok) return;
  window.__targets = data.targets || {};
  const firstStrip = {};
  Object.keys(data.targets).forEach((sIdx) => {
    data.targets[sIdx].forEach((t) => {
      if (t.crutch_class && t.crutch_class !== "none" && !(t.crutch_class in firstStrip)) {
        firstStrip[t.crutch_class] = Number(sIdx);
      }
    });
  });
  if (prevFirstStrip) {
    const moved = [];
    Object.keys(firstStrip).forEach((c) => {
      const before = prevFirstStrip[c], after = firstStrip[c];
      if (before != null && after != null && after < before) {
        moved.push(`${c}: session ${before} → ${after}`);
      }
    });
    const note = document.createElement("div");
    note.className = "rationale";
    note.innerHTML = moved.length
      ? `<span class="moved">Re-plan pulled a crutch earlier ⟶ ${moved.map(esc).join("; ")}</span>`
      : `<span class="muted">Re-plan kept the schedule (not enough recall signal yet to shift a crutch).</span>`;
    $("rationale-list").prepend(note);
    await showProfile();
  }
  prevFirstStrip = firstStrip;
}

async function showProfile() {
  const mem = await fetch(`/api/memory?web_session_id=${WSID}&poem_id=${POEM_ID}`).then((r) => r.json());
  const dom = (mem.profile && mem.profile.dominant) || [];
  if (!dom.length) return;
  const note = document.createElement("div");
  note.className = "rationale";
  note.innerHTML = `<b>Diagnosed pattern</b> — you lean on: ${dom.map(esc).join(", ")} ` +
                   `(${mem.profile.total_attempts} attempts)`;
  $("rationale-list").prepend(note);
}

// ---------------------------------------------------------------------------
// Recall (Graph B)
// ---------------------------------------------------------------------------

// Render the stanza from structured segments so the ONE quizzed blank is distinct from
// the stanza's other blanks; remember its <span> so we can fill it in on a correct recall.
function renderStanza(stanzaLines) {
  const pv = $("poem-view");
  pv.innerHTML = "";
  currentTargetBlank = null;
  stanzaLines.forEach((segs, li) => {
    segs.forEach((s) => {
      if (s.t === "text") { pv.appendChild(document.createTextNode(s.v)); return; }
      const span = document.createElement("span");
      const solved = s.stanza_idx != null
        ? solvedWords[`${s.stanza_idx}:${s.line_idx}:${s.word_idx}`] : null;
      if (s.target) {
        // the blank being quizzed right now — pulsing, awaiting recall
        span.className = "blank target";
        span.textContent = "_".repeat(Math.max(1, s.len));
        span.id = "target-blank";
        currentTargetBlank = span;
      } else if (solved) {
        // a word already earned (green) or revealed (amber) — keep it filled in
        span.className = "blank " + (solved.earned ? "correct" : "revealed");
        span.textContent = solved.word;
      } else {
        span.className = "blank";
        span.textContent = "_".repeat(Math.max(1, s.len));
      }
      pv.appendChild(span);
    });
    if (li < stanzaLines.length - 1) pv.appendChild(document.createTextNode("\n"));
  });
}

function setRecallEnabled(on) {
  $("recall-input").disabled = !on;
  $("btn-submit").disabled = !on;
}

async function startSession() {
  currentSessionIndex = Number($("session-pick").value);
  const targets = (window.__targets || {})[currentSessionIndex] || [];
  currentTargets = targets;
  currentTargetIdx = 0;
  solvedWords = {};        // fresh slate of earned/revealed words for this run-through
  currentHintLevel = 0;
  $("session-done").classList.add("hidden");
  setGraphCollapsed("build", true);      // Graph A is static now — give the log the room
  if (!currentTargets.length) {
    $("recall").classList.remove("hidden");
    $("poem-view").textContent = "(no new words to recall in this session)";
    return;
  }
  $("recall").classList.remove("hidden");
  await startTarget();
}

async function startTarget() {
  clearGraph("recall");
  $("result").innerHTML = "";
  ["btn-next", "btn-retry", "btn-reveal"].forEach((id) => $(id).classList.add("hidden"));
  $("waiting").classList.add("hidden");
  setRecallEnabled(true);
  const t = currentTargets[currentTargetIdx];

  const res = await fetch("/api/recall/start", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      web_session_id: WSID, poem_id: POEM_ID, session_index: currentSessionIndex,
      target: { stanza_idx: t.stanza_idx, line_idx: t.line_idx, word_idx: t.word_idx },
      // climbs across retries of the same word so the scaffold ladder escalates 1→2→3
      prior_hint_level: currentHintLevel,
    }),
  }).then((r) => r.json());

  if (!res.ok) {
    $("poem-view").textContent = `Could not present a word: ${res.reason || "unknown"}`;
    return;
  }
  if (Array.isArray(res.stanza_lines) && res.stanza_lines.length) {
    renderStanza(res.stanza_lines);
  } else {
    // Fallback (older payloads): flat string, blanks styled generically, no single target.
    currentTargetBlank = null;
    $("poem-view").innerHTML = esc(res.rendered_stanza).replace(/_+/g, (mm) => `<span class="blank">${mm}</span>`);
  }
  $("recall-progress").textContent = `· word ${currentTargetIdx + 1} of ${currentTargets.length}`;
  const cues = (res.available_cues || []);
  $("cue-note").textContent = cues.length
    ? `This blank leans on: ${cues.join(", ")} — recall it without the crutch.`
    : "This blank has no strong crutch — pure recall.";
  $("waiting").classList.remove("hidden");
  const input = $("recall-input");
  input.value = ""; input.focus();
}

async function submitRecall() {
  if ($("btn-submit").disabled) return;   // this pause is spent — use Try again / Reveal
  const input = $("recall-input");
  $("waiting").classList.add("hidden");
  document.querySelectorAll("#svg-recall .node").forEach((n) => n.classList.remove("waiting"));

  const res = await fetch("/api/recall/submit", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ web_session_id: WSID, recall: input.value }),
  }).then((r) => r.json());

  if (!res.ok) {
    $("result").textContent = res.reason || "could not grade";
    return;
  }
  setRecallEnabled(false);   // the RequestInput pause is consumed; next move is a button
  const t = currentTargets[currentTargetIdx];

  // Fill the quizzed blank: green with the poem's word on a success, a red flash on a miss.
  if (currentTargetBlank) {
    currentTargetBlank.classList.remove("target");
    if (res.advanced && res.revealed_word) {
      currentTargetBlank.textContent = res.revealed_word;
      currentTargetBlank.classList.add("correct");
    } else {
      currentTargetBlank.classList.add("wrong");
    }
  }

  let html = `<span class="tag ${res.outcome}">${res.outcome.replace("_", " ")}</span> `;
  if (res.crutch_dependence && res.crutch_dependence !== "none") {
    html += `<span class="tag crutch">leaned on: ${esc(res.crutch_dependence)}</span> `;
  }
  if (res.advanced) {
    html += `<span class="small good">✓ filled in — ${res.outcome === "variant" ? "accepted variant" : "correct"}</span>`;
  }
  if (res.hint) {
    html += `<div class="small" style="margin-top:8px;">Scaffold hint (level ${res.hint_level}): ${esc(res.hint)}</div>`;
  }
  $("result").innerHTML = html;

  if (res.advanced) {
    // Earned — keep it filled green across re-renders, reset the ladder, offer the next word.
    if (res.revealed_word) solvedWords[keyOf(t)] = { word: res.revealed_word, earned: true };
    currentHintLevel = 0;
    if (currentTargetIdx + 1 < currentTargets.length) $("btn-next").classList.remove("hidden");
    else $("session-done").classList.remove("hidden");
  } else {
    // Missed — let them try again (the scaffold hint climbs) or give up and reveal it.
    currentHintLevel = res.hint_level || currentHintLevel;
    $("btn-retry").classList.remove("hidden");
    $("btn-reveal").classList.remove("hidden");
  }
}

// Re-present the SAME word. currentHintLevel is preserved, so the Scaffolding Coach climbs
// the cue-withdrawal ladder (level 1 rhyme → 2 first letter → 3 gloss) on each retry.
function tryAgain() {
  startTarget();
}

// The explicit "I give up": disclose the word (held server-side until now), fill the blank
// in its distinct revealed style, keep it visible, and move on to the next word.
async function revealAndContinue() {
  const res = await fetch("/api/recall/reveal", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ web_session_id: WSID, recall: "" }),
  }).then((r) => r.json());

  const t = currentTargets[currentTargetIdx];
  if (res.ok && res.revealed_word && currentTargetBlank) {
    currentTargetBlank.classList.remove("target", "wrong");
    currentTargetBlank.textContent = res.revealed_word;
    currentTargetBlank.classList.add("revealed");
    solvedWords[keyOf(t)] = { word: res.revealed_word, earned: false };
  }
  ["btn-retry", "btn-reveal"].forEach((id) => $(id).classList.add("hidden"));
  nextWord();
}

function nextWord() {
  currentHintLevel = 0;            // a fresh word starts the scaffold ladder over
  currentTargetIdx += 1;
  if (currentTargetIdx < currentTargets.length) {
    startTarget();
  } else {
    // No more words: leave the stanza as-is (solved/revealed words stay filled) and finish.
    ["btn-next", "btn-retry", "btn-reveal"].forEach((id) => $(id).classList.add("hidden"));
    $("session-done").classList.remove("hidden");
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
function wireButtons() {
  $("btn-build").addEventListener("click", build);
  $("btn-replan").addEventListener("click", build);
  $("btn-reset").addEventListener("click", resetProgress);
  $("btn-start").addEventListener("click", startSession);
  $("btn-submit").addEventListener("click", submitRecall);
  $("btn-next").addEventListener("click", nextWord);
  $("btn-retry").addEventListener("click", tryAgain);
  $("btn-reveal").addEventListener("click", revealAndContinue);
  $("recall-input").addEventListener("keydown", (e) => { if (e.key === "Enter") submitRecall(); });
  document.querySelectorAll(".graphtitle").forEach((btn) =>
    btn.addEventListener("click", () => toggleGraph(btn.dataset.graph)));
}

boot();
