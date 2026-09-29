const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;
let turn = null;
let lastClaims = [];

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sec = (id) => id.split(":").slice(0, 2).join(" §");

// State reset for new session
async function newSession() {
  if (sessionId) fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
  const r = await fetch("/api/sessions", { method: "POST" });
  sessionId = (await r.json()).session_id;
  
  $("sessionIdDisplay").textContent = sessionId;
  $("systemStatus").innerHTML = `<span class="status-dot"></span> <span>READY</span>`;
  
  // Clear UI
  $("transcript").innerHTML = '<span class="placeholder-text">Click a demo scenario above to begin streaming...</span>';
  $("controllerCards").innerHTML = '<div class="empty-state">Awaiting speech chunks...</div>';
  $("subqueries").innerHTML = '<div class="empty-state">No queries generated yet.</div>';
  $("evidence").innerHTML = '<div class="empty-state">No evidence retrieved yet.</div>';
  $("answer").innerHTML = '<div class="empty-state">Waiting for answer generation...</div>';
  $("versions").innerHTML = '';
  $("events").innerHTML = '';
  $("timeline").innerHTML = '<div class="empty-state">Timeline will appear once the turn starts.</div>';
  
  $("metricClaims").textContent = '-';
  $("metricFabricated").textContent = '-';
  $("metricAbstain").textContent = 'N/A';
  $("unsupportedList").innerHTML = '';
  $("versionBadge").style.display = 'none';
  $("suppression").style.display = 'none';
  
  lastClaims = [];
}

// Cite button HTML
function citeButtons(ids) {
  return [...new Set(ids)].map((c) => `<button class="cite-btn" data-chunk="${esc(c)}">${esc(sec(c))}</button>`).join("");
}

// Telemetry events
function addTelemetry(t, type, desc) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="e-time">${t.toFixed(2)}s</span><span class="e-type">${esc(type)}</span><span class="e-desc">${desc}</span>`;
  $("events").appendChild(li);
  li.scrollIntoView({ block: "nearest" });
}

// Timeline Draw
function drawTimeline() {
  if (!turn) return;
  const ts = [turn.end, ...turn.chunks.map((c) => c.t), ...turn.decisions.map((d) => d.t),
    ...turn.retrievals.map((r) => r.t1 ?? r.t0), turn.firstToken ?? 0];
  const max = Math.max(...ts) * 1.08 + 0.2;
  const x = (t) => `${(100 * t) / max}%`;
  
  const lanes = [["Speech", 0], ["Controller", 30], ["Retrieval", 60], ["Answer", 90]];
  let h = lanes.map(([n, y]) => `<div class="tl-lane-label" style="top:${y+2}px">${n}</div><div class="tl-lane" style="top:${y}px"></div>`).join("");
  
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
     h += inner(90, `<div style="position:absolute;left:${x(turn.firstToken)};color:var(--accent);top:0;font-size:10px">● first token</div>`);
  }
  
  if (turn.utterEnd != null) {
    h += `<div style="position:absolute;left:90px;right:10px;top:0;bottom:0;pointer-events:none"><div class="tl-endline" style="left:${x(turn.utterEnd)}"></div><div class="tl-endlabel" style="left:${x(turn.utterEnd)}">Utterance End (${turn.utterEnd.toFixed(2)}s)</div></div>`;
  }
  
  $("timeline").innerHTML = h;
}

// Render Events
function render(ev) {
  const t = ev.t;
  switch (ev.type) {
    case "TURN_STARTED":
      turn = { end: ev.scheduled_end_t, chunks: [], decisions: [], retrievals: [], utterEnd: null, firstToken: null, suppressed: false, refinement: false };
      $("liveIndicator").className = "live-badge listening";
      $("liveIndicator").textContent = "● LISTENING";
      $("transcript").innerHTML = "";
      $("controllerCards").innerHTML = "";
      addTelemetry(t, ev.type, `turn started · v${ev.answer_version ?? 0}`);
      break;
      
    case "TRANSCRIPT_CHUNK":
      turn.chunks.push({ t, text: ev.text });
      $("transcript").insertAdjacentHTML("beforeend", `<span class="t-chunk"> ${esc(ev.text)}</span>`);
      addTelemetry(t, ev.type, `“${esc(ev.text)}”`);
      break;
      
    case "RETRIEVAL_DECISION":
      if (!ev.final) turn.decisions.push({ t, action: ev.action, reason: ev.reason });
      
      const card = document.createElement("div");
      card.className = `ctrl-card ${ev.action}`;
      card.innerHTML = `<div class="ctrl-header"><span>${ev.action}</span><span class="ctrl-time">${t.toFixed(2)}s</span></div><div class="ctrl-reason">${esc(ev.reason)}</div>`;
      if ($("controllerCards").querySelector('.empty-state')) $("controllerCards").innerHTML = "";
      $("controllerCards").appendChild(card);
      card.scrollIntoView({ behavior: "smooth", block: "end" });
      
      addTelemetry(t, ev.type, `action=${ev.action} reason=${esc(ev.reason)}`);
      break;
      
    case "QUERY_CREATED":
      addTelemetry(t, ev.type, `id=${esc(ev.sub_query_id)} text=“${esc(ev.query)}”`);
      break;
      
    case "RETRIEVAL_STARTED":
      turn.retrievals.push({ t0: t, t1: null, ids: ev.sub_query_ids, prov: ev.provisional });
      $("liveIndicator").className = "live-badge processing";
      $("liveIndicator").textContent = "● PROCESSING";
      addTelemetry(t, ev.type, `ids=${ev.sub_query_ids.join(",")}`);
      break;
      
    case "RETRIEVAL_COMPLETED":
      if (ev.batch) {
        const r = turn.retrievals.findLast((r) => r.t1 == null);
        if (r) r.t1 = t;
      } else {
        addTelemetry(t, ev.type, `id=${esc(ev.sub_query_id)} ms=${ev.retrieval_ms+ev.rerank_ms} top=${ev.top_chunks.length}`);
      }
      break;
      
    case "UTTERANCE_END":
      turn.utterEnd = t;
      $("liveIndicator").textContent = "● PROCESSING (SPEECH ENDED)";
      addTelemetry(t, ev.type, "user stopped speaking");
      break;
      
    case "DECOMPOSITION":
      if (ev.provisional) break;
      if (ev.refinement) turn.refinement = true;
      if ($("subqueries").querySelector('.empty-state')) $("subqueries").innerHTML = "";
      
      $("subqueries").innerHTML = ev.sub_queries.map((q) => `
        <div class="query-card">
          <div class="q-id">${esc(q.id)}</div>
          <div class="q-text">“${esc(q.text)}”</div>
          <div class="q-meta">Intent: ${esc(q.intent)}${q.carried_context.length ? ` · Carried Context: ${esc(q.carried_context.join(", "))}` : ""}</div>
        </div>
      `).join("");
      addTelemetry(t, ev.type, `queries=${ev.sub_queries.length}`);
      break;
      
    case "EVIDENCE_FUSED":
      if ($("evidence").querySelector('.empty-state')) $("evidence").innerHTML = "";
      
      $("evidence").innerHTML = ev.evidence.map((e) => `
        <div class="ev-card">
          <div class="ev-header">
            <span><strong>${esc(sec(e.chunk_id))}</strong></span>
            <span>Sub-queries: ${e.sub_query_ids.join(", ")} ${e.signals?.rerank !== undefined ? `(Rerank: ${e.signals.rerank})` : ""}</span>
          </div>
          <div class="ev-text">"..." (Excerpt fetched on demand)</div>
        </div>
      `).join("");
      addTelemetry(t, ev.type, `evidence_items=${ev.evidence.length}`);
      break;
      
    case "RETRIEVAL_SUPPRESSED":
      turn.suppressed = true;
      $("suppression").style.display = "block";
      $("suppression").innerHTML = `<strong>RETRIEVAL SUPPRESSED:</strong> ${esc(ev.reason)}`;
      addTelemetry(t, ev.type, esc(ev.reason));
      break;
      
    case "ANSWER_DELTA":
      if (turn.firstToken == null) {
        turn.firstToken = t;
        $("liveIndicator").className = "live-badge listening"; // change color
        $("liveIndicator").style.color = "var(--ret)";
        $("liveIndicator").textContent = "● ANSWERING";
      }
      break;
      
    case "CITATION_VALIDATED":
      $("metricClaims").textContent = `${ev.num_supported}/${ev.num_claims}`;
      $("metricFabricated").textContent = ev.fabricated_citations.length;
      $("unsupportedList").innerHTML = ev.unsupported_claims.map((u) => `
        <div class="unsupported-item">Removed: ${esc(u.claim)} (${esc(u.reason)})</div>
      `).join("");
      addTelemetry(t, ev.type, `supported=${ev.num_supported}/${ev.num_claims}`);
      break;
      
    case "ANSWER_VERSION_UPDATED":
      const live = ev.claims.filter((c) => c.supported);
      $("versionBadge").style.display = "inline-block";
      $("versionBadge").textContent = `v${ev.answer_version}`;
      
      $("answer").innerHTML = live.map((c) => {
        let cls = "";
        if (c.status === "retained") cls = "retained";
        if (c.status === "added" && ev.answer_version > 1 && turn.refinement) cls = "added";
        if (c.status === "removed") cls = "removed";
        return `<span class="claim ${cls}">${esc(c.text)}${citeButtons(c.citations)}</span>`;
      }).join("") || '<span class="empty-state">Insufficient evidence in corpus.</span>';
      
      $("versions").insertAdjacentHTML("afterbegin", `
        <div class="v-hist-item"><strong>v${ev.answer_version}</strong>: ${ev.change_log.map(esc).join("; ")}</div>
      `);
      addTelemetry(t, ev.type, `v${ev.answer_version} updated`);
      break;
      
    case "FINAL_RESPONSE":
      if (ev.suppressed) {
        $("answer").innerHTML = ev.answer.split("\n").map(l => `<span class="claim">${esc(l)}</span>`).join("");
      }
      if (ev.uncertainty?.length) {
         $("metricAbstain").textContent = "ABSTAINED";
         $("metricAbstain").style.color = "var(--wait)";
      } else {
         $("metricAbstain").textContent = "N/A";
         $("metricAbstain").style.color = "var(--text-muted)";
      }
      $("liveIndicator").textContent = "● COMPLETE";
      $("liveIndicator").style.color = "var(--text-muted)";
      $("liveIndicator").className = "live-badge";
      addTelemetry(t, ev.type, "done");
      break;
      
    case "ERROR":
      $("liveIndicator").textContent = "● ERROR";
      $("liveIndicator").style.color = "var(--bad)";
      addTelemetry(t, ev.type, esc(ev.message));
      break;
  }
  if (turn) drawTimeline();
}

// Turn execution
async function runTurn(chunks, endT) {
  if (busy) return;
  if (!sessionId) await newSession();
  busy = true;
  document.querySelectorAll("button").forEach((b) => (b.disabled = true));
  addTelemetry(0, "UI", "── new turn ──");
  
  try {
    const res = await fetch(`/api/sessions/${sessionId}/turns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chunks, end_t: endT, speed: parseFloat($("speed").value), system: $("system").value }),
    });
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
    busy = false;
    document.querySelectorAll("button").forEach((b) => (b.disabled = false));
  }
}

// Initialization
async function loadScenarios() {
  try {
    const sc = await (await fetch("/api/scenarios")).json();
    Object.entries(sc).forEach(([key, s], i) => {
      const b = document.createElement("button");
      b.innerHTML = `<b>${i + 1}</b>${esc(s.label || s.title)}`;
      b.title = s.title;
      b.onclick = async () => {
        await newSession();
        for (const t of s.turns) await runTurn(t.chunks, t.end_t);
      };
      $("scenarioButtons").appendChild(b);
    });
  } catch (e) {
    console.error("Failed to load scenarios:", e);
  }
}

// Handlers
$("customForm").onsubmit = (e) => {
  e.preventDefault();
  const parts = $("customText").value.split("|").map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return;
  let t = 0;
  const chunks = parts.map((text) => { const c = { t: +t.toFixed(2), text }; t += text.split(/\s+/).length / 2.5; return c; });
  $("customText").value = "";
  runTurn(chunks, +(t + 0.5).toFixed(2));
};

document.addEventListener("click", async (e) => {
  const id = e.target.dataset && e.target.dataset.chunk;
  if (!id) return;
  try {
    const c = await (await fetch(`/api/chunks/${encodeURIComponent(id)}`)).json();
    $("chunkTitle").textContent = `${c.document_id} §${c.section_id} — ${c.section_title}`;
    $("chunkMeta").textContent = `${c.source_title} · ${c.source_file} lines ${c.line_start}-${c.line_end}`;
    $("chunkText").textContent = c.text;
    $("chunkDialog").showModal();
  } catch(err) {
    console.error("Failed to fetch chunk:", err);
  }
});

$("newSession").onclick = newSession;

// Start
loadScenarios();
