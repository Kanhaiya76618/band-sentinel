// Runtime API base for the SPA. Empty = same-origin (single-host deploy).
// On Vercel this file is rewritten at build time from the AEGIS_API_BASE env var
// to point at the Railway backend, e.g. window.AEGIS_API_BASE="https://xxx.up.railway.app".
window.AEGIS_API_BASE = "";
