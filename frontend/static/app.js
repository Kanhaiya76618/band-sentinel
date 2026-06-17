/* Aegis platform UI. No build step: React UMD + htm tagged templates.
   A hash-routed SPA shell (Dashboard / Resolve / Jobs / History / Integrations /
   Settings). The Resolve section reuses the original war-room transcript UI —
   all incident logic still lives in the Python orchestrator and streams over
   /stream. Other sections read the platform API (/api/dashboard, ...). */
const { useState, useEffect, useRef } = React;
const html = htm.bind(React.createElement);

// If the session expires (or we're not signed in), any API call returns 401 —
// bounce to the landing/sign-in page. Wrap fetch once, globally.
const _fetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await _fetch(...args);
  if (res.status === 401) window.location = "/landing";
  return res;
};

async function signOut() {
  try { await fetch("/api/auth/logout", { method: "POST" }); } catch (_) {}
  window.location = "/landing";
}

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

function Sidebar({ route, me }) {
  const sections = [
    {
      title: "Platform",
      items: [
        { id: "resolve", label: "Playground", ic: "🎮", path: "#resolve" },
        { id: "integrations", label: "Models", ic: "🎛️", path: "#integrations" },
        { id: "settings_docs", label: "Documentation", ic: "📖", path: "#settings" }
      ]
    },
    {
      title: "Loans",
      items: [
        { id: "jobs", label: "Active Loans", ic: "💼", path: "#jobs" },
        { id: "jobs_req", label: "Loan Requests", ic: "📄", path: "#jobs" },
        { id: "analytics", label: "Reports", ic: "📊", path: "#analytics" }
      ]
    },
    {
      title: "Insights",
      items: [
        { id: "analytics_insights", label: "Borrower Insights", ic: "👥", path: "#analytics" },
        { id: "analytics_overview", label: "Investment Overview", ic: "📈", path: "#analytics" },
        { id: "analytics_trends", label: "Trends", ic: "📉", path: "#analytics" }
      ]
    },
    {
      title: "",
      items: [
        { id: "history", label: "History", ic: "🕒", path: "#history" },
        { id: "settings_star", label: "Starred", ic: "⭐", path: "#settings" },
        { id: "settings", label: "Setting", ic: "⚙️", path: "#settings" }
      ]
    }
  ];

  const parsedName = me && me.email
    ? me.email.split("@")[0].split(/[._-]/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    : "Lincoln Curtis";

  return html`<aside class="sidebar">
    <a href="#dashboard" class="brand">
      <h1>Lendo Enterprise</h1>
      <div class="sub">AEGIS MULTI-AGENT PLATFORM</div>
    </a>
    
    ${sections.map((sec, sIdx) => html`
      <div key=${sIdx} class="nav-section">
        ${sec.title ? html`<div class="nav-section-title">${sec.title}</div>` : null}
        <nav class="nav">
          ${sec.items.map((item) => {
            const isActive = route === item.id || 
              (item.id === "analytics_insights" && route === "analytics") ||
              (item.id === "analytics_overview" && route === "analytics") ||
              (item.id === "analytics_trends" && route === "analytics") ||
              (item.id === "settings_docs" && route === "settings") ||
              (item.id === "settings_star" && route === "settings") ||
              (item.id === "jobs_req" && route === "jobs");
            
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
  const [selectedLoans, setSelectedLoans] = useState({});

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
    { k: "Total Loan Issued", v: "$3,250,000", sub: "Total amount lent to borrowers", trend: "+3.2%", up: true },
    { k: "Approved Loans", v: "$2,780,000", sub: "Loans successfully funded", trend: "+3.2%", up: true },
    { k: "Interest Earned", v: "$1,436,120", sub: "Total interest from repayments", trend: "+3.2%", up: true },
  ];

  // Bar Chart Data (Jan - Dec)
  const barData = [
    { m: "Jan", edu: 15, pers: 8 },
    { m: "Feb", edu: 22, pers: 10 },
    { m: "Mar", edu: 28, pers: 12 },
    { m: "Apr", edu: 19, pers: 15 },
    { m: "May", edu: 34, pers: 21 },
    { m: "Jun", edu: 42, pers: 24 },
    { m: "Jul", edu: 39, pers: 18 },
    { m: "Aug", edu: 36, pers: 25 },
    { m: "Sep", edu: 42, pers: 20, active: true }, // Highlighted Month
    { m: "Oct", edu: 25, pers: 12 },
    { m: "Nov", edu: 30, pers: 16 },
    { m: "Dec", edu: 48, pers: 26 },
  ];

  // Loans list rows - match image with fallback to API data
  const baseLoans = [
    { id: "l1", name: "Personal Loan", time: "16 Mar 2024, 9:30 am", amount: "$4,200", status: "Applied" },
    { id: "l2", name: "Mortgage Loan", time: "16 Mar 2024, 9:30 am", amount: "$4,200", status: "Rejected" },
    { id: "l3", name: "Business Loan", time: "16 Mar 2024, 9:30 am", amount: "$4,200", status: "Applied" },
    { id: "l4", name: "Business Loan", time: "16 Mar 2024, 9:30 am", amount: "$4,200", status: "Applied" },
    { id: "l5", name: "Student Loan", time: "16 Mar 2024, 9:30 am", amount: "$4,200", status: "Applied" },
  ];

  // Map API activity into rows if available to keep it connected
  const dynamicRows = (data.activity || []).slice(0, 3).map((a, i) => {
    const isIncident = a.kind === "incident";
    return {
      id: "dyn-" + i,
      name: a.title,
      time: timeAgo(a.created_at),
      amount: isIncident ? "$12,500" : "$450",
      status: a.status === "resolved" || a.status === "submitted" || a.status === "applied" ? "Applied" : "Rejected"
    };
  });

  const allLoans = [...dynamicRows, ...baseLoans].slice(0, 5);

  const toggleSelect = (id) => {
    setSelectedLoans(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleSelectAll = (e) => {
    const checked = e.target.checked;
    const newSelects = {};
    if (checked) {
      allLoans.forEach(l => { newSelects[l.id] = true; });
    }
    setSelectedLoans(newSelects);
  };

  const isAllSelected = allLoans.length > 0 && allLoans.every(l => selectedLoans[l.id]);

  // Donut chart segments calculation
  // Total Circumference = 2 * Math.PI * 40 = 251.32
  const circ = 251.32;
  const donutSegments = [
    { label: "On Time", pct: 40, color: "#4f46e5", len: circ * 0.40, offset: 0 },
    { label: "Delayed", pct: 25, color: "#f59e0b", len: circ * 0.25, offset: -circ * 0.40 },
    { label: "Defaulted", pct: 20, color: "#ef4444", len: circ * 0.20, offset: -circ * 0.65 },
    { label: "Paid Off", pct: 15, color: "#10b981", len: circ * 0.15, offset: -circ * 0.85 }
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
      <!-- Left Column: Activity Chart & Loans List -->
      <div style=${{ display: "flex", flexDirection: "column", gap: "20px" }}>
        <!-- My Activity Chart -->
        <div class="block" style=${{ position: "relative" }}>
          <h3>
            <span>My Activity</span>
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
              <text x="30" y="44" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">$400,000</text>
              <text x="30" y="84" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">$320,000</text>
              <text x="30" y="124" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">$240,000</text>
              <text x="30" y="164" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">$120,000</text>
              <text x="30" y="204" text-anchor="end" fill="var(--muted)" font-size="10" font-weight="600">$0</text>
              
              <!-- Bars -->
              ${barData.map((b, idx) => {
                const totalH = 160; // Max height in px
                const maxVal = 76;  // Represents the max possible val (edu + pers max)
                const eduH = (b.edu / maxVal) * totalH;
                const persH = (b.pers / maxVal) * totalH;
                
                const colW = 16;
                const gap = (480) / 12;
                const x = 50 + idx * gap;
                const isHovered = hoveredBar === idx;
                const isSep = b.active;
                
                // Colors: highlighted is colored, others are muted pastel
                const eduColor = isSep || isHovered ? "#4f46e5" : "rgba(79, 70, 229, 0.15)";
                const persColor = isSep || isHovered ? "#fbbf24" : "rgba(251, 191, 36, 0.15)";
                
                return html`<g key=${idx} style=${{ cursor: "pointer" }} onMouseEnter=${() => setHoveredBar(idx)}>
                  <!-- Background thin full-height hover target -->
                  <rect x=${x - 8} y="20" width=${colW + 16} height="190" fill="transparent" />
                  
                  <!-- Stacked Bar (Education - bottom) -->
                  <rect 
                    x=${x} 
                    y=${200 - eduH} 
                    width=${colW} 
                    height=${eduH} 
                    fill=${eduColor} 
                    rx="3"
                  />
                  <!-- Stacked Bar (Personal - top) -->
                  <rect 
                    x=${x} 
                    y=${200 - eduH - persH} 
                    width=${colW} 
                    height=${persH} 
                    fill=${persColor} 
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
                <div class="chart-tooltip-title">${b.m} 2025</div>
                <div class="chart-tooltip-row">
                  <span>● Education</span>
                  <span class="chart-tooltip-val">$${(b.edu * 1000).toLocaleString()}</span>
                </div>
                <div class="chart-tooltip-row">
                  <span style=${{ color: "#fbbf24" }}>● Personal Loan</span>
                  <span class="chart-tooltip-val">$${(b.pers * 1000).toLocaleString()}</span>
                </div>
              </div>`;
            })() : null}
          </div>
        </div>

        <!-- Loans List Table -->
        <div class="block">
          <h3>
            <span>Loans List</span>
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
                  <th>Name</th>
                  <th>Time</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                ${allLoans.map((l) => html`<tr key=${l.id} class="table-row">
                  <td class="checkbox-cell">
                    <input type="checkbox" checked=${!!selectedLoans[l.id]} onChange=${() => toggleSelect(l.id)} />
                  </td>
                  <td style=${{ fontWeight: "700" }}>${l.name}</td>
                  <td style=${{ color: "var(--muted)", fontSize: "12.5px" }}>${l.time}</td>
                  <td style=${{ fontWeight: "700" }}>${l.amount}</td>
                  <td>
                    <span class=${"chip " + l.status.toLowerCase()}>${l.status}</span>
                  </td>
                </tr>`)}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Right Column: Borrower Insights, Investment, Recent Transactions -->
      <div style=${{ display: "flex", flexDirection: "column", gap: "20px" }}>
        <!-- Borrower Insights Donut Chart -->
        <div class="block">
          <h3>
            <span>Borrower Insights</span>
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
                <span style=${{ fontSize: "9px", color: "var(--muted)", fontWeight: "600", textTransform: "uppercase" }}>Total Loan</span>
                <span style=${{ fontSize: "13px", fontWeight: "800", color: "var(--txt)", marginTop: "2px" }}>$120,000</span>
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

        <!-- Investment Overview Line Chart -->
        <div class="block">
          <h3>
            <span>Investment Overview</span>
            <select style=${{ padding: "4px 8px", fontSize: "11px", borderRadius: "6px", background: "rgba(255,255,255,0.8)" }}>
              <option>Weekly</option>
              <option>Monthly</option>
            </select>
          </h3>
          
          <div style=${{ display: "flex", gap: "12px", fontSize: "11px", color: "var(--muted)", fontWeight: "700", margin: "4px 0 12px", justifyContent: "flex-end" }}>
            <div style=${{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style=${{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981" }}></span> Active Loans
            </div>
            <div style=${{ display: "flex", alignItems: "center", gap: "4px" }}>
              <span style=${{ width: "8px", height: "8px", borderRadius: "50%", background: "#4f46e5" }}></span> Total Invested
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
              <span>Oct, 2024</span>
              <span>Feb, 2025</span>
            </div>
          </div>
        </div>

        <!-- Recent Transactions -->
        <div class="block">
          <h3>Recent Transactions</h3>
          <div class="tx-list">
            <div class="tx-item">
              <div class="tx-icon" style=${{ color: "var(--accent-brand)", background: "rgba(79, 70, 229, 0.08)" }}>💼</div>
              <div class="tx-details">
                <div class="tx-title">Business Loan</div>
                <div class="tx-desc">Loan issued</div>
              </div>
              <div class="tx-amount" style=${{ color: "#0f172a" }}>$1,800</div>
            </div>
            
            <div class="tx-item">
              <div class="tx-icon" style=${{ color: "#fbbf24", background: "rgba(251, 191, 36, 0.08)" }}>⚡</div>
              <div class="tx-details">
                <div class="tx-title">Startup Loan</div>
                <div class="tx-desc">Partial repayment received</div>
              </div>
              <div class="tx-amount" style=${{ color: "#0f172a" }}>$2,300</div>
            </div>
            
            <div class="tx-item">
              <div class="tx-icon" style=${{ color: "#10b981", background: "rgba(16, 185, 129, 0.08)" }}>📄</div>
              <div class="tx-details">
                <div class="tx-title">Personal Loan</div>
                <div class="tx-desc">Loan request accepted</div>
              </div>
              <div class="tx-amount" style=${{ color: "#0f172a" }}>$500</div>
            </div>
          </div>
          
          <button class="btn-all-tx" onClick=${() => (window.location.hash = "#history")}>
            <span>All Transactions</span> ➔
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
      ${[["company", "By company"], ["field", "By field"], ["resume", "By resume"], ["rebuild", "Rebuild → email"]].map(([k, l]) =>
        html`<button key=${k} class=${"tab" + (mode === k ? " on" : "")} disabled=${running} onClick=${() => setMode(k)}>${l}</button>`)}
    </div>

    ${mode === "rebuild" ? html`<${ResumeRebuilder} />` : html`<div>
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

// Rebuild the user's resume for a target company/role and EMAIL it to them.
// No fabrication: the tailor re-emphasizes REAL experience and flags gaps.
function ResumeRebuilder() {
  const [me, setMe] = useState(null);
  const [resumeB64, setResumeB64] = useState("");
  const [resumeName, setResumeName] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [jd, setJd] = useState("");
  const [recipient, setRecipient] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");

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

  async function rebuild() {
    setErr(""); setRes(null);
    if (!company.trim()) { setErr("Enter a target company."); return; }
    if (!resumeB64 && !(me && me.has_resume)) { setErr("Upload a resume — none on file yet."); return; }
    setBusy(true);
    const payload = { company: company.trim(), role: role.trim(), job_description: jd.trim(), recipient: recipient.trim() };
    if (resumeB64) { payload.resume_b64 = resumeB64; payload.resume_name = resumeName; }
    try {
      const r = await fetch("/api/jobs/rebuild-resume", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const d = await r.json();
      if (!r.ok) setErr(d.error || "Rebuild failed");
      else { setRes(d); setMe((m) => (m ? { ...m, has_resume: true } : m)); }
    } catch (e) { setErr(String(e)); }
    setBusy(false);
  }

  const emailLine = (e) => ({
    sent: ["pass", `✓ Emailed to ${res.recipient} via ${e.provider}${(e.attached || []).length ? " — " + e.attached.join(", ") : ""}`],
    not_configured: ["warn", "✉ Email not configured (RESEND/SMTP empty) — download your resume below instead."],
    recipient_not_allowed: ["warn", `✉ ${e.detail}`],
    error: ["warn", `✉ Send failed — ${e.detail}`],
  }[e.status] || ["", ""]);

  return html`<div>
    <div class="block resolve-input">
      <div class="muted note">Tailor your resume to a company and email it to yourself (${me ? me.email : "your account"}). The tailor agent re-emphasizes your <b>real</b> experience — it never invents skills.</div>
      <div>
        <label class="filebtn">${me && me.has_resume ? "Replace resume (optional)" : "Upload resume (PDF / DOCX)"}<input type="file" accept=".pdf,.docx,.txt" onChange=${onResume} /></label>
        ${resumeName ? html`<span class="muted"> ${resumeName}</span>`
          : me && me.has_resume ? html`<span class="muted"> reusing the resume already on file</span>`
          : html`<span class="muted"> required the first time</span>`}
      </div>
      <div class="fields" style=${{ marginTop: "12px" }}>
        <label>Target company <input value=${company} placeholder="e.g. Stripe" onInput=${(e) => setCompany(e.target.value)} /></label>
        <label>Role (optional) <input value=${role} placeholder="e.g. Backend Engineer" onInput=${(e) => setRole(e.target.value)} /></label>
      </div>
      <div class="resolve-input" style=${{ marginTop: "12px" }}>
        <label class="muted" style=${{ fontSize: "11px", letterSpacing: ".5px" }}>Job description / key requirements (optional — improves targeting & gap analysis)</label>
        <textarea rows="4" style=${{ width: "100%", marginTop: "6px" }} value=${jd} placeholder="Paste the posting or key requirements…" onInput=${(e) => setJd(e.target.value)}></textarea>
      </div>
      <div class="fields" style=${{ marginTop: "12px" }}>
        <label>Email to <input value=${recipient} onInput=${(e) => setRecipient(e.target.value)} /></label>
      </div>
    </div>

    <div class="section-head">
      <div class="status"><span class=${"dot" + (busy ? " live" : "")}></span>${busy ? "tailoring…" : res ? "done" : "idle"}</div>
      <div class="spacer"></div>
      <button class="run" onClick=${rebuild} disabled=${busy}>${busy ? "Rebuilding…" : "Rebuild & email"}</button>
    </div>

    ${err ? html`<div class="empty" style=${{ borderColor: "var(--reject)", color: "var(--reject)" }}>${err}</div>` : null}

    ${res ? html`<div>
      <div class="verdict">
        <div class="vhead">RESUME TAILORED — ${res.role || "role"} @ ${res.company}</div>
        <div class="grid">
          <div class="cell"><div class="k">Emphasized (your real skills)</div><div class="v" style=${{ fontSize: "14px" }}>${(res.emphasized || []).join(", ") || "—"}</div></div>
          <div class="cell"><div class="k">Downloads</div><div class="v dlrow" style=${{ fontSize: "12px" }}>
            ${["pdf", "docx", "md"].filter((x) => res.files && res.files[x]).map((x) => html`<a key=${x} class="dlbtn" href=${dl(res.files[x])}>${x.toUpperCase()}</a>`)}
          </div></div>
        </div>
      </div>
      ${(res.gaps || []).length ? html`<div class="block" style=${{ marginTop: "14px", borderColor: "#5a4a1f" }}>
        <h3 style=${{ color: "var(--warn)" }}>Gaps to consider — NOT added to your resume</h3>
        <p class="muted">The posting mentions these, but they weren't found on your resume. They were deliberately <b>not</b> written in — add them only if you genuinely have the experience:</p>
        <div class="facts">${res.gaps.map((g) => html`<span key=${g} class="pill warn">${g}</span>`)}</div>
      </div>` : null}
      ${res.email ? html`<div class=${"emailbar " + emailLine(res.email)[0]} style=${{ marginTop: "12px" }}>${emailLine(res.email)[1]}</div>` : null}
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
      <!-- Lendo Top Header Bar -->
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
      <${Comp} />
    </main>
  </div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
