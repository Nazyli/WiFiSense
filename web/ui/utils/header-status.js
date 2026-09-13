// web/ui/utils/header-status.js — FE header global brand-tagline live status
// Polls /health (fallback /api/v1/status) every 2s and injects formatted status into
//   #brand-tagline (observatory.html), #viz-container top (viz.html), header (index.html).
// Format: "FLAMBOYAN'S → 192.168.1.75:5005 · ESP 192.168.1.92:53083 · RSSI -53dBm var1.67 pps13 LIVE" (green) / SIMULATED (red)
// Never hardcodes SSID — falls back to data.ssid only.

const POLL_MS = 2000;
const ENDPOINTS = ['/health', '/api/v1/status'];
let _timer = null;
let _el = null;

function isLiveData(d) {
  if (!d) return false;
  const src = (d.source || '').toLowerCase();
  const st = (d.source_state || '').toLowerCase();
  if (st === 'live_verified' || st === 'live_unverified') return true;
  if (st === 'synthetic') return false;
  if (src === 'esp32' || src === 'wifi' || src === 'live') return true;
  if (src === 'simulated' || src === 'simulate') return false;
  // _simulated flag
  if (d._simulated === false) return true;
  if (d._simulated === true) return false;
  // heuristic: if pps>0 and lastFrom present and source not simulated -> live
  return false;
}

function fmtNum(v, digits) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '--';
  return Number(v).toFixed(digits);
}

function buildText(d) {
  // Don't hardcode ssid — use server value, fallback to placeholder only if missing
  const ssid = d.ssid || d.SSID || '—';
  const targetIp = d.targetIp || d.target_ip || d.targetIP || '192.168.1.75';
  const targetPort = d.targetPort ?? d.target_port ?? d.target_port ?? 5005;
  const lastFrom = d.lastFrom || d.last_from || d.lastfrom || '—';
  const rssi = d.rssi ?? d.mean_rssi ?? '--';
  const variance = d.variance ?? d.var ?? 0;
  const pps = d.pps ?? d.PPS ?? 0;
  const live = isLiveData(d);
  const rssiStr = (rssi === '--' || rssi === null) ? '--' : String(Math.round(Number(rssi)));
  const varStr = (variance === null || variance === undefined) ? '--' : Number(variance).toFixed(2);
  const ppsStr = String(pps ?? 0);
  const stateLabel = live ? 'LIVE' : 'SIMULATED';
  // ESP part: if lastFrom is "—" still show placeholder to keep layout stable
  const espPart = lastFrom && lastFrom !== '—' ? `ESP ${lastFrom}` : 'ESP —';
  return `${ssid} \u2192 ${targetIp}:${targetPort} \u00B7 ${espPart} \u00B7 RSSI ${rssiStr}dBm var${varStr} pps${ppsStr} ${stateLabel}`;
}

function ensureStyle() {
  if (document.getElementById('header-status-style')) return;
  const s = document.createElement('style');
  s.id = 'header-status-style';
  s.textContent = `
#brand-tagline.header-live { color:#00e676 !important; text-shadow:0 0 8px rgba(0,230,118,0.35); }
#brand-tagline.header-sim { color:#ff3d57 !important; text-shadow:0 0 8px rgba(255,61,87,0.3); }
#header-status.header-live, #header-status-viz.header-live { color:#00e676; border-color:rgba(0,230,118,0.35) !important; }
#header-status.header-sim, #header-status-viz.header-sim { color:#ff3d57; border-color:rgba(255,61,87,0.35) !important; }
#header-status-viz { font-variant-ligatures:none; }
`;
  document.head.appendChild(s);
}

function ensureTarget() {
  if (_el && document.contains(_el)) return _el;
  // 1) observatory.html
  let el = document.getElementById('brand-tagline');
  if (el) {
    _el = el;
    return el;
  }
  // 2) viz or index injected elements
  el = document.getElementById('header-status');
  if (el) { _el = el; return el; }
  el = document.getElementById('header-status-viz');
  if (el) { _el = el; return el; }

  const vizContainer = document.getElementById('viz-container');
  if (vizContainer) {
    el = document.createElement('div');
    el.id = 'header-status-viz';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    el.style.cssText = 'position:absolute;top:10px;left:16px;z-index:500;font:600 11px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:0.04em;padding:6px 10px;border-radius:6px;background:rgba(0,0,0,0.62);border:1px solid rgba(255,255,255,0.12);backdrop-filter:blur(6px);max-width:92vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
    // Insert as first child so it sits above canvas but below overlay? keep visible during loading too
    vizContainer.prepend(el);
    _el = el;
    return el;
  }

  const hdr = document.querySelector('header.header');
  if (hdr) {
    el = document.createElement('div');
    el.id = 'header-status';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    el.style.cssText = 'margin-top:8px;font:600 12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:0.04em;padding:6px 10px;border-radius:6px;background:rgba(0,0,0,0.06);border:1px solid rgba(0,0,0,0.12);display:inline-block;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
    const subtitle = hdr.querySelector('.subtitle');
    if (subtitle && subtitle.parentNode) subtitle.insertAdjacentElement('afterend', el);
    else hdr.appendChild(el);
    _el = el;
    return el;
  }

  // Fallback fixed top bar
  el = document.createElement('div');
  el.id = 'ruview-header-status';
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');
  el.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;text-align:center;padding:5px 10px;font:600 11px ui-monospace,monospace;letter-spacing:0.04em;background:rgba(0,0,0,0.7);border-bottom:1px solid rgba(255,255,255,0.12);';
  document.body.prepend(el);
  _el = el;
  return el;
}

async function fetchHealth() {
  for (const ep of ENDPOINTS) {
    try {
      const res = await fetch(ep, { cache: 'no-store', headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        const data = await res.json();
        return data;
      }
    } catch (_) { /* try next */ }
  }
  return null;
}

async function tick() {
  const el = ensureTarget();
  if (!el) return;
  const data = await fetchHealth();
  if (!data) {
    // offline: keep previous text but mark simulated/red
    el.textContent = el.textContent || '— → — · ESP — · RSSI --dBm var-- pps-- SIMULATED';
    el.classList.remove('header-live');
    el.classList.add('header-sim');
    // also set color fallback inline for viz/index where class may not apply to color via !important only brand-tagline
    if (el.id !== 'brand-tagline') el.style.color = '#ff3d57';
    el.title = 'offline — /health unreachable';
    return;
  }
  const live = isLiveData(data);
  const text = buildText(data);
  el.textContent = text;
  el.title = JSON.stringify({ ssid: data.ssid, targetIp: data.targetIp, lastFrom: data.lastFrom, rssi: data.rssi, variance: data.variance, pps: data.pps, source: data.source, source_state: data.source_state }, null, 0);
  el.classList.toggle('header-live', live);
  el.classList.toggle('header-sim', !live);
  // For brand-tagline the CSS class controls color; for viz/index also set inline as backup
  if (el.id === 'brand-tagline') {
    el.style.color = live ? '#00e676' : '#ff3d57';
  } else {
    el.style.color = live ? '#00e676' : '#ff3d57';
  }
}

export function initHeaderStatus(opts = {}) {
  const interval = opts.intervalMs || POLL_MS;
  if (_timer) clearInterval(_timer);
  ensureStyle();
  ensureTarget();
  // immediate
  tick();
  _timer = setInterval(tick, interval);
  // also re-ensure target on resize/navigation
  window.addEventListener('focus', tick);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  return () => { if (_timer) clearInterval(_timer); _timer = null; };
}

// Auto-init when loaded as <script type="module" src=".../header-status.js">
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initHeaderStatus());
  } else {
    initHeaderStatus();
  }
}
