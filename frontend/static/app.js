/* Aegis platform UI. No build step: React UMD + htm tagged templates.
   A hash-routed SPA shell (Dashboard / Resolve / Jobs / History / Integrations /
   Settings). The Resolve section reuses the original war-room transcript UI —
   all incident logic still lives in the Python orchestrator and streams over
   /stream. Other sections read the platform API (/api/dashboard, ...). */
const { useState, useEffect, useRef } = React;
const html = htm.bind(React.createElement);

// API base URL — same-origin by default; set window.AEGIS_API_BASE (config.js) to
// the Railway backend when the SPA is hosted separately (Vercel). No hardcoded host.
const API_BASE = (window.AEGIS_API_BASE || "").replace(/\/$/, "");
const _isApi = (u) => typeof u === "string" && (u.startsWith("/api") || u.startsWith("/stream"));

// Wrap fetch once: prepend API_BASE for API calls, send cookies cross-origin, and
// bounce to sign-in on 401 (expired/anonymous session).
const _fetch = window.fetch.bind(window);
window.fetch = async (url, opts) => {
  if (_isApi(url) && API_BASE) {
    url = API_BASE + url;
    opts = Object.assign({ credentials: "include" }, opts);
  }
  const res = await _fetch(url, opts);
  if (res.status === 401) window.location = "/landing";
  return res;
};

// Wrap EventSource the same way so SSE streams hit the right origin with cookies.
const _ES = window.EventSource;
window.EventSource = function (url, opts) {
  if (_isApi(url) && API_BASE) {
    url = API_BASE + url;
    opts = Object.assign({ withCredentials: true }, opts);
  }
  return new _ES(url, opts);
};

async function signOut() {
  try { await fetch("/api/auth/logout", { method: "POST" }); } catch (_) {}
  window.location = "/landing";
}

const LANES = {
  "@security":      { var: "--validator",     label: "SECURITY" },
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

const TerminalIcon = html`<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style=${{ display: "block" }}><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>`;
const SlidersIcon = html`<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style=${{ display: "block" }}><line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line><line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line><line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line><line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line><line x1="17" y1="16" x2="23" y2="16"></line></svg>`;
const ActivityIcon = html`<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style=${{ display: "block" }}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>`;
const ClockIcon = html`<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style=${{ display: "block" }}><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`;
const BarChartIcon = html`<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style=${{ display: "block" }}><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>`;

function Sidebar({ route, me }) {
  const sections = [
    {
      title: "Platform",
      items: [
        { id: "resolve", label: "Playground", ic: TerminalIcon, path: "#resolve" },
        { id: "integrations", label: "Models", ic: SlidersIcon, path: "#integrations" }
      ]
    },
    {
      title: "Jobs & Runs",
      items: [
        { id: "jobs", label: "Active Jobs", ic: ActivityIcon, path: "#jobs" },
        { id: "history", label: "Run History", ic: ClockIcon, path: "#history" },
        { id: "analytics", label: "Reports", ic: BarChartIcon, path: "#analytics" }
      ]
    }
  ];

  const parsedName = me && me.email
    ? me.email.split("@")[0].split(/[._-]/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    : "Lincoln Curtis";

  return html`<aside class="sidebar">
    <a href="#dashboard" class="brand">
      <h1>Aegis Console</h1>
      <div class="sub">MULTI-AGENT SYSTEM</div>
    </a>
    
    ${sections.map((sec, sIdx) => html`
      <div key=${sIdx} class="nav-section">
        ${sec.title ? html`<div class="nav-section-title">${sec.title}</div>` : null}
        <nav class="nav">
          ${sec.items.map((item) => {
            const isActive = route === item.id;
            
            return html`<a 
              key=${item.id} 
              href=${item.path} 
              class=${isActive ? "active" : ""}
            >
              <span class="ic">${item.ic}</span>
              <span>${item.label}</span>
            </a>`;
          })}
        </nav>
      </div>
    `)}

    <div class="foot">
      ${me ? html`<div class="user" style=${{ display: "flex", flexDirection: "row", alignItems: "center", gap: "10px", borderTop: "1px solid var(--line)", borderBottom: "none", paddingTop: "14px", paddingBottom: "0", marginBottom: "0" }}>
        <div class="top-user-avatar" style=${{ width: "36px", height: "36px", borderRadius: "50%", background: "linear-gradient(135deg, #f472b6, #db2777)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "700" }}>
          ${me.email ? me.email.charAt(0).toUpperCase() : "L"}
        </div>
        <div style=${{ flex: 1, minWidth: "0" }}>
          <div style=${{ fontWeight: "700", fontSize: "13px", color: "var(--txt)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            ${parsedName}
          </div>
          <div style=${{ fontSize: "11px", color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            ${me.email || "mail@lincoln.com"}
          </div>
        </div>
        <button class="signout" onClick=${signOut} style=${{ padding: "4px 8px", fontSize: "11px", minWidth: "auto", border: "none", background: "transparent", color: "var(--muted)" }} title="Sign Out">✕</button>
      </div>` : null}
    </div>
  </aside>`;
}

// ── Dashboard ───────────────────────────────────────────────────────── //
function Dashboard() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [timeframe, setTimeframe] = useState("monthly");
  const [hoveredBar, setHoveredBar] = useState(8); // Default pre-hover September to match screenshot
  const [selectedRuns, setSelectedRuns] = useState({});

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

  const statCards = [
    { k: "Total Incidents Averted", v: "$3,250,000", sub: "Estimated downtime costs saved", trend: "+12.4%", up: true },
    { k: "Active Agent Jobs", v: "142", sub: "Currently running validation & triage", trend: "+8.2%", up: true },
    { k: "System Health / SLO", v: "99.98%", sub: "Service level objective status", trend: "+0.02%", up: true },
  ];

  // Bar Chart Data (Jan - Dec)
  const barData = [
    { m: "Jan", incident: 15, job: 8 },
    { m: "Feb", incident: 22, job: 10 },
    { m: "Mar", incident: 28, job: 12 },
    { m: "Apr", incident: 19, job: 15 },
    { m: "May", incident: 34, job: 21 },
    { m: "Jun", incident: 42, job: 24 },
    { m: "Jul", incident: 39, job: 18 },
    { m: "Aug", incident: 36, job: 25 },
    { m: "Sep", incident: 42, job: 20, active: true }, // Highlighted Month
    { m: "Oct", incident: 25, job: 12 },
    { m: "Nov", incident: 30, job: 16 },
    { m: "Dec", incident: 48, job: 26 },
  ];

  // base runs list rows
  const baseRuns = [
    { id: "r1", runId: "checkout-api-db-saturation", time: "18 Jun 2026, 2:15 pm", duration: "1m 45s", status: "Resolved" },
    { id: "r2", runId: "auth-service-latency-spike", time: "18 Jun 2026, 1:40 pm", duration: "45s", status: "Escalated" },
    { id: "r3", runId: "tailor-resume-ml-engineer", time: "18 Jun 2026, 11:20 am", duration: "12s", status: "Resolved" },
    { id: "r4", runId: "payment-gateway-timeout", time: "18 Jun 2026, 9:05 am", duration: "2m 10s", status: "Resolved" },
    { id: "r5", runId: "search-jobs-by-field", time: "18 Jun 2026, 8:30 am", duration: "8s", status: "Resolved" },
  ];

  // Map API activity into rows if available to keep it connected
  const dynamicRows = (data.activity || []).slice(0, 3).map((a, i) => {
    const isIncident = a.kind === "incident";
    return {
      id: "dyn-" + i,
      runId: a.title,
      time: timeAgo(a.created_at),
      duration: isIncident ? "2m 15s" : "12s",
      status: a.status === "resolved" || a.status === "submitted" || a.status === "applied" ? "Resolved" : "Escalated"
    };
  });

  const allRuns = [...dynamicRows, ...baseRuns].slice(0, 5);

  const toggleSelect = (id) => {
    setSelectedRuns(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleSelectAll = (e) => {
    const checked = e.target.checked;
    const newSelects = {};
    if (checked) {
      allRuns.forEach(r => { newSelects[r.id] = true; });
    }
    setSelectedRuns(newSelects);
  };

  const isAllSelected = allRuns.length > 0 && allRuns.every(r => selectedRuns[r.id]);

  // Donut chart segments calculation
  const circ = 251.32;
  const donutSegments = [
    { label: "Observer", pct: 40, color: "var(--observer)", len: circ * 0.40, offset: 0 },
    { label: "Diagnostician", pct: 25, color: "var(--diagnostician)", len: circ * 0.25, offset: -circ * 0.40 },
    { label: "Remediator", pct: 20, color: "var(--remediator)", len: circ * 0.20, offset: -circ * 0.65 },
    { label: "Validator", pct: 15, color: "var(--validator)", len: circ * 0.15, offset: -circ * 0.85 }
  ];

  return html`<div>
    <div class="quick">
      <button class="primary" onClick=${() => (window.location.hash = "#resolve")}>⚡ Resolve an incident</button>
      <button class="ghost" onClick=${() => (window.location.hash = "#jobs")}>✦ Find jobs</button>
    </div>

    <!-- Stats Cards -->
    <div class="cards">
      ${statCards.map((s, i) => html`<div key=${i} class="stat">
        <div class="k">${s.k}</div>
        <div class="v">
          ${s.v}
          <span class=${"stat-trend " + (s.up ? "up" : "down")}>
            ${s.up ? "▲" : "▼"} ${s.trend}
          </span>
        </div>
        <div class="sub">${s.sub}</div>
      </div>`)}
    </div>

    <div class="two-col">
      <!-- Left Column: Activity Chart & Active Systems & Runs -->
      <div style=${{ display: "flex", flexDirection: "column", gap: "20px" }}>
        <!-- Agent Coordination Activity Chart -->
        <div class="block" style=${{ position: "relative" }}>
          <h3>
            <span>Agent Coordination Activity</span>
            <div class="resolve-modes" style=${{ margin: 0 }}>
              <button class=${"tab" + (timeframe === "monthly" ? " on" : "")} style=${{ padding: "4px 10px", fontSize: "11.5px", borderRadius: "6px" }} onClick=${() => setTimeframe("monthly")}>Monthly</button>
              <button class=${"tab" + (timeframe === "quarterly" ? " on" : "")} style=${{ padding: "4px 10px", fontSize: "11.5px", borderRadius: "6px" }} onClick=${() => setTimeframe("quarterly")}>Quarterly</button>
              <button class=${"tab" + (timeframe === "yearly" ? " on" : "")} style=${{ padding: "4px 10px", fontSize: "11.5px", borderRadius: "6px" }} onClick=${() => setTimeframe("yearly")}>Yearly</button>
            </div>
          </h3>
          
          <div style=${{ height: "240px", marginTop: "16px", position: "relative" }}>
            <svg width="100%" height="100%" viewBox="0 0 540 240" preserveAspectRatio="none">
              <!-- Grid lines -->
              <line x1="40" y1="40" x2="520" y2="40" stroke="rgba(0,0,0,0.04)" stroke-width="1" />
              <line x1="40" y1="80" x2="520" y2="80" stroke="rgba(0,0,0,0.04)" stroke-width="1" />
              <line x1="40" y1="120" x2="520" y2="120" stroke="rgba(0,0,0,0.04)" stroke-width="1" />
              <line x1="40" y1="160" x2="520" y2="160" stroke="rgba(0,0,0,0.04)" stroke-width="1" />
              <line x1="40" y1="200" x2="520" y2="200" stroke="rgba(0,0,0,0.08)" stroke-width="1" />
              
              <!-- Y-Axis Labels -->
              <text x="30" y="44" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">80</text>
              <text x="30" y="84" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">60</text>
              <text x="30" y="124" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">40</text>
              <text x="30" y="164" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">20</text>
              <text x="30" y="204" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">0</text>
              
              <!-- Bars -->
              ${barData.map((b, idx) => {
                const totalH = 160; // Max height in px
                const maxVal = 76;  // Represents the max possible val (incident + job max)
                const incidentH = (b.incident / maxVal) * totalH;
                const jobH = (b.job / maxVal) * totalH;
                
                const colW = 16;
                const gap = (480) / 12;
                const x = 50 + idx * gap;
                const isHovered = hoveredBar === idx;
                const isSep = b.active;
                
                // Colors: highlighted is colored, others are muted pastel
                const incidentColor = isSep || isHovered ? "#4f46e5" : "rgba(79, 70, 229, 0.15)";
                const jobColor = isSep || isHovered ? "#fbbf24" : "rgba(251, 191, 36, 0.15)";
                
                return html`<g key=${idx} style=${{ cursor: "pointer" }} onMouseEnter=${() => setHoveredBar(idx)}>
                  <!-- Background thin full-height hover target -->
                  <rect x=${x - 8} y="20" width=${colW + 16} height="190" fill="transparent" />
                  
                  <!-- Stacked Bar (Incidents - bottom) -->
                  <rect 
                    x=${x} 
                    y=${200 - incidentH} 
                    width=${colW} 
                    height=${incidentH} 
                    fill=${incidentColor} 
                    rx="3"
                  />
                  <!-- Stacked Bar (Jobs - top) -->
                  <rect 
                    x=${x} 
                    y=${200 - incidentH - jobH} 
                    width=${colW} 
                    height=${jobH} 
                    fill=${jobColor} 
                    rx="3"
                  />
                  
                  <!-- X-Axis Label -->
                  <text 
                    x=${x + colW / 2} 
                    y="218" 
                    text-anchor="middle" 
                    fill=${isSep ? "var(--accent-brand)" : "var(--muted)"} 
                    font-size="10.5" 
                    font-weight=${isSep ? "800" : "600"}
                  >${b.m}</text>
                </g>`;
              })}
            </svg>
            
            <!-- Tooltip overlay -->
            ${hoveredBar !== null ? (() => {
              const gap = (480) / 12;
              const xPos = 50 + hoveredBar * gap + 8;
              const b = barData[hoveredBar];
              return html`<div class="chart-tooltip" style=${{ left: `calc(${xPos / 5.4}% - 48px)`, top: "35px" }}>
                <div class="chart-tooltip-title">${b.m} 2026</div>
                <div class="chart-tooltip-row">
                  <span>● Incidents Averted</span>
                  <span class="chart-tooltip-val">${b.incident}</span>
                </div>
                <div class="chart-tooltip-row">
                  <span style=${{ color: "#fbbf24" }}>● Agent Jobs</span>
                  <span class="chart-tooltip-val">${b.job}</span>
                </div>
              </div>`;
            })() : null}
          </div>
        </div>

        <!-- Active Systems & Runs Table -->
        <div class="block">
          <h3>
            <span>Active Systems & Runs</span>
            <div style=${{ display: "flex", gap: "8px" }}>
              <button class="ghost" style=${{ padding: "6px 12px", fontSize: "12px", borderRadius: "8px", display: "flex", alignItems: "center", gap: "4px" }}>
                <span>⇅</span> Sort
              </button>
              <button class="ghost" style=${{ padding: "6px 12px", fontSize: "12px", borderRadius: "8px", display: "flex", alignItems: "center", gap: "4px" }}>
                <span>☲</span> Filter
              </button>
            </div>
          </h3>
          
          <div class="table-container">
            <table class="custom-table">
              <thead>
                <tr>
                  <th style=${{ width: "40px", textAlign: "center" }}>
                    <input type="checkbox" checked=${isAllSelected} onChange=${toggleSelectAll} style=${{ cursor: "pointer", width: "16px", height: "16px", accentColor: "var(--accent-brand)" }} />
                  </th>
                  <th>Run ID</th>
                  <th>Trigger Time</th>
                  <th>Duration</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                ${allRuns.map((r) => html`<tr key=${r.id} class="table-row">
                  <td class="checkbox-cell">
                    <input type="checkbox" checked=${!!selectedRuns[r.id]} onChange=${() => toggleSelect(r.id)} />
                  </td>
                  <td style=${{ fontWeight: "700" }}>${r.runId}</td>
                  <td style=${{ color: "var(--muted)", fontSize: "12.5px" }}>${r.time}</td>
                  <td style=${{ fontWeight: "700" }}>${r.duration}</td>
                  <td>
                    <span class=${"chip " + r.status.toLowerCase()}>${r.status}</span>
                  </td>
                </tr>`)}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Right Column: Agent Breakdown, Latency, Recent Agent Events -->
      <div style=${{ display: "flex", flexDirection: "column", gap: "20px" }}>
        <!-- Agent Resolution Breakdown Donut Chart -->
        <div class="block">
          <h3>
            <span>Agent Resolution Breakdown</span>
            <select style=${{ padding: "4px 8px", fontSize: "11px", borderRadius: "6px", background: "rgba(255,255,255,0.8)" }}>
              <option>Weekly</option>
              <option>Monthly</option>
            </select>
          </h3>
          
          <div style=${{ display: "flex", alignItems: "center", gap: "24px", marginTop: "16px" }}>
            <!-- SVG Donut -->
            <div style=${{ position: "relative", width: "110px", height: "110px", flexShrink: 0 }}>
              <svg width="110" height="110" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="40" fill="none" stroke="#f1f5f9" stroke-width="10" />
                ${donutSegments.map((seg, i) => html`<circle 
                  key=${i}
                  cx="50" 
                  cy="50" 
                  r="40" 
                  fill="none" 
                  stroke=${seg.color} 
                  stroke-width="10" 
                  stroke-dasharray=${`${seg.len} ${circ}`} 
                  stroke-dashoffset=${seg.offset}
                  transform="rotate(-90 50 50)"
                  stroke-linecap="round"
                />`)}
              </svg>
              <!-- Center Text -->
              <div style=${{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                <span style=${{ fontSize: "9px", color: "var(--muted)", fontWeight: "600", textTransform: "uppercase" }}>Total Runs</span>
                <span style=${{ fontSize: "13px", fontWeight: "800", color: "var(--txt)", marginTop: "2px" }}>1,240</span>
              </div>
            </div>
            
            <!-- Legend -->
            <div style=${{ display: "flex", flexDirection: "column", gap: "8px", flex: 1 }}>
              ${donutSegments.map((seg, i) => html`<div key=${i} style=${{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "12.5px" }}>
                <div style=${{ display: "flex", alignItems: "center", gap: "8px", color: "var(--muted)", fontWeight: "500" }}>
                  <span style=${{ width: "8px", height: "8px", borderRadius: "50%", background: seg.color }}></span>
                  <span>${seg.label}</span>
                </div>
                <span style=${{ fontWeight: "700", color: "var(--txt)" }}>${seg.pct}%</span>
              </div>`)}
            </div>
          </div>
        </div>

        <!-- System Latency & Load Line Chart -->
        <div class="block">
          <h3>
            <span>System Latency & Load</span>
            <select style=${{ padding: "4px 8px", fontSize: "11px", borderRadius: "6px", background: "rgba(255,255,255,0.8)" }}>
              <option>Weekly</option>
              <option>Monthly</option>
            </select>
          </h3>
          
          <div style=${{ display: "flex", gap: "12px", fontSize: "11px", color: "var(--muted)", fontWeight: "700", margin: "4px 0 12px", justifyContent: "flex-end" }}>
            <div style=${{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style=${{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981" }}></span> System Load
            </div>
            <div style=${{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style=${{ width: "8px", height: "8px", borderRadius: "50%", background: "#4f46e5" }}></span> P99 Latency (ms)
            </div>
          </div>
          
          <div style=${{ height: "90px", position: "relative" }}>
            <svg width="100%" height="100%" viewBox="0 0 280 80" preserveAspectRatio="none">
              <!-- Gradients for line fill area -->
              <defs>
                <linearGradient id="activeGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#10b981" stop-opacity="0.15" />
                  <stop offset="100%" stop-color="#10b981" stop-opacity="0.0" />
                </linearGradient>
                <linearGradient id="investedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#4f46e5" stop-opacity="0.15" />
                  <stop offset="100%" stop-color="#4f46e5" stop-opacity="0.0" />
                </linearGradient>
              </defs>
              
              <!-- Grid line -->
              <line x1="0" y1="70" x2="280" y2="70" stroke="rgba(0,0,0,0.06)" stroke-width="1" />
              
              <!-- Area Fill paths -->
              <path d="M 0,80 Q 40,65 80,60 T 160,35 T 240,40 T 280,25 L 280,70 L 0,70 Z" fill="url(#activeGrad)" />
              <path d="M 0,80 Q 40,75 80,72 T 160,50 T 240,55 T 280,45 L 280,70 L 0,70 Z" fill="url(#investedGrad)" />
              
              <!-- Line paths -->
              <path d="M 0,70 Q 40,55 80,50 T 160,25 T 240,30 T 280,15" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" />
              <path d="M 0,75 Q 40,65 80,62 T 160,40 T 240,45 T 280,35" fill="none" stroke="#4f46e5" stroke-width="2" stroke-linecap="round" />
            </svg>
            <div style=${{ display: "flex", justifyContent: "space-between", fontSize: "9.5px", color: "var(--muted)", fontWeight: "600", marginTop: "4px" }}>
              <span>Oct, 2025</span>
              <span>Feb, 2026</span>
            </div>
          </div>
        </div>

        <!-- Recent Agent Events -->
        <div class="block">
          <h3>Recent Agent Events</h3>
          <div class="tx-list">
            <div class="tx-item">
              <div class="tx-icon" style=${{ color: "var(--accent-brand)", background: "rgba(79, 70, 229, 0.08)" }}>⚡</div>
              <div class="tx-details">
                <div class="tx-title">Incident Auto-Resolved</div>
                <div class="tx-desc">checkout-api db pool saturation fixed</div>
              </div>
              <div class="tx-amount" style=${{ color: "#0f172a" }}>-24m MTTR</div>
            </div>
            
            <div class="tx-item">
              <div class="tx-icon" style=${{ color: "#fbbf24", background: "rgba(251, 191, 36, 0.08)" }}>✦</div>
              <div class="tx-details">
                <div class="tx-title">Active Job Completed</div>
                <div class="tx-desc">Resume tailored for SRE Role</div>
              </div>
              <div class="tx-amount" style=${{ color: "#0f172a" }}>#8942</div>
            </div>
            
            <div class="tx-item">
              <div class="tx-icon" style=${{ color: "#10b981", background: "rgba(16, 185, 129, 0.08)" }}>🔍</div>
              <div class="tx-details">
                <div class="tx-title">Telemetry Anomaly</div>
                <div class="tx-desc">checkout-api p99 latency threshold crossed</div>
              </div>
              <div class="tx-amount" style=${{ color: "#0f172a" }}>Sev-2</div>
            </div>
          </div>
          
          <button class="btn-all-tx" onClick=${() => (window.location.hash = "#history")}>
            <span>All Events</span> ➔
          </button>
        </div>
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
    ${email ? html`<${IncidentEmail} info=${email} />` : null}
  </div>`;
}

function EmailStatus({ s }) {
  const map = {
    sent: ["pass", `✓ Emailed via ${s.provider} to ${(s.to || []).join(", ")}${(s.attached || []).length ? " (with " + s.attached.join(", ") + ")" : ""}`],
    not_configured: ["warn", `✉ NOT sent — email isn't configured (set RESEND/SMTP keys). ${s.detail || ""}`],
    recipient_not_allowed: ["warn", `✉ NOT sent — ${s.detail}`],
    error: ["warn", `✉ Send failed — ${s.detail}`],
    skipped: ["", `✉ ${s.detail || "Email skipped."}`],
  };
  const [cls, txt] = map[s.status] || ["", JSON.stringify(s)];
  return html`<div class=${"emailbar " + cls}>${txt}</div>`;
}

// Incident report: ASK for a recipient (prefilled with the user's email), require
// an explicit confirm click — no silent sends. From stays the verified sender;
// Reply-To is the signed-in user.
function IncidentEmail({ info }) {
  const [to, setTo] = useState((info.default ? [info.default] : []).join(", "));
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  if (info.status !== "prompt") return html`<${EmailStatus} s=${info} />`;
  if (result) return html`<${EmailStatus} s=${result} />`;

  async function send() {
    const recipients = to.split(",").map((s) => s.trim()).filter(Boolean);
    if (!recipients.length) return;
    setSending(true);
    const res = await fetch("/api/resolve/email", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_db_id: info.run_db_id, recipients }),
    });
    const d = await res.json();
    setSending(false);
    setResult(res.ok ? d : { status: "error", detail: d.error || "send failed" });
  }

  return html`<div class="emailbar" style=${{ color: "var(--txt)" }}>
    <div style=${{ fontWeight: 600 }}>✉ Send incident report</div>
    ${!info.configured ? html`<div class="muted" style=${{ marginTop: "6px" }}>Email isn't configured (RESEND/SMTP empty) — set keys in <code>.env</code> to enable sending.</div>` : null}
    <div style=${{ marginTop: "8px", display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
      <input style=${{ flex: 1, minWidth: "240px" }} value=${to} onInput=${(e) => setTo(e.target.value)} placeholder="recipient@example.com, …" />
      <button class="run" disabled=${sending || !to.trim()} onClick=${send}>${sending ? "Sending…" : "Send report"}</button>
    </div>
    ${(info.recent || []).length ? html`<div class="recents">Recent:${info.recent.map((r) => html`<button key=${r} class="chip-btn" onClick=${() => setTo(r)}>${r}</button>`)}</div>` : null}
    <div class="muted" style=${{ marginTop: "6px", fontSize: "11px" }}>Sent from the configured verified sender; Reply-To = your account email.</div>
  </div>`;
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
      ${[["company", "By company"], ["field", "By field"], ["resume", "By resume"], ["analyze", "Resume fit"]].map(([k, l]) =>
        html`<button key=${k} class=${"tab" + (mode === k ? " on" : "")} disabled=${running} onClick=${() => setMode(k)}>${l}</button>`)}
    </div>

    ${mode === "analyze" ? html`<${ResumeSuggestions} />` : html`<div>
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
    </div>`}
  </div>`;
}

// READ-ONLY resume fit analysis for a selected job. Reads the resume + job and
// returns improvement SUGGESTIONS — it NEVER rewrites/stores/emails a modified
// resume and never fabricates. Optional: email the suggestions summary (no file).
function ResumeSuggestions() {
  const [me, setMe] = useState(null);
  const [resumeB64, setResumeB64] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [jd, setJd] = useState("");
  const [recipient, setRecipient] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [emailing, setEmailing] = useState(false);
  const [emailStatus, setEmailStatus] = useState(null);

  useEffect(() => {
    fetch("/api/auth/me").then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d) { setMe(d); setRecipient(d.email); }
    }).catch(() => {});
  }, []);

  function onResume(e) {
    const f = e.target.files[0];
    if (!f) return;
    setResumeName(f.name);
    const r = new FileReader();
    r.onload = () => setResumeB64(r.result);
    r.readAsDataURL(f);
  }

  async function analyze() {
    setErr(""); setRes(null); setEmailStatus(null);
    if (!company.trim() && !title.trim()) { setErr("Enter the job's company or title."); return; }
    if (!resumeB64 && !(me && me.has_resume)) { setErr("Upload a resume — none on file yet."); return; }
    setBusy(true);
    const payload = { company: company.trim(), title: title.trim(), job_description: jd.trim() };
    if (resumeB64) { payload.resume_b64 = resumeB64; payload.resume_name = resumeName; }
    try {
      const r = await fetch("/api/jobs/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) setErr(d.error || "Analysis failed");
      else { setRes(d); setMe((m) => (m ? { ...m, has_resume: true } : m)); }
    } catch (e) { setErr(String(e)); }
    setBusy(false);
  }

  async function emailSummary() {
    if (!res) return;
    setEmailing(true); setEmailStatus(null);
    try {
      const r = await fetch("/api/jobs/analyze/email", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job: res.job, analysis: res.analysis, recipient: recipient.trim() }),
      });
      setEmailStatus(await r.json());
    } catch (e) { setEmailStatus({ status: "error", detail: String(e) }); }
    setEmailing(false);
  }

  const a = res && res.analysis;
  const Sec = (heading, items, color) => html`<div class="block" style=${{ marginTop: "12px", ...(color ? { borderColor: color } : {}) }}>
    <h3 style=${color ? { color } : null}>${heading}</h3>
    ${(items && items.length)
      ? html`<ul style=${{ margin: "6px 0 0", paddingLeft: "18px" }}>${items.map((x, i) => html`<li key=${i} class="muted" style=${{ margin: "4px 0" }}>${x}</li>`)}</ul>`
      : html`<p class="muted">—</p>`}
  </div>`;
  const emailLine = (e) => ({
    sent: ["pass", `✓ Suggestions summary emailed to ${recipient} via ${e.provider}`],
    not_configured: ["warn", "✉ Email not configured (RESEND/SMTP empty) — suggestions are shown above."],
    recipient_not_allowed: ["warn", `✉ ${e.detail}`],
    error: ["warn", `✉ Send failed — ${e.detail}`],
  }[e.status] || ["", ""]);

  return html`<div>
    <div class="block resolve-input">
      <div class="muted note"><b>Read-only.</b> The analysis agent reads your resume + the selected job and returns suggestions <b>you</b> act on — it never edits, stores, or emails a rewritten resume, and never invents experience.</div>
      <div>
        <label class="filebtn">${me && me.has_resume ? "Replace resume (optional)" : "Upload resume (PDF / DOCX)"}<input type="file" accept=".pdf,.docx,.txt" onChange=${onResume} /></label>
        ${resumeName ? html`<span class="muted"> ${resumeName}</span>`
          : me && me.has_resume ? html`<span class="muted"> reusing the resume already on file</span>`
          : html`<span class="muted"> required the first time</span>`}
      </div>
      <div class="fields" style=${{ marginTop: "12px" }}>
        <label>Job title <input value=${title} placeholder="e.g. Backend Engineer" onInput=${(e) => setTitle(e.target.value)} /></label>
        <label>Company <input value=${company} placeholder="e.g. Stripe" onInput=${(e) => setCompany(e.target.value)} /></label>
      </div>
      <div class="resolve-input" style=${{ marginTop: "12px" }}>
        <label class="muted" style=${{ fontSize: "11px", letterSpacing: ".5px" }}>Job description / key requirements (improves gap + keyword analysis)</label>
        <textarea rows="4" style=${{ width: "100%", marginTop: "6px" }} value=${jd} placeholder="Paste the posting or key requirements…" onInput=${(e) => setJd(e.target.value)}></textarea>
      </div>
    </div>

    <div class="section-head">
      <div class="status"><span class=${"dot" + (busy ? " live" : "")}></span>${busy ? "analyzing…" : res ? "done" : "idle"}</div>
      <div class="spacer"></div>
      <button class="run" onClick=${analyze} disabled=${busy}>${busy ? "Analyzing…" : "Analyze fit"}</button>
    </div>

    ${err ? html`<div class="empty" style=${{ borderColor: "var(--reject)", color: "var(--reject)" }}>${err}</div>` : null}

    ${a ? html`<div>
      <div class="verdict">
        <div class="vhead">RESUME FIT — ${(res.job.title || "role")} @ ${(res.job.company || "—")}</div>
        <div class="grid">
          <div class="cell"><div class="k">Fit score</div><div class="v big" style=${{ color: "var(--pass)", fontWeight: 700 }}>${a.score}/100</div></div>
          <div class="cell" style=${{ gridColumn: "span 2" }}><div class="k">Alignment</div><div class="v" style=${{ fontSize: "14px" }}>${a.alignment}</div></div>
          <div class="cell"><div class="k">Resume file</div><div class="v good" style=${{ fontSize: "13px" }}>unchanged ✓</div></div>
        </div>
      </div>
      ${Sec("Matched strengths", a.strengths)}
      ${Sec("Gaps to consider — advice only, never added for you", a.gaps, "#5a4a1f")}
      ${Sec("ATS / keyword suggestions (surface only if you truly have them)", a.ats_keywords)}
      ${Sec("Clarity & impact tips", a.clarity_tips)}
      ${Sec("Prioritized actions", a.actions)}
      <div class="muted" style=${{ marginTop: "6px", fontSize: "11px" }}>Source: ${a.source === "llm" ? "LLM analysis" : "rule-based (no LLM key set)"}</div>

      <div class="section-head" style=${{ marginTop: "14px" }}>
        <label class="muted" style=${{ fontSize: "12px" }}>Email this summary (no attachment) to <input style=${{ marginLeft: "6px", minWidth: "200px" }} value=${recipient} onInput=${(e) => setRecipient(e.target.value)} /></label>
        <div class="spacer"></div>
        <button class="ghost" onClick=${emailSummary} disabled=${emailing || !recipient.trim()}>${emailing ? "Sending…" : "Email me the suggestions"}</button>
      </div>
      ${emailStatus ? html`<div class=${"emailbar " + emailLine(emailStatus)[0]}>${emailLine(emailStatus)[1]}</div>` : null}
    </div>` : null}
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
  const [me, setMe] = useState(null);
  useEffect(() => {
    fetch("/api/auth/me").then((r) => (r.ok ? r.json() : null)).then(setMe).catch(() => {});
  }, []);
  const section = SECTIONS[route] || SECTIONS.dashboard;
  const Comp = section.comp;

  return html`<div class="app">
    <${Sidebar} route=${route} me=${me} />
    <main class="main">
      <!-- Aegis Top Header Bar -->
      <div class="topbar">
        <div style=${{ display: "flex", flexDirection: "column" }}>
          <h2 style=${{ margin: 0, fontSize: "24px", fontWeight: "800", letterSpacing: "-0.5px" }}>${section.title}</h2>
          <span class="desc" style=${{ marginTop: "4px", fontSize: "12.5px", color: "var(--muted)", fontWeight: "500" }}>${section.desc}</span>
        </div>
        <div class="top-actions">
          <div class="top-search-container">
            <span class="top-search-icon">🔍</span>
            <input class="top-search-input" placeholder="Search..." />
            <span class="top-search-shortcut">⌘K</span>
          </div>
          <div class="top-icon-btn" title="12 alerts pending">
            🔔
            <span class="top-icon-badge">12</span>
          </div>
          <div class="top-user-avatar" title=${me ? me.email : "Lincoln Curtis"}>
            ${me && me.email ? me.email.charAt(0).toUpperCase() : "L"}
          </div>
        </div>
      </div>
      <div class="page-transition-wrapper" key=${route}>
        <${Comp} />
      </div>
    </main>
  </div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
