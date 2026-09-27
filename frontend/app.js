// Streaming Live RAG dashboard: renders the SSE event stream of each turn.
const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;
let turn = null;        // per-turn state for the timeline + proof banner
let lastClaims = [];    // previous answer version's claims (for the diff)

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sec = (id) => id.split(":").slice(0, 2).join(" §");

async function newSession() {
  if (sessionId) fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
  const r = await fetch("/api/sessions", { method: "POST" });
  sessionId = (await r.json()).session_id;
  $("telemetryLink").href = `/api/sessions/${sessionId}/telemetry`;
  for (const id of ["events", "subqueries", "evidence", "answer", "uncertainty", "grounding", "versions", "metrics"]) $(id).innerHTML = "";
  $("versionBadge").textContent = "";
  lastClaims = [];
  setProof("idle", `New session ${sessionId}. Memory is session-only and dropped when the session ends.`);
}

function setProof(kind, text, detail = "") {
  $("proof").className = `proof ${kind}`;
  $("proof").innerHTML = esc(text) + (detail ? `<span class="detail">${esc(detail)}</span>` : "");
}

function citeButtons(ids) {
  return [...new Set(ids)].map((c) => `<button class="cite" data-chunk="${esc(c)}">${esc(sec(c))}</button>`).join("");
}

function addEvent(t, badge, html) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="t">${t.toFixed(2)}s</span><div>${badge ? `<span class="badge ${badge}">${badge}</span>` : ""}${html}</div>`;
  $("events").appendChild(li);
  li.scrollIntoView({ block: "nearest" });
}

// ---------------------------------------------------------------- timeline (swim lanes)
function drawTimeline() {
  if (!turn) return;
  const ts = [turn.end, ...turn.chunks.map((c) => c.t), ...turn.decisions.map((d) => d.t),
    ...turn.retrievals.map((r) => r.t1 ?? r.t0), turn.firstToken ?? 0];
  const max = Math.max(...ts) * 1.08 + 0.2;
  const x = (t) => `${(100 * t) / max}%`;
  const lanes = [["Speech", 8], ["Controller", 34], ["Retrieval", 60], ["Answer", 96]];
  let h = lanes.map(([n, y]) => `<div class="lane-label" style="top:${y + 4}px">${n}</div><div class="lane" style="top:${y}px"></div>`).join("");
  const inner = (y, content) => `<div class="lane" style="top:${y}px;border:none">${content}</div>`;
  const speechEnd = turn.utterEnd ?? turn.chunks.at(-1)?.t ?? 0;
  let s = turn.chunks.length ? `<div class="bar speech" style="left:0;width:${x(speechEnd)}"></div>` : "";
  s += turn.chunks.map((c) => `<div class="tick" style="left:${x(c.t)}" title="${esc(c.text)}"></div>`).join("");
  h += inner(8, s);
  h += inner(34, turn.decisions.map((d) => `<div class="cdot ${d.action}" style="left:${x(d.t)}" title="${d.action}: ${esc(d.reason)}"></div>`).join(""));
  h += inner(60, turn.retrievals.map((r) => {
    const w = Math.max(0.6, (100 * ((r.t1 ?? r.t0 + 0.05) - r.t0)) / max);
    return `<div class="bar ret ${r.prov ? "prov" : ""}" style="left:${x(r.t0)};width:${w}%" title="${r.prov ? "provisional" : "final"} ${r.ids.join(",")}"></div>`;
  }).join(""));
  if (turn.firstToken != null) h += inner(96, `<div class="anslabel" style="left:${x(turn.firstToken)}">● first answer token</div>`);
  if (turn.utterEnd != null) {
    h += `<div class="lane" style="top:0;height:118px;border:none"><div class="endline" style="left:${x(turn.utterEnd)}"></div></div>`;
    h += `<div class="axis"><span style="left:${x(turn.utterEnd)};color:var(--bad)">utterance end ${turn.utterEnd.toFixed(2)}s</span></div>`;
  }
  $("timeline").innerHTML = h;
}

// ---------------------------------------------------------------- event rendering
function render(ev) {
  const t = ev.t;
  switch (ev.type) {
    case "TURN_STARTED":
      turn = { end: ev.scheduled_end_t, chunks: [], decisions: [], retrievals: [], utterEnd: null, firstToken: null,
               suppressed: false, refinement: false, provisionalBeforeEnd: 0 };
      addEvent(t, "INFO", `turn started · session answer so far: v${ev.answer_version ?? 0}`);
      setProof("idle", "Listening… watch for retrieval to start before the utterance ends.");
      break;
    case "TRANSCRIPT_CHUNK":
      turn.chunks.push({ t, text: ev.text });
      addEvent(t, null, `<span class="quote">“${esc(ev.text)}”</span>`);
      break;
    case "RETRIEVAL_DECISION":
      if (!ev.final) turn.decisions.push({ t, action: ev.action, reason: ev.reason });
      addEvent(t, ev.action, `${ev.final ? "<b>[final]</b> " : ""}intent=${esc(ev.intent)} <div class="reason">${esc(ev.reason)}</div>`);
      break;
    case "QUERY_CREATED":
      addEvent(t, "RETRIEVE", `${ev.provisional ? "<b>early</b> " : ""}query ${esc(ev.sub_query_id)}: “${esc(ev.query)}”`);
      break;
    case "RETRIEVAL_STARTED":
      turn.retrievals.push({ t0: t, t1: null, ids: ev.sub_query_ids, prov: ev.provisional });
      if (turn.utterEnd == null) turn.provisionalBeforeEnd += 1;
      break;
    case "RETRIEVAL_COMPLETED":
      if (ev.batch) {
        const r = turn.retrievals.findLast((r) => r.t1 == null);
        if (r) r.t1 = t;
      } else {
        addEvent(t, "INFO", `retrieved ${esc(ev.sub_query_id)} (${ev.mode}${ev.reranker !== "none" ? " + rerank" : ""}) ${(ev.retrieval_ms + ev.rerank_ms).toFixed(0)} ms → ${ev.top_chunks.map(sec).join(", ")}`);
      }
      break;
    case "RETRIEVAL_REUSED":
      addEvent(t, "INFO", `${esc(ev.sub_query_id)} reuses early retrieval “${esc(ev.provisional_query)}” (ready at ${ev.retrieved_at_t.toFixed(2)}s)`);
      break;
    case "SYNTHESIS_PREPARED":
      addEvent(t, "INFO", esc(ev.note));
      break;
    case "UTTERANCE_END":
      turn.utterEnd = t;
      addEvent(t, "INFO", "<b>utterance end</b>");
      break;
    case "DECOMPOSITION":
      if (ev.provisional) break;
      if (ev.refinement) turn.refinement = true;
      $("subqueries").classList.remove("muted");
      $("subqueries").innerHTML =
        `<div class="small">${ev.refinement ? "delta queries for the late detail" : ev.is_multi_intent ? "multi-intent: one utterance → several searches" : "single intent"} · ${ev.ms} ms</div>` +
        ev.sub_queries.map((q) => `<div class="item"><b>${esc(q.id)}</b> “${esc(q.text)}”<div class="reason">intent: ${esc(q.intent)}${q.carried_context.length ? ` · carried: ${esc(q.carried_context.join(", "))}` : ""}</div></div>`).join("");
      break;
    case "EVIDENCE_FUSED": {
      $("evidence").classList.remove("muted");
      const flags = [];
      ev.duplicates.forEach((d) => flags.push(`duplicate dropped: ${sec(d.dropped)} (same text as ${sec(d.kept)})`));
      ev.superseded.forEach((s) => flags.push(s.dropped ? `superseded version dropped: ${sec(s.dropped)} → ${s.superseded_by}` : `superseded, kept with warning: ${sec(s.kept_with_warning)}`));
      ev.conflicts.forEach((c) => flags.push(`possible conflict: ${sec(c.a)} vs ${sec(c.b)}`));
      $("evidence").innerHTML =
        ev.evidence.map((e) => `<div class="item">${citeButtons([e.chunk_id])} <span class="reason">for ${e.sub_query_ids.join(", ")}${e.signals && e.signals.rerank !== undefined ? ` · rerank ${e.signals.rerank}` : ""}</span></div>`).join("") +
        flags.map((f) => `<div class="flag">${esc(f)}</div>`).join("");
      break;
    }
    case "RETRIEVAL_SUPPRESSED":
      turn.suppressed = true;
      addEvent(t, "SUPPRESS", `no corpus search · ${esc(ev.reason)}`);
      break;
    case "ANSWER_DELTA":
      if (turn.firstToken == null) turn.firstToken = t;
      break;
    case "CITATION_VALIDATED":
      $("grounding").innerHTML = `Grounding: ${ev.num_supported}/${ev.num_claims} claims supported by their cited text · fabricated citation ids: ${ev.fabricated_citations.length}` +
        ev.unsupported_claims.map((u) => `<div class="flag">removed: ${esc(u.claim)} (${esc(u.reason)})</div>`).join("");
      break;
    case "ANSWER_VERSION_UPDATED": {
      $("answer").classList.remove("muted");
      const live = ev.claims.filter((c) => c.supported);
      $("answer").innerHTML = live.map((c) => `<p class="claim-${c.status}">${esc(c.text)} ${citeButtons(c.citations)}${c.status === "retained" ? ' <span class="small">(kept from previous version)</span>' : c.status === "added" && ev.answer_version > 1 && turn.refinement ? ' <span class="small">(new)</span>' : ""}</p>`).join("")
        || "<p>The provided corpus does not contain enough information to verify this.</p>";
      $("versionBadge").textContent = `v${ev.answer_version}`;
      $("versions").classList.remove("muted");
      $("versions").insertAdjacentHTML("afterbegin", `<div class="item"><b>v${ev.answer_version}</b> ${ev.change_log.map(esc).join("<br>")}</div>`);
      turn.version = ev.answer_version;
      turn.retained = live.filter((c) => c.status === "retained").length;
      turn.added = live.filter((c) => c.status === "added").length;
      lastClaims = live;
      break;
    }
    case "FINAL_RESPONSE":
      if (ev.suppressed) {
        $("answer").classList.remove("muted");
        $("answer").innerHTML = `<p class="small">Reformatted from v${ev.answer_version}, no retrieval:</p>` + ev.answer.split("\n").map((l) => `<p>${esc(l)}</p>`).join("");
      }
      $("uncertainty").innerHTML = (ev.uncertainty || []).map((u) => `<div class="unc">${esc(u)}</div>`).join("");
      addEvent(t, "INFO", `final response · v${ev.answer_version}${ev.suppressed ? " · retrieval suppressed" : ""}`);
      turn.uncertain = (ev.uncertainty || []).length > 0;
      turn.hasCitations = (ev.citations || []).length > 0;
      break;
    case "TURN_SUMMARY":
      summarise(ev);
      break;
    case "ERROR":
      addEvent(t || 0, "ERR", esc(ev.message));
      break;
  }
  if (turn) drawTimeline();
}

function summarise(ev) {
  const lead = ev.retrieval_lead_s;
  const m = [
    ["first retrieval", ev.first_retrieval_t != null ? `${ev.first_retrieval_t.toFixed(2)} s` : "none"],
    ["utterance end", `${ev.utterance_end_t.toFixed(2)} s`],
    ["retrieval lead", lead != null && lead > 0 ? `${lead.toFixed(2)} s before end` : "—"],
    ["time to first token", ev.ttft_s != null ? `${Math.round(ev.ttft_s * 1000)} ms` : "—"],
    ["retrieval calls", `${ev.retrieval_calls_total} (${ev.provisional_calls} early)`],
    ["reused at end", ev.reused_subqueries],
    ["search + rerank CPU", `${(ev.planning_ms_total + ev.retrieval_ms_total + ev.rerank_ms_total).toFixed(0)} ms`],
    ["LLM tokens / cost", `${Object.values(ev.llm_usage || {}).reduce((a, b) => a + b, 0)} / $0`],
  ];
  $("metrics").classList.remove("muted");
  $("metrics").innerHTML = m.map(([k, v]) => `<div class="metric">${k}<b>${esc(v)}</b></div>`).join("");

  if (ev.suppressed) {
    setProof("sup", "Retrieval SUPPRESSED: no corpus search for this turn.",
      ev.intent === "presentation" ? "Presentation-only request: the previous answer was reshaped from session memory; no new citations are possible." : "Nothing to look up.");
  } else if (ev.intent === "refinement") {
    setProof("good", `Late detail → answer v${ev.answer_version}: ${turn.retained ?? 0} claims kept, ${turn.added ?? 0} added, 0 prior sub-queries re-searched.`,
      `${ev.retrieval_calls_total} delta retrieval(s)${lead > 0 ? `, started ${lead.toFixed(2)} s before the detail was finished` : ""}. Turn-based RAG would restart the whole search.`);
  } else if (ev.early_retrieval) {
    setProof("good", `Retrieval started ${lead.toFixed(2)} s BEFORE you finished speaking (${ev.first_retrieval_t.toFixed(2)} s < ${ev.utterance_end_t.toFixed(2)} s).`,
      `${ev.reused_subqueries} of ${ev.sub_queries.length} sub-queries were already retrieved at utterance end · first answer ${Math.round((ev.ttft_s ?? 0) * 1000)} ms after you stopped${turn.uncertain ? " · part of the request could not be verified from the corpus (see answer)" : ""}.`);
  } else if (ev.intent === "n/a") {
    setProof("warn", `Baseline: waited for the utterance to end (${ev.utterance_end_t.toFixed(2)} s), then searched once with the whole sentence.`,
      "Switch System to Streaming Live RAG and run the same demo to compare.");
  } else {
    setProof("warn", "Retrieval ran at utterance end (the partial transcript was never specific enough to search early).",
      turn.uncertain ? "Part of the request could not be verified from the corpus." : "");
  }
}

// ---------------------------------------------------------------- running turns
async function runTurn(chunks, endT) {
  if (busy) return;
  if (!sessionId) await newSession();
  busy = true;
  document.querySelectorAll("button").forEach((b) => (b.disabled = true));
  $("events").insertAdjacentHTML("beforeend", '<li><span></span><div class="small">── new turn ──</div></li>');
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

async function loadScenarios() {
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
  try {
    const h = await (await fetch("/api/health")).json();
    const c = h.corpus || {};
    $("corpusNote").textContent = `Corpus: ${c.num_documents} documents / ${c.num_chunks} chunks` +
      (c.synthetic ? " · DEVELOPMENT / DEMONSTRATION corpus (synthetic, not the official Theme 4 corpus)" : "") +
      ` · reranker: ${h.reranker} · sufficiency gate: ${h.sufficiency_gate?.status ?? "n/a"}`;
  } catch (_) { /* health is informational */ }
}

$("customForm").onsubmit = (e) => {
  e.preventDefault();
  const parts = $("customText").value.split("|").map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return;
  let t = 0;
  const chunks = parts.map((text) => { const c = { t: +t.toFixed(2), text }; t += text.split(/\s+/).length / 2.5; return c; });
  $("customText").value = "";
  runTurn(chunks, +(t + 0.5).toFixed(2)); // 150 wpm + 0.5 s end-pointing, as in the benchmark
};

document.addEventListener("click", async (e) => {
  const id = e.target.dataset && e.target.dataset.chunk;
  if (!id) return;
  const c = await (await fetch(`/api/chunks/${encodeURIComponent(id)}`)).json();
  $("chunkTitle").textContent = `${c.document_id} §${c.section_id} — ${c.section_title}`;
  $("chunkMeta").textContent = `${c.source_title} · ${c.source_file} lines ${c.line_start}-${c.line_end}`;
  $("chunkText").textContent = c.text;
  $("chunkDialog").showModal();
});

$("newSession").onclick = newSession;
loadScenarios();
