const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;
let turn = null;      // timing data for the timeline (one turn)
let view = null;      // DOM handles of the current turn in the conversation

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sec = (id) => id.split(":").slice(0, 2).join(" §");
const ACTION = {
  WAIT: { label: "Waiting for enough context", short: "Wait" },
  RETRIEVE: { label: "Searching the documents", short: "Retrieve" },
  SUPPRESS: { label: "No search needed", short: "Suppress" },
};
const EMPTY_HERO = $("emptyState").outerHTML;
const chunkCache = new Map();

function setStatus(text, cls) {
  $("systemStatus").className = `status-pill ${cls || ""}`;
  $("statusText").textContent = text;
  $("liveIndicator").textContent = text;
  $("liveIndicator").className = `live-badge ${cls || ""}`;
}

function setLiveState(action, reason) {
  $("liveState").className = `live-state ${action}`;
  $("liveState").innerHTML = `<span class="ls-action">${esc(ACTION[action]?.label ?? action)}</span><span class="ls-reason">${esc(reason)}</span>`;
}

async function newSession() {
  if (sessionId) fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
  const r = await fetch("/api/sessions", { method: "POST" });
  sessionId = (await r.json()).session_id;
  $("sessionIdDisplay").textContent = sessionId;
  turn = null;
  view = null;
  setStatus("Ready", "");
  $("thread").innerHTML = EMPTY_HERO;
  $("liveState").className = "live-state idle";
  $("liveState").innerHTML = '<span class="ls-action">Idle</span><span class="ls-reason">Start a scenario to see each decision as the words arrive.</span>';
  $("controllerCards").innerHTML = "";
  $("subqueries").innerHTML = '<p class="muted">No sub-queries yet.</p>';
  $("evidence").innerHTML = '<p class="muted">No evidence retrieved yet.</p>';
  $("versions").innerHTML = '<p class="muted">Each answer version and what changed appears here.</p>';
  $("events").innerHTML = "";
  $("timeline").innerHTML = '<p class="muted">The timeline appears once a turn starts.</p>';
  $("metricClaims").textContent = "–";
  $("metricFabricated").textContent = "–";
  $("metricAbstain").textContent = "–";
  $("metricAbstain").className = "metric-value";
  $("unsupportedList").innerHTML = "";
}

function addTelemetry(t, type, desc) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="e-time">${t.toFixed(2)}s</span><span class="e-type">${esc(type)}</span><span class="e-desc">${desc}</span>`;
  $("events").appendChild(li);
}

function addToThread(html) {
  $("emptyState")?.remove();
  $("thread").insertAdjacentHTML("beforeend", html);
  const el = $("thread").lastElementChild;
  el.scrollIntoView({ block: "nearest" });
  return el;
}

function newTurnView() {
  const el = addToThread(`
    <article class="turn">
      <div class="msg user">
        <div class="msg-label">User <span class="hint">simulated speech</span></div>
        <p class="utterance"></p>
      </div>
      <div class="msg assistant">
        <div class="msg-label">Streaming Live RAG <span class="badges"></span></div>
        <p class="progress">Listening…</p>
        <div class="answer-body"></div>
        <div class="extra"></div>
        <ol class="sources"></ol>
      </div>
    </article>`);
  return {
    utterance: el.querySelector(".utterance"),
    badges: el.querySelector(".badges"),
    progress: el.querySelector(".progress"),
    body: el.querySelector(".answer-body"),
    extra: el.querySelector(".extra"),
    sources: el.querySelector(".sources"),
    rendered: false,
  };
}

// Numbered citations: [n] links to the cited chunk; the source list below shows its real text.
function numberer() {
  const ids = [];
  return { ids, n: (id) => (ids.includes(id) ? ids.indexOf(id) : ids.push(id) - 1) + 1 };
}

const citeChip = (num, id) =>
  `<button type="button" class="cite" data-chunk="${esc(id)}" title="${esc(sec(id))}: open the source">${num.n(id)}</button>`;

async function chunk(id) {
  if (!chunkCache.has(id)) chunkCache.set(id, fetch(`/api/chunks/${encodeURIComponent(id)}`).then((r) => (r.ok ? r.json() : null)));
  return chunkCache.get(id);
}

function renderSources(v, ids) {
  v.sources.innerHTML = ids.map((id, i) => `
    <li class="source" data-chunk="${esc(id)}" tabindex="0" role="button" title="Open the full source section">
      <span class="src-num">${i + 1}</span>
      <div><div class="src-head">${esc(sec(id))}<span class="src-title"></span></div><p class="src-text">Loading source text…</p></div>
    </li>`).join("");
  ids.forEach(async (id, i) => {
    const li = v.sources.children[i];
    const c = await chunk(id);
    if (!c || !li) { if (li) li.querySelector(".src-text").textContent = "Source text unavailable."; return; }
    li.querySelector(".src-title").textContent = ` · ${c.section_title}`;
    const text = c.text.replace(/\s+/g, " ").trim();
    li.querySelector(".src-text").textContent = text.length > 240 ? `${text.slice(0, 240)}…` : text;
  });
}

function renderClaims(v, claims, refinement) {
  const num = numberer();
  const live = claims.filter((c) => c.supported && c.status !== "removed");
  v.body.innerHTML = live.map((c) => {
    const isNew = refinement && c.status === "added";
    return `<p class="claim${isNew ? " added" : ""}">${isNew ? '<span class="new-tag">New</span>' : ""}${esc(c.text)} ${[...new Set(c.citations)].map((id) => citeChip(num, id)).join("")}</p>`;
  }).join("");
  const removed = claims.filter((c) => c.status === "removed");
  if (removed.length) {
    v.body.insertAdjacentHTML("beforeend", removed.map((c) => `<p class="claim removed">${esc(c.text)}</p>`).join(""));
  }
  renderSources(v, num.ids);
  v.rendered = true;
}

// Suppressed and baseline turns arrive as plain text with "[DOC_01 §S2]" markers; link a marker only
// when it matches a citation the backend returned.
function renderAnswerText(v, answer, citations) {
  const ids = citations.map((c) => (typeof c === "string" ? c : c.chunk_id));
  const num = numberer();
  const parts = [];
  const re = /(.+?)\s*\[([A-Z]+_\d+) §(S\d+)\]/g;
  let m, last = 0;
  while ((m = re.exec(answer))) {
    const id = ids.find((x) => sec(x) === `${m[2]} §${m[3]}`);
    parts.push(`<p class="claim">${esc(m[1].trim())} ${id ? citeChip(num, id) : `<span class="cite-text">[${esc(m[2])} §${esc(m[3])}]</span>`}</p>`);
    last = re.lastIndex;
  }
  const rest = answer.slice(last).trim();
  if (rest) parts.push(`<p class="claim">${esc(rest)}</p>`);
  v.body.innerHTML = parts.join("");
  renderSources(v, num.ids);
  v.rendered = true;
}

function badge(text, cls) {
  return `<span class="badge ${cls}">${esc(text)}</span>`;
}

function drawTimeline() {
  if (!turn) return;
  const ts = [turn.end, ...turn.chunks.map((c) => c.t), ...turn.decisions.map((d) => d.t),
    ...turn.retrievals.map((r) => r.t1 ?? r.t0), turn.firstToken ?? 0];
  const max = Math.max(...ts) * 1.08 + 0.2;
  const x = (t) => `${(100 * t) / max}%`;

  const lanes = [["Speech", 0], ["Controller", 30], ["Retrieval", 60], ["Answer", 90]];
  let h = lanes.map(([n, y]) => `<div class="tl-lane-label" style="top:${y + 2}px">${n}</div><div class="tl-lane" style="top:${y}px"></div>`).join("");
  const inner = (y, content) => `<div class="tl-lane" style="top:${y}px;border:none;left:90px">${content}</div>`;

  const speechEnd = turn.utterEnd ?? turn.chunks.at(-1)?.t ?? 0;
  let s = turn.chunks.length ? `<div class="tl-bar tl-speech" style="left:0;width:${x(speechEnd)}"></div>` : "";
  s += turn.chunks.map((c) => `<div class="tl-tick" style="left:${x(c.t)}" title="${esc(c.text)}"></div>`).join("");
  h += inner(0, s);
  h += inner(30, turn.decisions.map((d) => `<div class="tl-dot ${d.action}" style="left:${x(d.t)}" title="${d.action}: ${esc(d.reason)}"></div>`).join(""));
  h += inner(60, turn.retrievals.map((r) => {
    const w = Math.max(0.6, (100 * ((r.t1 ?? r.t0 + 0.05) - r.t0)) / max);
    return `<div class="tl-bar tl-ret ${r.prov ? "prov" : ""}" style="left:${x(r.t0)};width:${w}%" title="${r.prov ? "provisional" : "final"} ${r.ids.join(",")}"></div>`;
  }).join(""));
  if (turn.firstToken != null) {
    h += inner(90, `<div class="tl-first" style="left:${x(turn.firstToken)}">● first token</div>`);
  }
  if (turn.utterEnd != null) {
    h += `<div style="position:absolute;left:90px;right:10px;top:0;bottom:0;pointer-events:none"><div class="tl-endline" style="left:${x(turn.utterEnd)}"></div><div class="tl-endlabel" style="left:${x(turn.utterEnd)}">Utterance end (${turn.utterEnd.toFixed(2)}s)</div></div>`;
  }
  $("timeline").innerHTML = h;
}

function render(ev) {
  const t = ev.t;
  switch (ev.type) {
    case "TURN_STARTED":
      turn = { end: ev.scheduled_end_t, chunks: [], decisions: [], retrievals: [], utterEnd: null, firstToken: null, suppressed: false, refinement: false };
      view = newTurnView();
      setStatus("Listening", "listening");
      $("controllerCards").innerHTML = "";
      if ($("system").value === "baseline") {
        $("liveState").className = "live-state idle";
        $("liveState").innerHTML = '<span class="ls-action">Baseline: no controller</span><span class="ls-reason">Turn-based RAG waits for the whole utterance, then searches once.</span>';
      }
      addTelemetry(t, ev.type, `turn started · v${ev.answer_version ?? 0}`);
      break;

    case "TRANSCRIPT_CHUNK":
      turn.chunks.push({ t, text: ev.text });
      view.utterance.insertAdjacentHTML("beforeend", `<span class="t-chunk">${esc(ev.text)} </span>`);
      addTelemetry(t, ev.type, `“${esc(ev.text)}”`);
      break;

    case "RETRIEVAL_DECISION": {
      if (!ev.final) turn.decisions.push({ t, action: ev.action, reason: ev.reason });
      turn.last = ev;
      setLiveState(ev.action, ev.reason);
      if (!view.rendered) view.progress.textContent = `${ACTION[ev.action]?.label ?? ev.action}…`;
      const li = document.createElement("li");
      li.className = `decision ${ev.action}`;
      li.innerHTML = `<span class="d-action">${esc(ACTION[ev.action]?.short ?? ev.action)}</span><span class="d-reason">${esc(ev.reason)}</span><span class="d-time">${t.toFixed(2)}s</span>`;
      $("controllerCards").appendChild(li);
      addTelemetry(t, ev.type, `action=${ev.action} reason=${esc(ev.reason)}`);
      break;
    }

    case "QUERY_CREATED":
      addTelemetry(t, ev.type, `id=${esc(ev.sub_query_id)} text=“${esc(ev.query)}”`);
      break;

    case "RETRIEVAL_STARTED":
      turn.retrievals.push({ t0: t, t1: null, ids: ev.sub_query_ids, prov: ev.provisional });
      setStatus("Searching", "searching");
      addTelemetry(t, ev.type, `ids=${ev.sub_query_ids.join(",")}`);
      break;

    case "RETRIEVAL_COMPLETED":
      if (ev.batch) {
        const r = turn.retrievals.findLast((r) => r.t1 == null);
        if (r) r.t1 = t;
      } else {
        addTelemetry(t, ev.type, `id=${esc(ev.sub_query_id)} ms=${ev.retrieval_ms + ev.rerank_ms} top=${ev.top_chunks.length}`);
      }
      break;

    case "UTTERANCE_END":
      turn.utterEnd = t;
      if (!view.rendered) view.progress.textContent = "Speech ended. Preparing the answer…";
      addTelemetry(t, ev.type, "user stopped speaking");
      break;

    case "DECOMPOSITION":
      if (ev.provisional) break;
      if (ev.refinement) turn.refinement = true;
      $("subqueries").innerHTML = ev.sub_queries.map((q) => `
        <div class="query-card">
          <div class="q-id">${esc(q.id)}</div>
          <div class="q-text">“${esc(q.text)}”</div>
          <div class="q-meta">Topic: ${esc(q.intent)}${q.carried_context.length ? ` · Carried context: ${esc(q.carried_context.join(", "))}` : ""}</div>
        </div>`).join("");
      addTelemetry(t, ev.type, `queries=${ev.sub_queries.length}`);
      break;

    case "EVIDENCE_FUSED":
      $("evidence").innerHTML = ev.evidence.map((e) => `
        <div class="ev-card" data-chunk="${esc(e.chunk_id)}" title="Open the source section">
          <div class="ev-header"><strong>${esc(sec(e.chunk_id))}</strong><span>Sub-queries: ${e.sub_query_ids.join(", ")}${e.signals?.rerank !== undefined ? ` · rerank ${e.signals.rerank}` : ""}</span></div>
        </div>`).join("");
      addTelemetry(t, ev.type, `evidence_items=${ev.evidence.length}`);
      break;

    case "RETRIEVAL_SUPPRESSED":
      turn.suppressed = true;
      view.extra.insertAdjacentHTML("beforeend", `<div class="note suppress"><strong>No search needed.</strong> This request only reshapes the previous answer, so it was rebuilt from session memory without searching the documents. <span class="muted">(${esc(ev.reason)})</span></div>`);
      addTelemetry(t, ev.type, esc(ev.reason));
      break;

    case "ANSWER_DELTA":
      if (turn.firstToken == null) {
        turn.firstToken = t;
        setStatus("Answering", "answering");
      }
      break;

    case "CITATION_VALIDATED":
      $("metricClaims").textContent = `${ev.num_supported}/${ev.num_claims}`;
      $("metricFabricated").textContent = ev.fabricated_citations.length;
      $("unsupportedList").innerHTML = ev.unsupported_claims.map((u) => `<div class="unsupported-item">Removed: ${esc(u.claim)} (${esc(u.reason)})</div>`).join("");
      addTelemetry(t, ev.type, `supported=${ev.num_supported}/${ev.num_claims}`);
      break;

    case "ANSWER_VERSION_UPDATED": {
      const refined = ev.answer_version > 1 && turn.refinement;
      renderClaims(view, ev.claims, refined);
      view.badges.innerHTML = badge(`v${ev.answer_version}`, "version");
      if (refined) {
        view.extra.insertAdjacentHTML("beforeend", `<div class="note refine"><strong>Updated, not restarted.</strong> ${ev.change_log.map(esc).join(" · ")}</div>`);
      }
      $("versions").querySelector(".muted")?.remove();
      $("versions").insertAdjacentHTML("afterbegin", `<div class="v-hist-item"><strong>v${ev.answer_version}</strong> ${ev.change_log.map(esc).join("; ")}</div>`);
      addTelemetry(t, ev.type, `v${ev.answer_version} updated`);
      break;
    }

    case "FINAL_RESPONSE": {
      const unc = ev.uncertainty || [];
      const cites = ev.citations || [];
      if (!view.rendered) {
        if (ev.answer && ev.answer.trim()) renderAnswerText(view, ev.answer, cites);
        else view.body.innerHTML = "";
      }
      // ABSTAINED = no grounded claim at all; PARTIAL = some sub-intents answered, others flagged.
      let state, cls;
      if (ev.suppressed) { state = "Reformatted · no search"; cls = "suppress"; }
      else if (!cites.length) { state = "Abstained"; cls = "warn"; }
      else if (unc.length) { state = "Partial answer"; cls = "warn"; }
      else { state = "Answered"; cls = "ok"; }
      view.badges.insertAdjacentHTML("beforeend", badge(state, cls));
      $("metricAbstain").textContent = state.split(" ·")[0];
      $("metricAbstain").className = `metric-value ${cls}`;
      if (unc.length) {
        view.extra.insertAdjacentHTML("beforeend", `<div class="note uncertain"><strong>${cites.length ? "Not everything could be verified." : "The documents don't cover this."}</strong>${unc.map((u) => `<div>${esc(u)}</div>`).join("")}</div>`);
      }
      const first = turn.retrievals[0];
      if (first && turn.utterEnd != null && !ev.suppressed) {
        const lead = turn.utterEnd - first.t0;
        const speed = parseFloat($("speed").value);
        const at = speed === 1 ? "" : ` (replay clock at ${speed}x speed)`;
        view.extra.insertAdjacentHTML("beforeend", `<p class="timing">${lead > 0
          ? `Search started <strong>${lead.toFixed(1)} s before</strong> the speaker finished${at}.`
          : `Search started ${(-lead).toFixed(1)} s after the speaker finished${at}.`}</p>`);
      }
      if (turn.last) {
        $("liveState").className = `live-state done ${turn.last.action}`;
        $("liveState").innerHTML = `<span class="ls-action">Done</span><span class="ls-reason">Last decision: ${esc(turn.last.action)}, ${esc(turn.last.reason)}</span>`;
      }
      view.progress.remove();
      setStatus("Done", "done");
      addTelemetry(t, ev.type, "done");
      break;
    }

    case "ERROR":
      setStatus("Error", "error");
      if (view) {
        view.progress.textContent = "";
        view.extra.insertAdjacentHTML("beforeend", `<div class="note error"><strong>Something went wrong.</strong> ${esc(ev.message)}</div>`);
      } else {
        addToThread(`<div class="note error"><strong>Something went wrong.</strong> ${esc(ev.message)}</div>`);
      }
      addTelemetry(t, ev.type, esc(ev.message));
      break;
  }
  if (turn) drawTimeline();
  $("thread").scrollTop = $("thread").scrollHeight;   // follow the newest message, as a chat does
}

function setBusy(on) {
  busy = on;
  document.querySelectorAll("#scenarioButtons button, #customForm button, #newSession, #system").forEach((b) => (b.disabled = on));
  document.body.classList.toggle("busy", on);
}

async function runTurn(chunks, endT) {
  if (busy) return;
  if (!sessionId) await newSession();
  setBusy(true);
  addTelemetry(0, "UI", "── new turn ──");
  try {
    const post = () => fetch(`/api/sessions/${sessionId}/turns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chunks, end_t: endT, speed: parseFloat($("speed").value), system: $("system").value }),
    });
    let res = await post();
    // Sessions expire after 30 idle minutes; the server has already dropped that memory, so start fresh once.
    if (res.status === 404) {
      await newSession();
      res = await post();
    }
    if (!res.ok) throw new Error(await res.text());
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 2);
        if (line.startsWith("data: ")) render(JSON.parse(line.slice(6)));
      }
    }
  } catch (e) {
    render({ type: "ERROR", t: 0, message: e.message });
  } finally {
    setBusy(false);
  }
}

async function loadScenarios() {
  try {
    const sc = await (await fetch("/api/scenarios")).json();
    Object.values(sc).forEach((s, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.innerHTML = `<b>${i + 1}</b>${esc(s.label || s.title)}`;
      b.title = s.narration || s.title;
      b.onclick = async () => {
        if (busy) return;
        await newSession();
        addToThread(`<div class="scenario-note"><strong>${esc(s.title)}</strong>${s.narration ? `<span>${esc(s.narration)}</span>` : ""}</div>`);
        for (const t of s.turns) await runTurn(t.chunks, t.end_t);
      };
      $("scenarioButtons").appendChild(b);
    });
  } catch (e) {
    console.error("Failed to load scenarios:", e);
  }
}

$("customForm").onsubmit = (e) => {
  e.preventDefault();
  const parts = $("customText").value.split("|").map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return;
  let t = 0;
  const chunks = parts.map((text) => { const c = { t: +t.toFixed(2), text }; t += text.split(/\s+/).length / 2.5; return c; });
  $("customText").value = "";
  runTurn(chunks, +(t + 0.5).toFixed(2));
};

async function openChunk(id) {
  const c = await chunk(id);
  if (!c) return;
  $("chunkTitle").textContent = `${c.document_id} §${c.section_id} · ${c.section_title}`;
  $("chunkMeta").textContent = `${c.source_title} · ${c.source_file} lines ${c.line_start}-${c.line_end}`;
  $("chunkText").textContent = c.text;
  $("chunkDialog").showModal();
}

document.addEventListener("click", (e) => {
  const el = e.target.closest && e.target.closest("[data-chunk]");
  if (el) openChunk(el.dataset.chunk).catch((err) => console.error("Failed to fetch chunk:", err));
});
document.addEventListener("keydown", (e) => {
  const el = (e.key === "Enter" || e.key === " ") && e.target.closest && e.target.closest("li[data-chunk]");
  if (el) { e.preventDefault(); openChunk(el.dataset.chunk); }
});

$("newSession").onclick = () => { if (!busy) newSession(); };
// Baseline and proposed must not share session memory (a proposed turn would otherwise
// "refine" a baseline answer), so switching system starts a fresh session.
$("system").onchange = () => { if (!busy) newSession(); };

loadScenarios();
