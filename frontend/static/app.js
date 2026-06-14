/* Aegis war-room UI. No build step: React UMD + htm tagged templates.
   It only renders the room transcript streamed from /stream — all incident
   logic lives in the Python orchestrator. */
const { useState, useEffect, useRef } = React;
const html = htm.bind(React.createElement);

const LANES = {
  "@observer":      { var: "--observer",      label: "OBSERVER" },
  "@diagnostician": { var: "--diagnostician", label: "DIAGNOSTICIAN" },
  "@remediator":    { var: "--remediator",    label: "REMEDIATOR" },
  "@validator":     { var: "--validator",     label: "VALIDATOR" },
  "@commander":     { var: "--commander",     label: "COMMANDER" },
};
const ORDER = Object.keys(LANES);

const INTENT_TAG = {
  signal: "signal",
  hypothesis: "hypothesis",
  remediation_proposal: "remediation",
  validation_result: "validation",
  approval_request: "approval",
  decision: "decision",
  postmortem: "postmortem",
};

const accent = (sender) => `var(${(LANES[sender] || {}).var || "--line"})`;
const usd = (n) => "$" + Math.round(n).toLocaleString();

function Facts({ m }) {
  const p = m.payload || {};
  const pills = [];
  if (m.intent === "signal") {
    if (p.severity) pills.push(["warn", p.severity]);
    (p.anomalies || []).forEach((a) => pills.push(["", a]));
  } else if (m.intent === "hypothesis") {
    if (p.confidence != null) pills.push(["", `confidence ${(p.confidence * 100).toFixed(0)}%`]);
    if (p.suspected_change) pills.push(["", p.suspected_change]);
  } else if (m.intent === "remediation_proposal") {
    if (p.action) pills.push(["", p.action]);
    if (p.attempt) pills.push(["", `attempt ${p.attempt}`]);
    pills.push([p.reversible ? "" : "warn", p.reversible ? "reversible" : "irreversible — needs human"]);
  } else if (m.intent === "validation_result") {
    if (p.projected_p99_ms != null) pills.push(["", `p99 ${Math.round(p.projected_p99_ms)}ms / slo ${Math.round(p.slo_p99_ms)}ms`]);
    if (p.projected_error_rate != null) pills.push(["", `err ${(p.projected_error_rate * 100).toFixed(2)}% / slo ${(p.slo_error_rate * 100).toFixed(2)}%`]);
  } else if (m.intent === "decision") {
    if (p.approved_by) pills.push(["", `approved by ${p.approved_by}`]);
    if (p.averted_cost_usd != null) pills.push(["", `averted ${usd(p.averted_cost_usd)}`]);
  }
  if (!pills.length) return null;
  return html`<div class="facts">
    ${pills.map(([cls, txt], i) => html`<span key=${i} class=${"pill " + cls}>${txt}</span>`)}
  </div>`;
}

function Card({ m }) {
  const lane = LANES[m.sender] || { label: m.sender };
  const p = m.payload || {};
  const isVal = m.intent === "validation_result";
  const passed = isVal && p.passed;
  const rejected = isVal && !p.passed;
  const cls = "card" + (passed ? " pass" : rejected ? " reject" : "");

  return html`<div class=${cls} style=${{ "--accent": accent(m.sender) }}>
    <div class="head">
      <span class="who">${lane.label}</span>
      <span class="tag">${INTENT_TAG[m.intent] || m.intent}</span>
      ${isVal && html`<span class=${"badge " + (passed ? "pass" : "reject")}>${passed ? "PASS ✓" : "REJECTED ✕"}</span>`}
      ${(m.mentions || []).length ? html`<span class="ment">${m.mentions.join(" ")}</span>` : null}
      <span class="seq">#${m.seq}</span>
    </div>
    <p class="text">${m.text}</p>
    <${Facts} m=${m} />
    ${(isVal && (p.trace || []).length) ? html`<div class="trace">
      ${p.trace.map((l, i) => html`<div key=${i} class="line">${l}</div>`)}
    </div>` : null}
    ${(m.intent === "postmortem") ? html`<div class="trace">
      ${p.root_cause ? html`<div class="line">root cause: ${p.root_cause}</div>` : null}
      ${p.cost_summary ? html`<div class="line">${p.cost_summary}</div>` : null}
    </div>
    ${(p.follow_ups || []).length ? html`<div class="followups">
      ${p.follow_ups.map((f, i) => html`<div key=${i} class="fu">${f}</div>`)}
    </div>` : null}` : null}
  </div>`;
}

function Verdict({ v }) {
  if (!v) return null;
  if (!v.resolved) {
    return html`<div class="verdict unresolved">
      <div class="vhead">VERDICT — NOT AUTO-RESOLVED · ESCALATED TO HUMAN</div>
    </div>`;
  }
  const cells = [
    ["Resolved by", v.action],
    ["Approved by", v.approved_by],
    ["Attempts", `${v.attempts} (1 rejected, 1 passed)`],
    ["MTTR (modeled)", `${(v.mttr_seconds / 60).toFixed(1)} min`],
    ["Agent latency", `${v.decision_latency_ms.toFixed(1)} ms`],
    ["Downtime cost", usd(v.downtime_cost_usd)],
    ["Remediation cost", usd(v.remediation_cost_usd)],
  ];
  return html`<div class="verdict">
    <div class="vhead">VERDICT — INCIDENT RESOLVED</div>
    <div class="grid">
      ${cells.map(([k, val], i) => html`<div key=${i} class="cell"><div class="k">${k}</div><div class="v">${val}</div></div>`)}
      <div class="cell"><div class="k">Cost AVERTED vs ~42m manual</div><div class="v big">${usd(v.averted_cost_usd)}</div></div>
    </div>
  </div>`;
}

function App() {
  const [msgs, setMsgs] = useState([]);
  const [verdict, setVerdict] = useState(null);
  const [running, setRunning] = useState(false);
  const [pace, setPace] = useState("0.7");
  const esRef = useRef(null);
  const feedRef = useRef(null);

  useEffect(() => {
    if (feedRef.current) window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }, [msgs, verdict]);

  function run() {
    if (esRef.current) esRef.current.close();
    setMsgs([]); setVerdict(null); setRunning(true);
    const es = new EventSource(`/stream?pace=${pace}`);
    esRef.current = es;
    es.addEventListener("message", (e) => setMsgs((prev) => [...prev, JSON.parse(e.data)]));
    es.addEventListener("verdict", (e) => setVerdict(JSON.parse(e.data)));
    es.addEventListener("error", (e) => { try { setVerdict(JSON.parse(e.data)); } catch (_) {} });
    es.addEventListener("done", () => { setRunning(false); es.close(); });
  }

  const activeSender = running && msgs.length ? msgs[msgs.length - 1].sender : null;

  return html`<div>
    <header class="top">
      <div class="brand">
        <h1>AEGIS // BAND WAR ROOM</h1>
        <div class="sub">INC-2041 · checkout-api · us-east-1</div>
      </div>
      <div class="spacer"></div>
      <div class="ctrl">
        <span class="status"><span class=${"dot" + (running ? " live" : "")}></span>${running ? "live" : verdict ? "resolved" : "idle"}</span>
        <select value=${pace} onChange=${(e) => setPace(e.target.value)} disabled=${running}>
          <option value="1.1">Slow</option>
          <option value="0.7">Normal</option>
          <option value="0.3">Fast</option>
          <option value="0">Instant</option>
        </select>
        <button class="run" onClick=${run} disabled=${running}>${verdict || msgs.length ? "Replay" : "Run incident"}</button>
      </div>
    </header>

    <div class="lanes">
      ${ORDER.map((s) => html`<div key=${s} class=${"lane-chip" + (s === activeSender ? " active" : "")}>
        <span class="swatch" style=${{ background: `var(${LANES[s].var})` }}></span>${LANES[s].label}
      </div>`)}
    </div>

    <div class="feed" ref=${feedRef}>
      ${msgs.length === 0
        ? html`<div class="empty">Press <b>Run incident</b> to open the war room. Five agents coordinate over the Band bus — watch the validator reject the first fix, then pass the second.</div>`
        : msgs.map((m) => html`<${Card} key=${m.seq} m=${m} />`)}
    </div>

    <${Verdict} v=${verdict} />
  </div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
