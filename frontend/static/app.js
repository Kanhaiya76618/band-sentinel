/* Aegis platform UI. No build step: React UMD + htm tagged templates.
   A hash-routed SPA shell (Dashboard / Resolve / Jobs / History / Integrations /
   Settings). The Resolve section reuses the original war-room transcript UI —
   all incident logic still lives in the Python orchestrator and streams over
   /stream. Other sections read the platform API (/api/dashboard, ...). */
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
const usd = (n) => "$" + Math.round(n || 0).toLocaleString();

function timeAgo(epochSeconds) {
  const s = Math.max(0, Date.now() / 1000 - epochSeconds);
  if (s < 60) return Math.floor(s) + "s ago";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}

// ── Navigation ──────────────────────────────────────────────────────── //
const NAV = [
  { id: "dashboard",    label: "Dashboard",    ic: "▦" },
  { id: "resolve",      label: "Resolve",      ic: "⚡" },
  { id: "jobs",         label: "Jobs",         ic: "✦" },
  { id: "history",      label: "History",      ic: "≡" },
  { id: "analytics",    label: "Analytics",    ic: "▤" },
  { id: "integrations", label: "Integrations", ic: "⚙" },
  { id: "settings",     label: "Settings",     ic: "⚒" },
];

function useRoute() {
  const get = () => (window.location.hash || "#dashboard").slice(1).split("?")[0];
  const [route, setRoute] = useState(get());
  useEffect(() => {
    const on = () => setRoute(get());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

function Sidebar({ route }) {
  return html`<aside class="sidebar">
    <div class="brand">
      <h1>AEGIS</h1>
      <div class="sub">MULTI-AGENT PLATFORM</div>
    </div>
    <nav class="nav">
      ${NAV.map((n) => html`<a key=${n.id} href=${"#" + n.id} class=${route === n.id ? "active" : ""}>
        <span class="ic">${n.ic}</span><span>${n.label}</span>
        ${n.soon ? html`<span class="badge-soon">${n.soon}</span>` : null}
      </a>`)}
    </nav>
    <div class="foot">
      Coordination layer<br/>
      <span class="mode">● Band bus (local)</span>
    </div>
  </aside>`;
}

// ── Dashboard ───────────────────────────────────────────────────────── //
function Dashboard() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    fetch("/api/dashboard")
      .then((r) => r.json())
      .then((d) => { if (live) setData(d); })
      .catch((e) => { if (live) setErr(String(e)); });
    return () => { live = false; };
  }, []);

  if (err) return html`<div class="empty">Failed to load dashboard: ${err}</div>`;
  if (!data) return html`<div class="empty">Loading…</div>`;

  const c = data.cards;
  const cards = [
    { k: "Open incidents", v: c.open_incidents },
    { k: "MTTR (avg)", v: c.mttr_avg_seconds ? (c.mttr_avg_seconds / 60).toFixed(1) + "m" : "—" },
    { k: "Cost averted", v: usd(c.cost_averted_usd), good: true, accent: true },
    { k: "Resolved (7d)", v: c.incidents_resolved_7d },
    { k: "Jobs found", v: c.jobs_found },
    { k: "Applications sent", v: c.applications_sent },
    { k: "Resumes tailored", v: c.resumes_tailored },
  ];

  return html`<div>
    <div class="quick">
      <button class="primary" onClick=${() => (window.location.hash = "#resolve")}>⚡ Resolve an incident</button>
      <button class="ghost" onClick=${() => (window.location.hash = "#jobs")}>✦ Find jobs</button>
    </div>

    <div class="cards">
      ${cards.map((s, i) => html`<div key=${i} class=${"stat" + (s.accent ? " accent" : "")}>
        <div class="k">${s.k}</div>
        <div class=${"v" + (s.good ? " good" : "")}>${s.v}</div>
      </div>`)}
    </div>

    <div class="two-col">
      <div class="block">
        <h3>Recent activity</h3>
        ${data.activity.length === 0
          ? html`<div class="empty">No runs yet. Resolve an incident or run a job search to populate this feed.</div>`
          : html`<div class="activity">
              ${data.activity.map((a, i) => html`<div key=${i} class="act">
                <span class="ic">${a.kind === "incident" ? "⚡" : "✦"}</span>
                <div class="body">
                  <div class="t">${a.title}</div>
                  <div class="s">${a.subtitle}</div>
                </div>
                <span class=${"chip " + a.status}>${a.status}</span>
                <span class="when">${timeAgo(a.created_at)}</span>
              </div>`)}
            </div>`}
      </div>

      <div class="block">
        <h3>Connected services</h3>
        <${ServiceList} services=${data.services} />
      </div>
    </div>
  </div>`;
}

function ServiceList({ services }) {
  return html`<div class="services">
    ${services.map((s) => html`<div key=${s.key} class="svc">
      <span class=${"dot " + (s.ok ? "ok" : "bad")}></span>
      <span class="label">${s.label}</span>
      <span class="detail">${s.ok ? s.detail : "⚠ " + s.detail}</span>
    </div>`)}
  </div>`;
}

// ── War-room (Resolve) — preserved transcript UI ────────────────────── //
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

function Resolve() {
  const [msgs, setMsgs] = useState([]);
  const [verdict, setVerdict] = useState(null);
  const [email, setEmail] = useState(null);
  const [running, setRunning] = useState(false);
  const [awaiting, setAwaiting] = useState(null); // run_id awaiting approval
  const [pace, setPace] = useState("0.5");
  const [mode, setMode] = useState("demo");
  const [fileName, setFileName] = useState("");
  const [fileText, setFileText] = useState("");
  const [paste, setPaste] = useState("");
  const [svc, setSvc] = useState("checkout-api");
  const [region, setRegion] = useState("us-east-1");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const esRef = useRef(null);
  const feedRef = useRef(null);

  useEffect(() => () => { if (esRef.current) esRef.current.close(); }, []);
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [msgs, verdict, awaiting]);

  function onFile(e) {
    const f = e.target.files[0];
    if (!f) return;
    setFileName(f.name);
    const r = new FileReader();
    r.onload = () => setFileText(r.result);
    r.readAsText(f);
  }

  async function run() {
    if (esRef.current) esRef.current.close();
    setMsgs([]); setVerdict(null); setEmail(null); setAwaiting(null); setErr(""); setNote("");
    const payload = { mode, service: svc, region };
    if (mode === "upload") { payload.content = fileText; payload.filename = fileName; }
    if (mode === "paste") { payload.content = paste; payload.filename = "pasted.log"; }
    let start;
    try {
      const res = await fetch("/api/resolve/start", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      start = await res.json();
      if (!res.ok) { setErr(start.error || "Failed to start run"); return; }
    } catch (e) { setErr(String(e)); return; }
    setNote(start.note || "");
    setRunning(true);
    const es = new EventSource(`/api/resolve/stream?run_id=${start.run_id}&pace=${pace}`);
    esRef.current = es;
    es.addEventListener("message", (e) => setMsgs((p) => [...p, JSON.parse(e.data)]));
    es.addEventListener("await_approval", (e) => setAwaiting(JSON.parse(e.data).run_id));
    es.addEventListener("verdict", (e) => setVerdict(JSON.parse(e.data)));
    es.addEventListener("email", (e) => setEmail(JSON.parse(e.data)));
    es.addEventListener("error", (e) => { try { setErr(JSON.parse(e.data).detail); } catch (_) {} });
    es.addEventListener("done", () => { setRunning(false); setAwaiting(null); es.close(); });
  }

  async function decide(approve) {
    const run_id = awaiting;
    setAwaiting(null);
    await fetch("/api/resolve/decision", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id, approve }),
    });
  }

  const activeSender = running && msgs.length ? msgs[msgs.length - 1].sender : null;
  const started = running || verdict || msgs.length;

  return html`<div>
    <div class="resolve-modes">
      ${[["demo", "Run demo"], ["upload", "Upload telemetry"], ["paste", "Paste artifact"], ["describe", "Describe service"]].map(
        ([m, label]) => html`<button key=${m} class=${"tab" + (mode === m ? " on" : "")} disabled=${running} onClick=${() => setMode(m)}>${label}</button>`
      )}
    </div>

    <div class="block resolve-input">
      ${mode === "demo" ? html`<div class="muted">Runs the deterministic checkout-api SEV1 scenario — five agents coordinate over the Band bus; the validator rejects the first fix, then passes the second.</div>` : null}
      ${mode === "upload" ? html`<div>
        <label class="filebtn">Choose JSON / CSV / log file<input type="file" accept=".json,.csv,.log,.txt" onChange=${onFile} /></label>
        ${fileName ? html`<span class="muted"> ${fileName} (${fileText.length} bytes)</span>` : html`<span class="muted"> needs p99 / error_rate / mem_util columns</span>`}
      </div>` : null}
      ${mode === "paste" ? html`<textarea rows="6" placeholder="Paste JSON points, CSV rows, or log lines with p99=… error_rate=… mem_util=…" value=${paste} onInput=${(e) => setPaste(e.target.value)}></textarea>` : null}
      ${mode === "describe" ? html`<div class="fields">
        <label>Service <input value=${svc} onInput=${(e) => setSvc(e.target.value)} /></label>
        <label>Region <input value=${region} onInput=${(e) => setRegion(e.target.value)} /></label>
        <span class="muted">Generates a realistic incident timeline for this service via the chaos model.</span>
      </div>` : null}
    </div>

    <div class="section-head">
      <div class="status"><span class=${"dot" + (running ? " live" : "")}></span>${running ? "live" : verdict ? (verdict.resolved ? "resolved" : "escalated") : "idle"}</div>
      <div class="spacer"></div>
      <select value=${pace} onChange=${(e) => setPace(e.target.value)} disabled=${running}>
        <option value="1.1">Slow</option>
        <option value="0.5">Normal</option>
        <option value="0.2">Fast</option>
        <option value="0">Instant</option>
      </select>
      <button class="run" onClick=${run} disabled=${running || (mode === "upload" && !fileText) || (mode === "paste" && !paste.trim())}>
        ${started ? "Re-run" : "Run pipeline"}
      </button>
    </div>

    ${note ? html`<div class="muted note">${note}</div>` : null}
    ${err ? html`<div class="empty" style=${{ borderColor: "var(--reject)", color: "var(--reject)" }}>${err}</div>` : null}

    <div class="lanes">
      ${ORDER.map((s) => html`<div key=${s} class=${"lane-chip" + (s === activeSender ? " active" : "")}>
        <span class="swatch" style=${{ background: `var(${LANES[s].var})` }}></span>${LANES[s].label}
      </div>`)}
    </div>

    <div class="feed" ref=${feedRef}>
      ${msgs.length === 0 && !err
        ? html`<div class="empty">Pick a mode and press <b>Run pipeline</b>. The commander will pause for your approval before any irreversible action; on resolution an incident report is emailed.</div>`
        : msgs.map((m) => html`<${Card} key=${m.seq} m=${m} />`)}
      ${awaiting ? html`<div class="approval">
        <div class="ahead">⚠ HUMAN APPROVAL REQUIRED — irreversible action</div>
        <div class="muted">The commander is holding. Approve to execute, or reject to escalate.</div>
        <div class="abtns">
          <button class="run" onClick=${() => decide(true)}>Approve & execute</button>
          <button class="ghost" onClick=${() => decide(false)}>Reject</button>
        </div>
      </div>` : null}
    </div>

    <${Verdict} v=${verdict} />
    ${email ? html`<${EmailStatus} s=${email} />` : null}
  </div>`;
}

function EmailStatus({ s }) {
  const map = {
    sent: ["pass", `✓ Incident report emailed via ${s.provider} to ${(s.to || []).join(", ")}`],
    not_configured: ["warn", `✉ Report NOT sent — ${s.detail}`],
    error: ["warn", `✉ Report send failed — ${s.detail}`],
    skipped: ["", `✉ ${s.detail || "Email skipped."}`],
  };
  const [cls, txt] = map[s.status] || ["", JSON.stringify(s)];
  return html`<div class=${"emailbar " + cls}>${txt}</div>`;
}

// ── Placeholder sections (filled in by later phases) ────────────────── //
function Placeholder({ phase, title, items }) {
  return html`<div class="block placeholder">
    <h3>${title} — arrives in ${phase}</h3>
    <p>This section is scaffolded into the platform shell. ${phase} wires it to real data:</p>
    <ul>${items.map((it, i) => html`<li key=${i}>${it}</li>`)}</ul>
  </div>`;
}

const JOB_LANES = {
  "@observer":  "--observer",
  "@validator": "--validator",
  "@commander": "--commander",
  "@tailor":    "--remediator",
  "@applier":   "--diagnostician",
};
const FIELDS = [
  "Software Engineer", "Data Scientist", "Product Manager", "Consultant",
  "DevOps Engineer", "ML Engineer", "Frontend Engineer", "Backend Engineer",
  "Full-Stack Engineer", "Cybersecurity Analyst", "Cloud Architect",
  "Business Analyst", "UX Designer", "QA Engineer", "Site Reliability Engineer",
];
const dl = (p) => `/api/download?path=${encodeURIComponent(p)}`;

function JobCard({ m }) {
  const p = m.payload || {};
  const acc = `var(${JOB_LANES[m.sender] || "--line"})`;
  return html`<div class="card" style=${{ "--accent": acc }}>
    <div class="head">
      <span class="who">${m.sender.replace("@", "").toUpperCase()}</span>
      <span class="tag">${m.intent.replace("_", " ")}</span>
      ${(m.mentions || []).length ? html`<span class="ment">${m.mentions.join(" ")}</span>` : null}
      <span class="seq">#${m.seq}</span>
    </div>
    <p class="text">${m.text}</p>
    ${m.intent === "search_profile" && (p.skills || []).length ? html`<div class="facts">
      ${(p.skills || []).slice(0, 10).map((s, i) => html`<span key=${i} class="pill">${s}</span>`)}
    </div>` : null}
    ${m.intent === "job_matches" ? html`<div class="matches">
      ${(p.matches || []).map((j, i) => html`<${MatchRow} key=${i} j=${j} />`)}
    </div>` : null}
    ${m.intent === "tailor_result" && p.tailored ? html`<div class="trace">
      <div class="line">added keywords: ${(p.keywords_added || []).join(", ") || "—"}</div>
      <div class="dlrow">${Object.entries(p.files || {}).map(([ext, path]) =>
        html`<a key=${ext} class="dlbtn" href=${dl(path)}>${ext.toUpperCase()}</a>`)}</div>
    </div>` : null}
    ${m.intent === "application" ? html`<div class=${"appbox " + p.status}>
      <span class=${"chip " + (p.status === "submitted" ? "submitted" : "queued")}>${p.status}</span>
      <span class="muted"> via ${p.method} — ${p.detail}</span>
      ${p.apply_url ? html`<div><a class="dlbtn" href=${p.apply_url} target="_blank" rel="noreferrer">Open apply link ↗</a></div>` : null}
    </div>` : null}
  </div>`;
}

function MatchRow({ j }) {
  const pct = Math.round((j.fit_score || 0) * 100);
  return html`<div class="match">
    <div class="mtop">
      <span class="mtitle">${j.title}</span>
      <span class="fit" style=${{ color: pct >= 60 ? "var(--pass)" : pct >= 35 ? "var(--warn)" : "var(--muted)" }}>${pct}% fit</span>
    </div>
    <div class="muted">${j.company}${j.location ? " · " + j.location : ""}${j.salary ? " · " + j.salary : ""}</div>
    ${(j.fit_reasons || []).length ? html`<div class="muted reasons">${j.fit_reasons.join(" · ")}</div>` : null}
  </div>`;
}

function Jobs() {
  const [mode, setMode] = useState("field");
  const [company, setCompany] = useState("");
  const [field, setField] = useState(FIELDS[0]);
  const [fieldOther, setFieldOther] = useState("");
  const [location, setLocation] = useState("");
  const [resumeB64, setResumeB64] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [msgs, setMsgs] = useState([]);
  const [matches, setMatches] = useState(null);
  const [picked, setPicked] = useState(null);
  const [tailor, setTailor] = useState(true);
  const [awaiting, setAwaiting] = useState(null);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState("");
  const esRef = useRef(null);
  const feedRef = useRef(null);

  useEffect(() => () => { if (esRef.current) esRef.current.close(); }, []);
  useEffect(() => { if (feedRef.current) feedRef.current.scrollIntoView({ block: "end", behavior: "smooth" }); }, [msgs, awaiting, result]);

  function onResume(e) {
    const f = e.target.files[0];
    if (!f) return;
    setResumeName(f.name);
    const r = new FileReader();
    r.onload = () => setResumeB64(r.result);
    r.readAsDataURL(f);
  }

  function queryFor() {
    if (mode === "company") return company.trim();
    if (mode === "field") return field === "Other" ? fieldOther.trim() : field;
    return "";
  }

  async function run() {
    if (esRef.current) esRef.current.close();
    setMsgs([]); setMatches(null); setPicked(null); setAwaiting(null); setResult(null); setErr("");
    const payload = { entry_mode: mode, query: queryFor(), location: location.trim() };
    if (mode === "resume") { payload.resume_b64 = resumeB64; payload.resume_name = resumeName; }
    let start;
    try {
      const res = await fetch("/api/jobs/start", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      start = await res.json();
      if (!res.ok) { setErr(start.error || "Failed to start"); return; }
    } catch (e) { setErr(String(e)); return; }
    setRunning(true);
    const es = new EventSource(`/api/jobs/stream?run_id=${start.run_id}&pace=0.4`);
    esRef.current = es;
    es.addEventListener("message", (e) => {
      const m = JSON.parse(e.data);
      setMsgs((p) => [...p, m]);
      if (m.intent === "job_matches") {
        const list = (m.payload.matches || []);
        setMatches(list);
        if (list.length) setPicked(list[0].id);
      }
    });
    es.addEventListener("await_decision", (e) => setAwaiting(JSON.parse(e.data).run_id));
    es.addEventListener("result", (e) => setResult(JSON.parse(e.data)));
    es.addEventListener("error", (e) => { try { setErr(JSON.parse(e.data).detail); } catch (_) {} });
    es.addEventListener("done", () => { setRunning(false); setAwaiting(null); es.close(); });
  }

  async function decide(proceed) {
    const run_id = awaiting; setAwaiting(null);
    await fetch("/api/jobs/decision", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id, proceed, match_id: picked, tailor }),
    });
  }

  const canRun = !running && (
    (mode === "company" && company.trim()) ||
    (mode === "field" && (field !== "Other" || fieldOther.trim())) ||
    (mode === "resume" && resumeB64)
  );

  return html`<div>
    <div class="resolve-modes">
      ${[["company", "By company"], ["field", "By field"], ["resume", "By resume"]].map(([k, l]) =>
        html`<button key=${k} class=${"tab" + (mode === k ? " on" : "")} disabled=${running} onClick=${() => setMode(k)}>${l}</button>`)}
    </div>

    <div class="block resolve-input">
      ${mode === "company" ? html`<div class="fields">
        <label>Company <input value=${company} placeholder="e.g. Stripe" onInput=${(e) => setCompany(e.target.value)} /></label>
        <label>Location <input value=${location} placeholder="optional" onInput=${(e) => setLocation(e.target.value)} /></label>
      </div>` : null}
      ${mode === "field" ? html`<div class="fields">
        <label>Field <select value=${field} onChange=${(e) => setField(e.target.value)}>
          ${FIELDS.map((f) => html`<option key=${f} value=${f}>${f}</option>`)}
          <option value="Other">Other (free text)</option>
        </select></label>
        ${field === "Other" ? html`<label>Custom <input value=${fieldOther} onInput=${(e) => setFieldOther(e.target.value)} /></label>` : null}
        <label>Location <input value=${location} placeholder="optional" onInput=${(e) => setLocation(e.target.value)} /></label>
      </div>` : null}
      ${mode === "resume" ? html`<div>
        <label class="filebtn">Upload resume (PDF / DOCX)<input type="file" accept=".pdf,.docx,.txt" onChange=${onResume} /></label>
        ${resumeName ? html`<span class="muted"> ${resumeName}</span>` : html`<span class="muted"> @observer parses skills + titles via pdfplumber/python-docx + LLM</span>`}
        <div class="fields" style=${{ marginTop: "10px" }}><label>Location <input value=${location} placeholder="optional" onInput=${(e) => setLocation(e.target.value)} /></label></div>
      </div>` : null}
    </div>

    <div class="section-head">
      <div class="status"><span class=${"dot" + (running ? " live" : "")}></span>${running ? "live" : result ? "done" : "idle"}</div>
      <div class="spacer"></div>
      <button class="run" onClick=${run} disabled=${!canRun}>${msgs.length ? "Re-run" : "Find jobs"}</button>
    </div>

    ${err ? html`<div class="empty" style=${{ borderColor: "var(--reject)", color: "var(--reject)" }}>${err}</div>` : null}

    <div class="feed" ref=${feedRef}>
      ${msgs.length === 0 && !err
        ? html`<div class="empty">Pick an entry mode and press <b>Find jobs</b>. Five agents coordinate over the Band bus: observer → validator (live Adzuna search + fit scoring) → your approval → tailor → applier.</div>`
        : msgs.map((m) => html`<${JobCard} key=${m.seq} m=${m} />`)}

      ${awaiting && matches ? html`<div class="approval">
        <div class="ahead">✦ PICK A ROLE & APPROVE</div>
        <div class="picker">
          ${matches.map((j) => html`<label key=${j.id} class=${"pick" + (picked === j.id ? " on" : "")}>
            <input type="radio" name="pick" checked=${picked === j.id} onChange=${() => setPicked(j.id)} />
            <span><b>${j.title}</b> — ${j.company} <span class="muted">(${Math.round(j.fit_score * 100)}% fit)</span></span>
          </label>`)}
        </div>
        <label class="tailorck"><input type="checkbox" checked=${tailor} onChange=${(e) => setTailor(e.target.checked)} /> Tailor my resume to this posting</label>
        <div class="abtns">
          <button class="run" onClick=${() => decide(true)}>Proceed</button>
          <button class="ghost" onClick=${() => decide(false)}>Cancel</button>
        </div>
      </div>` : null}
    </div>

    ${result ? html`<${JobResult} r=${result} />` : null}
  </div>`;
}

function JobResult({ r }) {
  const apps = r.applications || [];
  const submitted = apps.filter((a) => a.status === "submitted").length;
  const queued = apps.filter((a) => a.status === "queued").length;
  const [draft, setDraft] = useState(null);
  const [targets, setTargets] = useState([]);
  const [posted, setPosted] = useState(null);
  const top = (r.matches || [])[0];

  async function makeDraft() {
    const res = await fetch("/api/channels/draft", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: top && top.title, company: top && top.company, skills: (r.profile || {}).skills }),
    });
    const d = await res.json();
    setDraft(d.draft); setTargets(d.post_targets || []); setPosted(null);
  }
  async function post(name) {
    const res = await fetch(`/api/channels/${name}/post`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: draft }),
    });
    const d = await res.json();
    setPosted({ name, ...d });
  }

  return html`<div>
    <div class="verdict">
      <div class="vhead">RUN COMPLETE — ${r.matches.length} matches · ${r.tailored_count} tailored · ${submitted} submitted · ${queued} queued</div>
      <div class="grid">
        <div class="cell"><div class="k">Provider</div><div class="v">${r.provider}</div></div>
        <div class="cell"><div class="k">Matches found</div><div class="v">${r.matches.length}</div></div>
        <div class="cell"><div class="k">Submitted</div><div class="v">${submitted}</div></div>
        <div class="cell"><div class="k">Queued</div><div class="v">${queued}</div></div>
      </div>
    </div>
    ${top ? html`<div class="block" style=${{ marginTop: "14px" }}>
      <h3>Share as a post (approve, then publish)</h3>
      ${!draft ? html`<button class="ghost" onClick=${makeDraft}>Draft a post about ${top.title}</button>`
        : html`<div>
          <textarea rows="3" value=${draft} onInput=${(e) => setDraft(e.target.value)}></textarea>
          <div class="abtns" style=${{ marginTop: "10px" }}>
            ${targets.length ? targets.map((n) => html`<button key=${n} class="run" onClick=${() => post(n)}>Post to ${n}</button>`)
              : html`<span class="muted">No post-capable channel connected — connect X or LinkedIn in Integrations.</span>`}
          </div>
          ${posted ? html`<div class=${"emailbar " + (posted.ok ? "pass" : "warn")}>${posted.ok ? "✓" : "✕"} ${posted.name}: ${posted.detail}</div>` : null}
        </div>`}
    </div>` : null}
  </div>`;
}

function History() {
  const [filter, setFilter] = useState("all");
  const [items, setItems] = useState(null);
  const [sel, setSel] = useState(null);    // {kind, id}
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    setItems(null);
    fetch(`/api/history?type=${filter}`).then((r) => r.json()).then((d) => setItems(d.items)).catch(() => setItems([]));
  }, [filter]);

  function open(it) {
    setSel(it); setDetail(null);
    fetch(`/api/history/${it.kind}/${it.id}`).then((r) => r.json()).then((d) => setDetail(d));
  }

  if (sel) return html`<${HistoryDetail} sel=${sel} detail=${detail} onBack=${() => { setSel(null); setDetail(null); }} />`;

  return html`<div>
    <div class="resolve-modes">
      ${[["all", "All"], ["incident", "Incidents"], ["job", "Jobs"]].map(([k, l]) =>
        html`<button key=${k} class=${"tab" + (filter === k ? " on" : "")} onClick=${() => setFilter(k)}>${l}</button>`)}
    </div>
    ${items === null ? html`<div class="empty">Loading…</div>`
      : items.length === 0 ? html`<div class="empty">No runs yet. Resolve an incident or run a job search.</div>`
      : html`<div class="activity">
          ${items.map((it) => html`<div key=${it.kind + it.id} class="act histrow" onClick=${() => open(it)}>
            <span class="ic">${it.kind === "incident" ? "⚡" : "✦"}</span>
            <div class="body"><div class="t">${it.title}</div><div class="s">${it.subtitle}</div></div>
            <span class="metric muted">${it.metric}</span>
            <span class=${"chip " + it.status}>${it.status}</span>
            <span class="when">${timeAgo(it.created_at)}</span>
          </div>`)}
        </div>`}
  </div>`;
}

function HistoryDetail({ sel, detail, onBack }) {
  const dlMd = `/api/report/${sel.kind}/${sel.id}?fmt=md`;
  const dlPdf = `/api/report/${sel.kind}/${sel.id}?fmt=pdf`;
  return html`<div>
    <div class="section-head">
      <button class="ghost" onClick=${onBack}>← Back</button>
      <div class="spacer"></div>
      <a class="dlbtn" href=${dlMd} target="_blank" rel="noreferrer">Download MD</a>
      <a class="dlbtn" href=${dlPdf} target="_blank" rel="noreferrer">Download PDF</a>
    </div>
    ${!detail ? html`<div class="empty">Loading report…</div>`
      : sel.kind === "incident" ? html`<${IncidentReport} run=${detail.run} />`
      : html`<${JobReport} run=${detail.run} />`}
  </div>`;
}

function IncidentReport({ run }) {
  const v = run.verdict || {}, pm = run.postmortem || {};
  return html`<div>
    <div class="block">
      <h3>${pm.incident_id || "incident"} — ${run.service} / ${run.region}</h3>
      <div class="facts">
        <span class=${"pill " + (run.resolved ? "" : "warn")}>${run.resolved ? "resolved" : "escalated"}</span>
        <span class="pill">${run.severity}</span>
        <span class="pill">MTTR ${((run.mttr_seconds || 0) / 60).toFixed(1)}m</span>
        <span class="pill">averted $${Math.round(run.averted_cost_usd || 0).toLocaleString()}</span>
      </div>
      <p><b>Diagnosed:</b> ${pm.root_cause || "n/a"}</p>
      <p><b>Fixed via:</b> ${v.action || pm.resolution || "n/a"} · <b>approved by</b> ${v.approved_by || "n/a"}</p>
    </div>
    ${(pm.follow_ups || []).length ? html`<div class="block"><h3>Follow-ups</h3>
      <div class="followups">${pm.follow_ups.map((f, i) => html`<div key=${i} class="fu">${f}</div>`)}</div></div>` : null}
    <div class="block"><h3>Timeline</h3>
      <div class="trace">${(run.transcript || []).map((m, i) =>
        html`<div key=${i} class="line"><b>${m.sender}</b> [${m.intent}]: ${m.text}</div>`)}</div>
    </div>
  </div>`;
}

function JobReport({ run }) {
  const prof = run.profile || {}, matches = run.matches || [], apps = run.applications || [];
  return html`<div>
    <div class="block">
      <h3>Job search — ${run.query}</h3>
      <div class="facts">
        <span class="pill">${run.entry_mode}</span>
        <span class="pill">${run.match_count} matches</span>
        <span class="pill">${run.tailored_count} tailored</span>
        <span class="pill">${run.applied_count} submitted · ${run.queued_count} queued</span>
      </div>
      <p><b>Skills:</b> ${(prof.skills || []).join(", ") || "—"}</p>
    </div>
    <div class="block"><h3>Ranked matches</h3><div class="matches">
      ${matches.map((j, i) => html`<${MatchRow} key=${i} j=${j} />`)}
    </div></div>
    ${apps.length ? html`<div class="block"><h3>Applications</h3>
      ${apps.map((a, i) => html`<div key=${i} class=${"appbox " + a.status}>
        <span class=${"chip " + (a.status === "submitted" ? "submitted" : "queued")}>${a.status}</span>
        <span class="muted"> ${a.title} @ ${a.company} via ${a.method} — ${a.detail}</span>
      </div>`)}</div>` : null}
  </div>`;
}

function Integrations() {
  const [services, setServices] = useState(null);
  const [chans, setChans] = useState(null);
  const [tests, setTests] = useState({}); // key -> {loading|ok|detail}

  useEffect(() => {
    fetch("/api/dashboard").then((r) => r.json()).then((d) => setServices(d.services)).catch(() => {});
    fetch("/api/channels").then((r) => r.json()).then((d) => setChans(d.channels)).catch(() => {});
  }, []);

  async function test(key, url) {
    setTests((t) => ({ ...t, [key]: { loading: true } }));
    try {
      const r = await fetch(url, { method: "POST" });
      const res = await r.json();
      setTests((t) => ({ ...t, [key]: res }));
    } catch (e) {
      setTests((t) => ({ ...t, [key]: { ok: false, detail: String(e) } }));
    }
  }

  const CAPS = ["notify", "approve", "converse", "post", "job_search", "job_apply"];

  return html`<div>
    <div class="block">
      <h3>Connected services — config + live test</h3>
      ${!services ? html`<div class="empty">Loading…</div>` : html`<div class="services">
        ${services.map((s) => {
          const t = tests["svc:" + s.key];
          return html`<div key=${s.key} class="svc intg">
            <span class=${"dot " + (s.ok ? "ok" : "bad")}></span>
            <span class="label">${s.label}</span>
            <span class="detail">${s.detail}</span>
            <button class="ghost tbtn" disabled=${t && t.loading} onClick=${() => test("svc:" + s.key, `/api/integrations/test/${s.key}`)}>
              ${t && t.loading ? "Testing…" : "Test"}</button>
            ${t && !t.loading ? html`<span class=${"tres " + (t.ok ? "good" : "bad")}>${t.ok ? "✓" : "✕"} ${t.detail}</span>` : null}
          </div>`;
        })}
      </div>`}
    </div>

    <div class="block">
      <h3>Channels — multi-platform delivery</h3>
      ${!chans ? html`<div class="empty">Loading…</div>` : html`<div class="services">
        ${chans.map((c) => {
          const t = tests["ch:" + c.name];
          return html`<div key=${c.name} class="svc intg">
            <span class=${"dot " + (c.enabled ? "ok" : "bad")}></span>
            <span class="label">${c.label}</span>
            <span class="detail">${c.detail}</span>
            <button class="ghost tbtn" disabled=${!c.enabled || (t && t.loading)} onClick=${() => test("ch:" + c.name, `/api/channels/${c.name}/test`)}>
              ${t && t.loading ? "Sending…" : "Send test"}</button>
            <span class="caps">
              ${CAPS.filter((k) => c.capabilities[k]).map((k) => html`<span key=${k} class="cap on">${k}</span>`)}
              ${CAPS.filter((k) => !c.capabilities[k]).map((k) => html`<span key=${k} class="cap">${k}</span>`)}
            </span>
            ${t && !t.loading ? html`<span class=${"tres " + (t.ok ? "good" : "bad")}>${t.ok ? "✓" : "✕"} ${t.detail}</span>` : null}
          </div>`;
        })}
      </div>`}
    </div>
  </div>`;
}

function Settings() {
  const [s, setS] = useState(null);
  const [recips, setRecips] = useState("");
  const [field, setField] = useState("Software Engineer");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/settings").then((r) => r.json()).then((d) => {
      setS(d); setRecips(d.email_recipients || ""); setField(d.default_field || "Software Engineer");
    });
  }, []);

  async function save() {
    await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email_recipients: recips, default_field: field }),
    });
    setSaved(true); setTimeout(() => setSaved(false), 2000);
  }

  if (!s) return html`<div class="empty">Loading…</div>`;
  return html`<div>
    <div class="block">
      <h3>Keys — status only (values never shown)</h3>
      <${ServiceList} services=${s.services} />
    </div>
    <div class="block">
      <h3>Preferences</h3>
      <div class="setform">
        <label>Incident-report recipients (comma-separated)
          <input value=${recips} placeholder="oncall@team.com, lead@team.com" onInput=${(e) => setRecips(e.target.value)} /></label>
        <label>Default job field
          <select value=${field} onChange=${(e) => setField(e.target.value)}>
            ${FIELDS.map((f) => html`<option key=${f} value=${f}>${f}</option>`)}
          </select></label>
      </div>
      <div style=${{ marginTop: "14px" }}>
        <button class="primary" onClick=${save}>Save</button>
        ${saved ? html`<span class="muted" style=${{ marginLeft: "10px", color: "var(--pass)" }}>✓ Saved</span>` : null}
      </div>
    </div>
  </div>`;
}

function Bars({ title, data, fmt }) {
  const max = Math.max(1, ...data.map((d) => d.v));
  return html`<div class="block">
    <h3>${title}</h3>
    ${data.length === 0 ? html`<div class="muted">No data yet.</div>` : html`<div class="bars">
      ${data.map((d, i) => html`<div key=${i} class="bar">
        <span class="blabel">${d.k}</span>
        <span class="btrack"><span class="bfill" style=${{ width: (100 * d.v / max) + "%" }}></span></span>
        <span class="bval">${fmt ? fmt(d.v) : d.v}</span>
      </div>`)}
    </div>`}
  </div>`;
}

function Analytics() {
  const [a, setA] = useState(null);
  useEffect(() => { fetch("/api/analytics").then((r) => r.json()).then(setA).catch(() => {}); }, []);
  if (!a) return html`<div class="empty">Loading…</div>`;

  const mttr = a.mttr_series.map((p, i) => ({ k: "#" + (i + 1), v: p.mttr_min }));
  const cost = a.cost_series.map((p, i) => ({ k: "#" + (i + 1), v: p.cumulative }));
  const funnel = [
    { k: "Found", v: a.job_funnel.found }, { k: "Tailored", v: a.job_funnel.tailored },
    { k: "Submitted", v: a.job_funnel.submitted }, { k: "Queued", v: a.job_funnel.queued },
  ];
  const status = [
    { k: "Resolved", v: a.incident_status.resolved }, { k: "Escalated", v: a.incident_status.escalated },
  ];
  return html`<div>
    <div class="two-col">
      <${Bars} title="MTTR per incident (min)" data=${mttr} fmt=${(v) => v + "m"} />
      <${Bars} title="Cost averted (cumulative)" data=${cost} fmt=${(v) => "$" + Math.round(v).toLocaleString()} />
    </div>
    <div class="two-col" style=${{ marginTop: "14px" }}>
      <${Bars} title="Incident outcomes" data=${status} />
      <${Bars} title="Application funnel" data=${funnel} />
    </div>
  </div>`;
}

// ── App shell ───────────────────────────────────────────────────────── //
const SECTIONS = {
  dashboard: { title: "Dashboard", desc: "Platform overview", comp: Dashboard },
  resolve: { title: "Resolve", desc: "Incident war room — agents coordinate over the Band bus", comp: Resolve },
  jobs: { title: "Jobs", desc: "Find, tailor, and apply — multi-agent", comp: Jobs },
  history: { title: "History", desc: "Past incident and job runs", comp: History },
  analytics: { title: "Analytics", desc: "MTTR trend, cost averted, application funnel", comp: Analytics },
  integrations: { title: "Integrations", desc: "Connected services — config + live test", comp: Integrations },
  settings: { title: "Settings", desc: "Keys, recipients, defaults", comp: Settings },
};

function App() {
  const route = useRoute();
  const section = SECTIONS[route] || SECTIONS.dashboard;
  const Comp = section.comp;

  return html`<div class="app">
    <${Sidebar} route=${route} />
    <main class="main">
      <div class="section-head">
        <h2>${section.title}</h2>
        <span class="desc">${section.desc}</span>
      </div>
      <${Comp} />
    </main>
  </div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
