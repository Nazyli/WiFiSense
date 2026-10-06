// Quick Settings Panel - Centralized configuration for all UI features
// Accessible via gear icon in header — WiFi moved to its own wifi-gear/panel

import { apiService, API_TOKEN_STORAGE_KEY } from '../services/api.service.js';
import { API_CONFIG } from '../config/api.config.js';

// ── WifiSettings — standalone gear + panel (sebelah settings-gear) ───────
export class WifiSettings {
  constructor(app) {
    this.app = app;
    this.wifiButton = null;
    this.wifiPanel = null;
    this.isWifiOpen = false;
    this.EXPECTED_TARGET_IP = '192.168.1.75';
    this._actualLocalIp = null;
    this.WIFI_DRAFT_KEY = 'wifisense-wifi-draft';
    this._lastHealthTargetIp = null;
    this.wifiDraft = this.getDefaultWifiDraft();
    this.wifiTest = { running: false, lastPps: 0, lastFrom: null, pass: null };
    this._outsideHandler = null;
    this._liveData = { pps: null, variance: null, presence: null, reachable: false };
    this._livePollTimer = null;
    this.loadWifiDraft();
  }

  init() {
    this.createButton();
    this.createPanel();
  }

  // ── WiFi helpers (ported from SettingsPanel.js) ────────────────────────
  getDefaultWifiDraft() {
    return {
      mode: 'wifi',
      ssid: '',
      password: '',
      channel: 'auto',
      hop: false,
      targetIp: this._actualLocalIp || this.EXPECTED_TARGET_IP || '192.168.1.75',
      comPort: '',
      edgeTier: 1
    };
  }

  loadWifiDraft() {
    try {
      const keys = [
        this.WIFI_DRAFT_KEY,
        'wifisense-wifi-draft-quick-settings',
        'wifi-draft-quick-settings',
        'wifiDraft',
        'wifisense-wifi-draft-settings-panel',
        'wifi-draft-settings-panel'
      ];
      let raw = null;
      for (const k of keys) {
        const v = localStorage.getItem(k);
        if (v) { raw = v; break; }
      }
      if (!raw) {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.startsWith('wifisense-wifi-draft-')) { raw = localStorage.getItem(k); break; }
        }
      }
      if (raw) {
        const parsed = JSON.parse(raw);
        this.wifiDraft = { ...this.getDefaultWifiDraft(), ...parsed };
        if (!['wifi', 'channel'].includes(this.wifiDraft.mode)) this.wifiDraft.mode = 'wifi';
        const ch = String(this.wifiDraft.channel);
        const validCh = ['1', '6', '11', 'auto', 'all'];
        if (!validCh.includes(ch)) {
          this.wifiDraft.channel = this.wifiDraft.mode === 'channel' ? 'all' : 'auto';
        }
        if (this.wifiDraft.mode === 'channel' && this.wifiDraft.channel === 'auto') this.wifiDraft.channel = 'all';
        // Additive merge for edgeTier — default 1 if missing or invalid
        const t = this.wifiDraft.edgeTier;
        const n = Number(t);
        if (t == null || t === '' || Number.isNaN(n) || ![0, 1, 2].includes(n)) {
          this.wifiDraft.edgeTier = 1;
        } else {
          this.wifiDraft.edgeTier = n;
        }
      } else {
        // No draft found — ensure default edgeTier
        if (this.wifiDraft.edgeTier == null) this.wifiDraft.edgeTier = 1;
      }
    } catch { /* noop */ }
  }

  saveWifiDraft() {
    try {
      const s = JSON.stringify(this.wifiDraft);
      localStorage.setItem(this.WIFI_DRAFT_KEY, s);
      try { localStorage.setItem('wifisense-wifi-draft-quick-settings', s); } catch {}
      try { localStorage.setItem('wifiDraft', s); } catch {}
      try { localStorage.setItem('wifisense-wifi-draft-settings-panel', s); } catch {}
    } catch { /* noop */ }
  }

  updateWifiDraftField(key, value) {
    this.wifiDraft[key] = value;
    this.saveWifiDraft();
    this.updateWifiMismatchBadge();
  }

  updateWifiMismatchBadge() {
    if (this.wifiDraft.mode === 'channel') return;
    const mismatchBadge = this.wifiPanel?.querySelector('#qs-wifi-mismatch-badge');
    const matchBadge = this.wifiPanel?.querySelector('#qs-wifi-match-badge');
    if (!mismatchBadge || !matchBadge) return;
    const expectedIp = (this._actualLocalIp || this.EXPECTED_TARGET_IP || '').trim();
    const targetIp = (this.wifiDraft.targetIp || expectedIp).trim();
    const liveTarget = this._lastHealthTargetIp ? String(this._lastHealthTargetIp).trim() : null;
    const effectiveTarget = liveTarget || targetIp;
    const isMismatch = effectiveTarget !== expectedIp;
    const showMismatch = isMismatch;
    // Auto-migrate stale draft (e.g. old 192.168.1.75) when backend already correct
    if (targetIp !== expectedIp && !isMismatch) {
      this.wifiDraft.targetIp = expectedIp;
      this.saveWifiDraft();
    }
    mismatchBadge.style.display = showMismatch ? 'inline-flex' : 'none';
    matchBadge.style.display = showMismatch ? 'none' : 'inline-flex';
    const ipInput = this.wifiPanel.querySelector('#qs-wifi-target-ip');
    if (ipInput) {
      ipInput.value = expectedIp;
      ipInput.title = showMismatch ? `Mismatch: expected ${expectedIp} got ${effectiveTarget}` : 'MATCH';
      ipInput.style.borderColor = showMismatch ? 'rgba(239,68,68,0.8)' : '';
    }
    this.updateDynamicTargetIpHint();
  }

  updateDynamicTargetIpHint() {
    if (!this.wifiPanel) return;
    const expectedIp = this._actualLocalIp || this.EXPECTED_TARGET_IP;
    // Update the Target IP instruction code tag (step 2) that hardcodes 192.168.1.75:5005
    const step2 = this.wifiPanel.querySelector('#qs-wifi-step-2');
    if (step2) {
      const codeEls = step2.querySelectorAll('code');
      // first code is the target ip:port
      if (codeEls && codeEls.length > 0) {
        const firstCode = codeEls[0];
        if (firstCode.textContent.includes(':5005') || firstCode.textContent.match(/\d+\.\d+\.\d+\.\d+/)) {
          firstCode.textContent = `${expectedIp}:5005`;
        }
      }
    }
  }

  async fetchSerialPorts() {
    const sel = this.wifiPanel?.querySelector('#qs-wifi-com-port');
    const status = this.wifiPanel?.querySelector('#qs-wifi-status');
    if (!sel) return;
    try {
      if (status) status.textContent = 'Memuat daftar COM...';
      const url = `${API_CONFIG.BASE_URL}/api/v1/serial/ports`;
      const resp = await fetch(url, { headers: { Accept: 'application/json' } });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json().catch(() => ({}));
      let ports = [];
      if (Array.isArray(data)) ports = data;
      else if (Array.isArray(data.ports)) ports = data.ports;
      else if (Array.isArray(data.data)) ports = data.data;
      else if (Array.isArray(data.result)) ports = data.result;
      else if (data.port) ports = [data.port];
      if (!ports.length && Array.isArray(data.comPorts)) ports = data.comPorts;
      ports = ports.map(p => typeof p === 'string' ? p : (p.port || p.name || p.path || String(p))).filter(Boolean);
      const prev = this.wifiDraft.comPort;
      sel.innerHTML = '<option value="">-- pilih COM --</option>' + ports.map(p => `<option value="${p}">${p}</option>`).join('');
      if (prev && ports.includes(prev)) sel.value = prev;
      else if (prev) {
        const opt = document.createElement('option');
        opt.value = prev; opt.textContent = `${prev} (draft)`;
        sel.appendChild(opt);
        sel.value = prev;
      }
      if (!ports.length) {
        if (status) status.textContent = 'Tidak ada COM terdeteksi (colok USB S3 dahulu)';
      } else {
        if (status) status.textContent = `${ports.length} port ditemukan`;
        setTimeout(() => { if (status && status.textContent.includes('ditemukan')) status.textContent = ''; }, 3000);
      }
      this.updateWifiRetargetState();
    } catch (e) {
      if (sel.options.length <= 1 && this.wifiDraft.comPort) {
        sel.innerHTML = `<option value="">-- pilih COM --</option><option value="${this.wifiDraft.comPort}" selected>${this.wifiDraft.comPort} (draft)</option>`;
      }
      const statusEl = this.wifiPanel?.querySelector('#qs-wifi-status');
      if (statusEl) statusEl.textContent = `Gagal muat COM: ${e.message}`;
    }
  }

  async fetchNetworkIp() {
    // Fetch dynamic laptop IP from backend — replaces hardcoded EXPECTED_TARGET_IP
    try {
      const url = `${API_CONFIG.BASE_URL}/api/v1/network/local-ip`;
      const resp = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (resp.ok) {
        const j = await resp.json().catch(() => null);
        if (j) {
          const localIp = j.localIp || j.local_ip || j.localIP || j.ip || j.laptop_ip || null;
          const targetIp = j.targetIp || j.target_ip || j.targetIP || j.target_ip_address || null;
          if (localIp) this._actualLocalIp = String(localIp).trim();
          if (targetIp) this._lastHealthTargetIp = String(targetIp).trim();
          // Some backends return only one field; keep them in sync when only one present
          if (!this._lastHealthTargetIp && this._actualLocalIp) this._lastHealthTargetIp = this._actualLocalIp;
          if (!this._actualLocalIp && this._lastHealthTargetIp) this._actualLocalIp = this._lastHealthTargetIp;
        }
      }
    } catch { /* noop */ }
    // Also fetch /health/health for live targetIp (and keep localIp if already fetched) + live telemetry
    let healthOk = false;
    try {
      const url2 = `${API_CONFIG.BASE_URL}/health/health`;
      const resp2 = await fetch(url2, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (resp2.ok) {
        const data = await resp2.json().catch(() => null);
        if (data) {
          healthOk = true;
          if (data.targetIp) this._lastHealthTargetIp = String(data.targetIp).trim();
          else if (data.target_ip) this._lastHealthTargetIp = String(data.target_ip).trim();
          // Health may also expose localIp in some builds
          const hLocal = data.localIp || data.local_ip || data.laptop_ip || data.laptopIp || null;
          if (hLocal) this._actualLocalIp = String(hLocal).trim();
          if (!this._actualLocalIp && this._lastHealthTargetIp) {
            // Do not overwrite if we already have a localIp; otherwise keep null so badge falls back to expected
            // Leave _actualLocalIp as-is to allow fallback to EXPECTED_TARGET_IP for backwards compat
          }
          // Live telemetry for mini-bar
          const ppsRaw = data.pps ?? data.metrics?.pps ?? data.pps_value ?? null;
          const varRaw = data.variance ?? data.var ?? data.metrics?.variance ?? data.metrics?.var ?? data.variance_value ?? null;
          const presRaw = data.presence ?? data.presence_detected ?? data.occupied ?? data.metrics?.presence ?? data.metrics?.occupied ?? null;
          this._liveData.pps = ppsRaw != null ? Number(ppsRaw) : null;
          this._liveData.variance = varRaw != null ? Number(varRaw) : null;
          if (typeof presRaw === 'boolean') this._liveData.presence = presRaw;
          else if (presRaw != null) this._liveData.presence = presRaw === true || presRaw === 1 || String(presRaw).toLowerCase() === 'true';
          else this._liveData.presence = null;
          this._liveData.reachable = true;
        }
      } else {
        // Try fallback /health if /health/health not ok
        try {
          const fallbackUrl = `${API_CONFIG.BASE_URL}/health`;
          const r3 = await fetch(fallbackUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
          if (r3.ok) {
            const d3 = await r3.json().catch(() => null);
            if (d3) {
              healthOk = true;
              const ppsRaw = d3.pps ?? d3.metrics?.pps ?? null;
              const varRaw = d3.variance ?? d3.var ?? d3.metrics?.variance ?? null;
              const presRaw = d3.presence ?? d3.presence_detected ?? d3.occupied ?? d3.metrics?.presence ?? null;
              this._liveData.pps = ppsRaw != null ? Number(ppsRaw) : null;
              this._liveData.variance = varRaw != null ? Number(varRaw) : null;
              if (typeof presRaw === 'boolean') this._liveData.presence = presRaw;
              else if (presRaw != null) this._liveData.presence = presRaw === true || presRaw === 1 || String(presRaw).toLowerCase() === 'true';
              else this._liveData.presence = null;
              this._liveData.reachable = true;
              if (d3.targetIp) this._lastHealthTargetIp = String(d3.targetIp).trim();
              else if (d3.target_ip) this._lastHealthTargetIp = String(d3.target_ip).trim();
            }
          }
        } catch { /* noop */ }
      }
      if (!healthOk) {
        this._liveData.reachable = false;
      }
    } catch {
      this._liveData.reachable = false;
    }
    // If we now have a dynamic IP and draft still holds the old hardcoded value, sync draft
    if (this._actualLocalIp) {
      const expected = this._actualLocalIp.trim();
      // If draft was still the old hardcoded .75 and backend says different, keep draft in sync for display?
      // Only auto-correct if draft matches old hardcoded and live differs — ensures MISMATCH badge clears after backend fixed
      // But do not overwrite user-edited draft arbitrarily; update only the stored comparison basis via _actualLocalIp
      this.updateWifiMismatchBadge();
    } else {
      this.updateWifiMismatchBadge();
    }
    this.updateWifiLiveBar();
  }

  async refreshWifiHealth() {
    await this.fetchNetworkIp();
  }

  updateWifiLiveBar() {
    const el = this.wifiPanel?.querySelector('#qs-wifi-live-bar');
    if (!el) return;
    if (!this._liveData.reachable) {
      el.textContent = 'pps -- | var -- | presence --';
      el.style.color = '#6b7a8d';
      el.style.background = 'rgba(15,20,35,0.4)';
      el.style.borderColor = 'rgba(56,68,89,0.3)';
      return;
    }
    const pps = this._liveData.pps != null && !Number.isNaN(this._liveData.pps) ? String(this._liveData.pps) : '--';
    let varText = '--';
    if (this._liveData.variance != null && !Number.isNaN(this._liveData.variance)) {
      const v = this._liveData.variance;
      varText = Number.isInteger(v) ? String(v) : v.toFixed(2);
    }
    const presence = this._liveData.presence;
    const dot = presence ? '●' : '○';
    const presenceText = presence == null ? '--' : (presence ? 'yes' : 'no');
    el.textContent = `pps ${pps} | var ${varText} | presence ${dot} ${presenceText}`;
    if (presence === true) {
      el.style.color = '#4ade80';
      el.style.background = 'rgba(34,197,94,0.12)';
      el.style.borderColor = 'rgba(34,197,94,0.4)';
    } else if (presence === false) {
      el.style.color = '#9ca3af';
      el.style.background = 'rgba(15,20,35,0.4)';
      el.style.borderColor = 'rgba(56,68,89,0.3)';
    } else {
      el.style.color = '#c8d0dc';
      el.style.background = 'rgba(15,20,35,0.4)';
      el.style.borderColor = 'rgba(56,68,89,0.3)';
    }
  }

  updateSsidGuard() {
    const warn = this.wifiPanel?.querySelector('#qs-wifi-ssid-warn');
    const ssidEl = this.wifiPanel?.querySelector('#qs-wifi-ssid');
    if (!warn || !ssidEl) return;
    const v = String(ssidEl.value || this.wifiDraft.ssid || '').toLowerCase();
    const show = v.includes('_5ghz') || v.includes('5g');
    warn.style.display = show ? 'block' : 'none';
  }

  updateWifiRetargetState() {
    const btn = this.wifiPanel?.querySelector('#qs-wifi-retarget');
    if (!btn) return;
    if (this.wifiDraft.mode === 'channel') {
      btn.style.display = 'none';
      return;
    }
    btn.style.display = '';
    const hasCom = !!(this.wifiDraft.comPort && String(this.wifiDraft.comPort).trim());
    btn.disabled = !hasCom;
    btn.title = hasCom ? '1-klik Re-target laptop IP (butuh COM nyambung)' : 'Pilih COM port dahulu (butuh COM nyambung)';
    btn.style.opacity = hasCom ? '1' : '0.5';
    btn.style.cursor = hasCom ? 'pointer' : 'not-allowed';
  }

  setWifiStatus(msg, isError = false) {
    const el = this.wifiPanel?.querySelector('#qs-wifi-status');
    if (!el) return;
    el.textContent = msg || '';
    el.style.color = isError ? '#ef4444' : '#6b7a8d';
    if (msg) el.style.display = 'block';
  }

  renderWifiTestBadge({ pass, pps, from, source }) {
    const badge = this.wifiPanel?.querySelector('#qs-wifi-test-badge');
    if (!badge) return;
    const ip = from ? String(from).split(':')[0] : '192.168.1.92';
    const ppsVal = (pps != null ? pps : (this.wifiTest.lastPps || 0));
    const label = pass ? 'PASS' : 'FAIL';
    const connectedText = pass ? `Connected ESP ${ip} pps ${ppsVal} ${label}` : `FAIL pps ${ppsVal} ${label}`;
    badge.textContent = source ? `${connectedText} (${source})` : connectedText;
    badge.style.display = 'inline-flex';
    badge.style.background = pass ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)';
    badge.style.borderColor = pass ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)';
    badge.style.color = pass ? '#4ade80' : '#f87171';
  }

  async handleWifiTestDryRun() {
    const btn = this.wifiPanel?.querySelector('#qs-wifi-test');
    const badge = this.wifiPanel?.querySelector('#qs-wifi-test-badge');
    if (this.wifiTest.running) return;
    if (this.wifiDraft.mode === 'channel') {
      const com = (this.wifiDraft.comPort || '').trim();
      if (!com) {
        this.setWifiStatus('Pilih COM port dulu untuk Sniff Channel', true);
        this.renderWifiTestBadge({ pass: false, pps: 0, from: null, source: null });
        return;
      }
    } else {
      const ssid = (this.wifiDraft.ssid || '').trim();
      if (!ssid) {
        this.setWifiStatus('Isi SSID dulu sebelum Test', true);
        this.renderWifiTestBadge({ pass: false, pps: 0, from: null, source: null });
        return;
      }
    }
    this.wifiTest.running = true;
    if (btn) { btn.disabled = true; btn.textContent = 'Testing… 8s'; }
    if (badge) badge.style.display = 'none';
    this.setWifiStatus('Test dry-run: polling GET /health/health 8s pps>0 ...');
    this.saveWifiDraft();
    const start = Date.now();
    const durationMs = 8000;
    const intervalMs = 700;
    let best = { pps: 0, from: null, source: null, pass: false };
    let lastHealth = null;
    const pollOnce = async () => {
      try {
        const url = `${API_CONFIG.BASE_URL}/health/health`;
        const r = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
        if (!r.ok) return null;
        const j = await r.json().catch(() => null);
        return j;
      } catch { return null; }
    };
    try {
      while (Date.now() - start < durationMs) {
        const h = await pollOnce();
        if (h) {
          lastHealth = h;
          const pps = Number(h.pps ?? h.metrics?.pps ?? 0);
          const from = h.lastFrom || h.last_from || null;
          const source = h.source || h.status || null;
          if (pps > best.pps) best = { pps, from, source, pass: pps > 0 };
          if (pps > 0) {
            best.pass = true;
            best.pps = pps;
            best.from = from || best.from;
            best.source = source;
          }
          if (h.targetIp) this._lastHealthTargetIp = String(h.targetIp).trim();
          else if (h.target_ip) this._lastHealthTargetIp = String(h.target_ip).trim();
        }
        const remain = Math.max(0, Math.ceil((durationMs - (Date.now() - start)) / 1000));
        if (btn) {
          btn.textContent = `Testing… ${remain}s`;
        }
        this.setWifiStatus(`Test dry-run polling... ${remain}s pps=${best.pps} from=${best.from || '-'}`);
        await new Promise(res => setTimeout(res, intervalMs));
      }
      if (!lastHealth) {
        this.wifiTest.lastPps = 0;
        this.wifiTest.lastFrom = null;
        this.wifiTest.pass = false;
        this.renderWifiTestBadge({ pass: false, pps: 0, from: null, source: null });
        this.setWifiStatus('Dry-run FAIL — server tidak reachable (cek uvicorn :3000 & CORS)', true);
        this.updateWifiMismatchBadge();
      } else {
        const pass = best.pass && best.pps > 0;
        const finalPps = best.pps || Number(lastHealth.pps ?? lastHealth.metrics?.pps ?? 0);
        const finalSource = best.source || lastHealth.source || null;
        let finalFrom = best.from || (lastHealth.lastFrom || lastHealth.last_from || null);
        if (!finalFrom && finalSource === 'serial') {
          const com = (this.wifiDraft.comPort || '').trim();
          finalFrom = com ? `serial:${com}` : 'serial';
        }
        if (!finalFrom) finalFrom = '192.168.1.92';
        this.wifiTest.lastPps = finalPps;
        this.wifiTest.lastFrom = finalFrom;
        this.wifiTest.pass = pass;
        this.renderWifiTestBadge({ pass, pps: finalPps, from: finalFrom, source: finalSource });
        if (pass) {
          this.setWifiStatus(`Dry-run PASS — Connected ESP ${String(finalFrom).split(':')[0]} pps ${finalPps}`);
        } else {
          this.setWifiStatus(`Dry-run FAIL — pps ${finalPps} (cek ESP 192.168.1.92 & USB)`, true);
        }
        this.updateWifiMismatchBadge();
      }
    } finally {
      this.wifiTest.running = false;
      if (btn) { btn.disabled = false; btn.textContent = 'Test (dry-run)'; }
    }
  }

  async handleWifiApply() {
    const btn = this.wifiPanel?.querySelector('#qs-wifi-apply');
    if (btn) { btn.disabled = true; btn.textContent = 'Applying…'; }
    this.setWifiStatus('Apply (provision real) → POST ...');
    this.saveWifiDraft();
    let payload;
    const tier = Number(this.wifiDraft.edgeTier ?? 1);
    const tierSafe = [0, 1, 2].includes(tier) ? tier : 1;
    if (this.wifiDraft.mode === 'channel') {
      const chRaw = String(this.wifiDraft.channel);
      const chEff = chRaw === 'auto' ? 'all' : chRaw;
      const com = this.wifiDraft.comPort;
      if (chEff === 'all') {
        payload = { mode: 'channel', channel: null, hop: true, hop_channels: '1,6,11', port: com, comPort: com, dryRun: false, edge_tier: tierSafe, edgeTier: tierSafe };
      } else {
        payload = { mode: 'channel', channel: Number(chEff), hop: null, hop_channels: null, port: com, comPort: com, dryRun: false, edge_tier: tierSafe, edgeTier: tierSafe };
      }
    } else {
      payload = {
        mode: 'wifi',
        ssid: this.wifiDraft.ssid,
        password: this.wifiDraft.password,
        channel: null,
        hop: null,
        hop_channels: null,
        target_ip: this.wifiDraft.targetIp || this._actualLocalIp || this.EXPECTED_TARGET_IP,
        targetIp: this.wifiDraft.targetIp || this._actualLocalIp || this.EXPECTED_TARGET_IP,
        comPort: this.wifiDraft.comPort,
        port: this.wifiDraft.comPort,
        dryRun: false,
        edge_tier: tierSafe,
        edgeTier: tierSafe
      };
    }
    const endpoints = [
      '/api/v1/config/apply',
      '/api/v1/config/provision',
      '/api/v1/config/wifi',
      '/api/v1/serial/provision'
    ];
    let ok = false; let lastErr = null; let respJson = null;
    for (const ep of endpoints) {
      try {
        const url = `${API_CONFIG.BASE_URL}${ep}`;
        const r = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(payload)
        });
        const j = await r.json().catch(() => ({}));
        if (r.ok) { ok = true; respJson = j; break; }
        lastErr = j.message || j.error || j.detail || `HTTP ${r.status}`;
        if (r.status === 404 || r.status === 405) continue;
        else break;
      } catch (e) {
        lastErr = e.message;
      }
    }
    if (ok) {
      this.setWifiStatus(`Apply OK — ${respJson?.message || 'provision queued'}`);
    } else {
      this.setWifiStatus(`Apply gagal: ${lastErr || 'BE belum siap (lane lain)'} — draft tetap tersimpan di localStorage`, true);
    }
    if (btn) { btn.disabled = false; btn.textContent = 'Apply'; }
  }

  async handleWifiReTarget() {
    const btn = this.wifiPanel?.querySelector('#qs-wifi-retarget');
    const com = (this.wifiDraft.comPort || '').trim();
    if (!com) {
      this.setWifiStatus('Re-target butuh COM nyambung — pilih COMx dahulu', true);
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = 'Re-targeting…'; }
    this.setWifiStatus('1-klik Re-target laptop IP → POST /api/v1/config/re-target ...');
    const effectiveIp = this._actualLocalIp || this.EXPECTED_TARGET_IP;
    const payload = {
      port: com,
      comPort: com,
      targetIp: effectiveIp,
      target_ip: effectiveIp
    };
    try {
      const url = `${API_CONFIG.BASE_URL}/api/v1/config/re-target`;
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(payload)
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.message || j.error || j.detail || `HTTP ${r.status}`);
      const newIp = j.localIp || j.local_ip || j.localIP || j.targetIp || j.target_ip || j.targetIP || j.laptop_ip || j.laptopIp || this._actualLocalIp || this.EXPECTED_TARGET_IP;
      this.wifiDraft.targetIp = String(newIp).trim();
      // Keep dynamic cache in sync with backend response
      if (j.localIp || j.local_ip || j.localIP || j.laptop_ip || j.laptopIp) {
        this._actualLocalIp = String(j.localIp || j.local_ip || j.localIP || j.laptop_ip || j.laptopIp).trim();
      } else if (j.targetIp || j.target_ip || j.targetIP) {
        // If only targetIp returned, treat it as the new actual IP after retarget
        this._actualLocalIp = String(j.targetIp || j.target_ip || j.targetIP).trim();
      } else if (newIp) {
        this._actualLocalIp = String(newIp).trim();
      }
      this._lastHealthTargetIp = String(newIp).trim();
      this.saveWifiDraft();
      this.updateWifiUI();
      this.setWifiStatus(`Re-target OK → ${String(newIp).trim()} (COM ${com}) — ${j.message || 'done'}`);
    } catch (e) {
      this.setWifiStatus(`Re-target gagal: ${e.message} — pastikan COM nyambung & BE lane ready`, true);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Re-target laptop IP'; }
      this.updateWifiRetargetState();
    }
  }

  updateWifiUI() {
    if (!this.wifiPanel) return;
    const ssidEl = this.wifiPanel.querySelector('#qs-wifi-ssid');
    const passEl = this.wifiPanel.querySelector('#qs-wifi-password');
    const chEl = this.wifiPanel.querySelector('#qs-wifi-channel');
    const hopEl = this.wifiPanel.querySelector('#qs-wifi-hop');
    const ipEl = this.wifiPanel.querySelector('#qs-wifi-target-ip');
    const comEl = this.wifiPanel.querySelector('#qs-wifi-com-port');
    if (ssidEl) ssidEl.value = this.wifiDraft.ssid || '';
    if (passEl) passEl.value = this.wifiDraft.password || '';
    let chVal = this.wifiDraft.channel || 'auto';
    if (this.wifiDraft.mode === 'channel' && chVal === 'auto') chVal = 'all';
    if (chEl) chEl.value = chVal;
    if (hopEl) hopEl.checked = !!this.wifiDraft.hop;
    if (ipEl) ipEl.value = this._lastHealthTargetIp || this.wifiDraft.targetIp || this._actualLocalIp || this.EXPECTED_TARGET_IP;
    if (comEl && this.wifiDraft.comPort) {
      const has = Array.from(comEl.options).some(o => o.value === this.wifiDraft.comPort);
      if (!has && this.wifiDraft.comPort) {
        const opt = document.createElement('option');
        opt.value = this.wifiDraft.comPort;
        opt.textContent = `${this.wifiDraft.comPort} (draft)`;
        comEl.appendChild(opt);
      }
      comEl.value = this.wifiDraft.comPort;
    }
    const mode = this.wifiDraft.mode || 'wifi';
    const wifiRadio = this.wifiPanel.querySelector('#qs-wifi-mode-wifi');
    const chanRadio = this.wifiPanel.querySelector('#qs-wifi-mode-channel');
    if (wifiRadio) wifiRadio.checked = mode === 'wifi';
    if (chanRadio) chanRadio.checked = mode === 'channel';
    const ssidRow = this.wifiPanel.querySelector('#qs-wifi-ssid-row');
    const passRow = this.wifiPanel.querySelector('#qs-wifi-password-row');
    const chRow = this.wifiPanel.querySelector('#qs-wifi-channel-row');
    const hopRow = this.wifiPanel.querySelector('#qs-wifi-hop-row');
    const ipRow = this.wifiPanel.querySelector('#qs-wifi-target-ip-row');
    if (ssidRow) ssidRow.style.display = mode === 'wifi' ? '' : 'none';
    if (passRow) passRow.style.display = mode === 'wifi' ? '' : 'none';
    if (chRow) chRow.style.display = mode === 'channel' ? '' : 'none';
    if (hopRow) hopRow.style.display = 'none';
    if (ipRow) ipRow.style.display = mode === 'wifi' ? '' : 'none';
    // Sensing Mode tier radios
    const tier = Number(this.wifiDraft.edgeTier ?? 1);
    const tierSafe = [0, 1, 2].includes(tier) ? tier : 1;
    for (const v of [0, 1, 2]) {
      const r = this.wifiPanel.querySelector(`#qs-wifi-tier-${v}`);
      if (r) r.checked = v === tierSafe;
    }
    this.updateWifiMismatchBadge();
    this.updateWifiRetargetState();
    this.updateWifiLiveBar();
    this.updateSsidGuard();
  }

  setupWifiHandlers() {
    const ssidEl = this.wifiPanel.querySelector('#qs-wifi-ssid');
    const passEl = this.wifiPanel.querySelector('#qs-wifi-password');
    const chEl = this.wifiPanel.querySelector('#qs-wifi-channel');
    const hopEl = this.wifiPanel.querySelector('#qs-wifi-hop');
    const comEl = this.wifiPanel.querySelector('#qs-wifi-com-port');
    const refreshBtn = this.wifiPanel.querySelector('#qs-wifi-refresh-ports');
    const testBtn = this.wifiPanel.querySelector('#qs-wifi-test');
    const applyBtn = this.wifiPanel.querySelector('#qs-wifi-apply');
    const retargetBtn = this.wifiPanel.querySelector('#qs-wifi-retarget');
    const modeWifiRadio = this.wifiPanel.querySelector('#qs-wifi-mode-wifi');
    const modeChannelRadio = this.wifiPanel.querySelector('#qs-wifi-mode-channel');
    ssidEl?.addEventListener('input', (e) => { this.updateWifiDraftField('ssid', e.target.value); this.updateSsidGuard(); });
    ssidEl?.addEventListener('change', (e) => { this.updateWifiDraftField('ssid', e.target.value); this.updateSsidGuard(); });
    passEl?.addEventListener('input', (e) => this.updateWifiDraftField('password', e.target.value));
    passEl?.addEventListener('change', (e) => this.updateWifiDraftField('password', e.target.value));
    chEl?.addEventListener('change', (e) => this.updateWifiDraftField('channel', e.target.value));
    hopEl?.addEventListener('change', (e) => this.updateWifiDraftField('hop', e.target.checked));
    comEl?.addEventListener('change', (e) => {
      this.updateWifiDraftField('comPort', e.target.value);
      this.updateWifiRetargetState();
    });
    modeWifiRadio?.addEventListener('change', () => {
      if (modeWifiRadio.checked) { this.updateWifiDraftField('mode', 'wifi'); this.updateWifiUI(); }
    });
    modeChannelRadio?.addEventListener('change', () => {
      if (modeChannelRadio.checked) { this.updateWifiDraftField('mode', 'channel'); this.updateWifiUI(); }
    });
    // Sensing Mode tier radios
    for (const v of [0, 1, 2]) {
      const tierRadio = this.wifiPanel.querySelector(`#qs-wifi-tier-${v}`);
      tierRadio?.addEventListener('change', () => {
        if (tierRadio.checked) this.updateWifiDraftField('edgeTier', v);
      });
    }
    refreshBtn?.addEventListener('click', () => this.fetchSerialPorts());
    testBtn?.addEventListener('click', () => this.handleWifiTestDryRun());
    applyBtn?.addEventListener('click', () => this.handleWifiApply());
    retargetBtn?.addEventListener('click', () => this.handleWifiReTarget());
  }

  createButton() {
    this.wifiButton = document.createElement('button');
    this.wifiButton.className = 'wifi-gear';
    this.wifiButton.setAttribute('aria-label', 'WiFi Settings');
    this.wifiButton.setAttribute('title', 'WiFi settings');
    this.wifiButton.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0 1 14 0"/><path d="M8.5 16.5a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1"/></svg>`;
    this.wifiButton.addEventListener('click', () => this.toggle());
    const headerInfo = document.querySelector('.header-info');
    if (headerInfo) headerInfo.appendChild(this.wifiButton);
  }

  createPanel() {
    this.wifiPanel = document.createElement('div');
    this.wifiPanel.className = 'wifi-settings-panel';
    this.wifiPanel.setAttribute('role', 'dialog');
    this.wifiPanel.setAttribute('aria-label', 'WiFi settings');

    const draft = this.wifiDraft;
    const ssidVal = (draft.ssid || '').replace(/"/g, '&quot;');
    const passVal = (draft.password || '').replace(/"/g, '&quot;');
    let ch = String(draft.channel || 'auto');
    if (draft.mode === 'channel' && ch === 'auto') ch = 'all';
    const hopChecked = draft.hop ? 'checked' : '';
    const targetIpVal = (draft.targetIp || this._actualLocalIp || this.EXPECTED_TARGET_IP).replace(/"/g, '&quot;');
    const mode = draft.mode || 'wifi';
    const tierSafe = [0, 1, 2].includes(Number(draft.edgeTier)) ? Number(draft.edgeTier) : 1;

    const dynamicIpForHint = this._actualLocalIp || this.EXPECTED_TARGET_IP;
    this.wifiPanel.innerHTML = `
      <div class="qs-header">
        <h3>WiFi Settings</h3>
        <button class="qs-close" aria-label="Close">&times;</button>
      </div>
      <div class="qs-body">
        <div class="qs-section" id="qs-wifi-section">
          <div class="qs-section-title">WiFi</div>
          <div class="qs-row" id="qs-wifi-mode-row" style="gap:16px;margin-bottom:10px;">
            <label style="display:flex;gap:6px;align-items:center;cursor:pointer;font-size:12px;"><input type="radio" name="qs-wifi-mode" value="wifi" id="qs-wifi-mode-wifi" ${mode === 'wifi' ? 'checked' : ''}> Connect WiFi</label>
            <label style="display:flex;gap:6px;align-items:center;cursor:pointer;font-size:12px;"><input type="radio" name="qs-wifi-mode" value="channel" id="qs-wifi-mode-channel" ${mode === 'channel' ? 'checked' : ''}> Sniff Channel</label>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:10px;">
            <div id="qs-wifi-step-1" class="wifi-step-1" style="font-size:11px;line-height:1.5;color:#c8d0dc;background:rgba(15,20,35,0.6);border:1px solid rgba(56,68,89,0.4);border-left:3px solid #667eea;border-radius:6px;padding:6px 8px;"><strong style="color:#667eea;">1. USB &amp; COM</strong> — Colok USB S3 → Device Manager → Ports (COM &amp; LPT) → catat COMx (USB JTAG) → pilih di dropdown COM Port → Refresh ↻ jika tidak muncul (auto-detect).</div>
            <div id="qs-wifi-step-2" class="wifi-step-2" style="font-size:11px;line-height:1.5;color:#c8d0dc;background:rgba(15,20,35,0.6);border:1px solid rgba(56,68,89,0.4);border-left:3px solid #22c55e;border-radius:6px;padding:6px 8px;"><strong style="color:#22c55e;">2. Target IP</strong> — Auto <code style="background:rgba(34,197,94,0.15);padding:1px 4px;border-radius:3px;">${dynamicIpForHint}:5005</code> bind <code style="background:rgba(34,197,94,0.15);padding:1px 4px;border-radius:3px;">0.0.0.0</code> → cek badge <span style="font-size:10px;font-weight:700;padding:1px 4px;border-radius:8px;background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.5);color:#4ade80;">✓ MATCH</span>/<span style="font-size:10px;font-weight:700;padding:1px 4px;border-radius:8px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.5);color:#f87171;">⚠ MISMATCH</span> → jika mismatch klik Re-target (butuh COM nyambung).</div>
            <div id="qs-wifi-step-3" class="wifi-step-3" style="font-size:11px;line-height:1.5;color:#c8d0dc;background:rgba(15,20,35,0.6);border:1px solid rgba(56,68,89,0.4);border-left:3px solid #f59e0b;border-radius:6px;padding:6px 8px;"><strong style="color:#f59e0b;">3. Test &amp; Apply</strong> — Klik Test (dry-run 8s) polling <code style="background:rgba(245,158,11,0.15);padding:1px 4px;border-radius:3px;">GET /health/health</code> cek pps&gt;0 &amp; Connected ESP 192.168.1.92 → jika PASS baru klik Apply (provision real).</div>
          </div>
          <div class="qs-row" id="qs-wifi-ssid-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-ssid" style="font-size:12px;opacity:0.9;">SSID</label>
            <input type="text" id="qs-wifi-ssid" class="qs-text-input" placeholder="Ketik SSID WiFi..." value="${ssidVal}" style="width:100%;box-sizing:border-box;">
            <span id="qs-wifi-ssid-warn" style="display:none;font-size:11px;color:#f59e0b;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.4);border-radius:4px;padding:4px 6px;">⚠ ESP32-S3 hanya 2.4GHz — ganti ke FLAMBOYAN'S_EXT</span>
          </div>
          <div class="qs-row" id="qs-wifi-password-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-password" style="font-size:12px;opacity:0.9;">Password</label>
            <input type="password" id="qs-wifi-password" class="qs-text-input" placeholder="••••••••" value="${passVal}" style="width:100%;box-sizing:border-box;">
          </div>
          <div class="qs-row" id="qs-wifi-channel-row">
            <label for="qs-wifi-channel" style="font-size:12px;opacity:0.9;">Channel</label>
            <select id="qs-wifi-channel" class="qs-text-input" style="flex:0 0 100px;">
              <option value="1" ${ch === '1' ? 'selected' : ''}>1</option>
              <option value="6" ${ch === '6' ? 'selected' : ''}>6</option>
              <option value="11" ${ch === '11' ? 'selected' : ''}>11</option>
              <option value="all" ${ch === 'all' ? 'selected' : ''}>Semua (hop)</option>
            </select>
          </div>
          <label class="qs-toggle" id="qs-wifi-hop-row">
            <span>Hop</span>
            <input type="checkbox" id="qs-wifi-hop" ${hopChecked}>
            <span class="qs-switch"></span>
          </label>
          <div class="qs-row" id="qs-wifi-target-ip-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-target-ip" style="font-size:12px;opacity:0.9;">Target IP</label>
            <div style="display:flex;gap:8px;align-items:center;">
              <input type="text" id="qs-wifi-target-ip" class="qs-text-input" readonly value="${targetIpVal}" title="Auto laptop IP" style="flex:1;">
              <span id="qs-wifi-match-badge" style="display:none;font-size:10px;font-weight:700;padding:2px 6px;border-radius:10px;background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.5);color:#4ade80;">✓ MATCH</span>
              <span id="qs-wifi-mismatch-badge" style="display:none;font-size:10px;font-weight:700;padding:2px 6px;border-radius:10px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.5);color:#f87171;">⚠ MISMATCH</span>
            </div>
          </div>
          <div id="qs-wifi-live-bar" style="font-size:11px;font-family:monospace;padding:4px 8px;border-radius:6px;border:1px solid rgba(56,68,89,0.3);background:rgba(15,20,35,0.4);color:#6b7a8d;margin-bottom:8px;min-height:18px;">pps -- | var -- | presence --</div>
          <div class="qs-row" id="qs-wifi-com-port-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-com-port" style="font-size:12px;opacity:0.9;">COM Port</label>
            <div style="display:flex;gap:8px;">
              <select id="qs-wifi-com-port" class="qs-text-input" style="flex:1;"><option value="">-- pilih COM --</option></select>
              <button class="qs-btn" id="qs-wifi-refresh-ports" title="Refresh COM list">↻</button>
            </div>
          </div>
          <div class="qs-row" id="qs-wifi-sensing-mode-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label style="font-size:12px;opacity:0.9;" title="Hemat=hemat WiFi, Responsif=beban WiFi naik">Sensing Mode</label>
            <div style="display:flex;gap:10px;flex-wrap:wrap;" title="Hemat=hemat WiFi, Responsif=beban WiFi naik">
              <label style="display:flex;gap:4px;align-items:center;cursor:pointer;font-size:12px;" title="Hemat=hemat WiFi, Responsif=beban WiFi naik"><input type="radio" name="qs-wifi-edge-tier" value="0" id="qs-wifi-tier-0" ${tierSafe === 0 ? 'checked' : ''}> Hemat <span style="opacity:0.6;font-size:11px;">pps ~1</span></label>
              <label style="display:flex;gap:4px;align-items:center;cursor:pointer;font-size:12px;" title="Hemat=hemat WiFi, Responsif=beban WiFi naik"><input type="radio" name="qs-wifi-edge-tier" value="1" id="qs-wifi-tier-1" ${tierSafe === 1 ? 'checked' : ''}> Seimbang* <span style="opacity:0.6;font-size:11px;">pps ~5</span></label>
              <label style="display:flex;gap:4px;align-items:center;cursor:pointer;font-size:12px;" title="Hemat=hemat WiFi, Responsif=beban WiFi naik"><input type="radio" name="qs-wifi-edge-tier" value="2" id="qs-wifi-tier-2" ${tierSafe === 2 ? 'checked' : ''}> Responsif <span style="opacity:0.6;font-size:11px;">pps ~15</span></label>
            </div>
          </div>
          <div class="qs-row" style="gap:8px;flex-wrap:wrap;">
            <button class="qs-btn" id="qs-wifi-test">Test (dry-run)</button>
            <button class="qs-btn" id="qs-wifi-apply" style="background:rgba(102,126,234,0.9);color:#fff;border-color:rgba(102,126,234,1);">Apply</button>
            <button class="qs-btn" id="qs-wifi-retarget">Re-target laptop IP</button>
          </div>
          <div id="qs-wifi-status" style="min-height:18px;font-size:12px;color:#6b7a8d;margin-top:6px;word-break:break-word;"></div>
          <div style="margin-top:6px;"><span id="qs-wifi-test-badge" style="display:none;font-size:11px;font-weight:700;padding:4px 10px;border-radius:12px;border:1px solid;">--</span></div>
        </div>
      </div>
    `;

    this.wifiPanel.querySelector('.qs-close').addEventListener('click', () => this.close());
    this.setupWifiHandlers();
    this.updateWifiUI();
    document.body.appendChild(this.wifiPanel);

    this._outsideHandler = (e) => {
      if (this.isWifiOpen && !this.wifiPanel.contains(e.target) && !this.wifiButton.contains(e.target)) {
        const qsPanel = document.querySelector('.quick-settings-panel');
        const qsGear = document.querySelector('.settings-gear');
        if (qsPanel && qsPanel.contains(e.target)) return;
        if (qsGear && qsGear.contains(e.target)) return;
        this.close();
      }
    };
    document.addEventListener('click', this._outsideHandler);

    // Non-blocking WiFi fetches (BE may be down)
    this.fetchSerialPorts().catch(() => {});
    this.refreshWifiHealth().catch(() => {});
    // Live mini-bar polling every 1s (reuse fetchNetworkIp/refreshWifiHealth)
    if (this._livePollTimer) clearInterval(this._livePollTimer);
    this._livePollTimer = setInterval(() => { this.refreshWifiHealth().catch(() => {}); }, 1000);
  }

  toggle() {
    this.isWifiOpen ? this.close() : this.open();
  }

  open() {
    this.isWifiOpen = true;
    this.wifiPanel.classList.add('open');
    void this.refreshWifiHealth();
  }

  close() {
    this.isWifiOpen = false;
    this.wifiPanel.classList.remove('open');
  }

  dispose() {
    if (this._livePollTimer) { clearInterval(this._livePollTimer); this._livePollTimer = null; }
    if (this._outsideHandler) document.removeEventListener('click', this._outsideHandler);
    this.wifiButton?.remove();
    this.wifiPanel?.remove();
  }
}

// ── QuickSettings — 5 sections asli tanpa WiFi, plus companion WifiSettings ──
export class QuickSettings {
  constructor(app) {
    this.app = app;
    this.button = null;
    this.panel = null;
    this.isOpen = false;
    this._outsideHandler = null;
    this.wifiSettings = null;
  }

  init() {
    this.createButton();
    this.createPanel();
    // Companion WiFi gear/panel sebelah settings-gear in .header-info
    this.wifiSettings = new WifiSettings(this.app);
    this.wifiSettings.init();
  }

  createButton() {
    this.button = document.createElement('button');
    this.button.className = 'settings-gear';
    this.button.setAttribute('aria-label', 'Settings');
    this.button.setAttribute('title', 'Quick settings');
    this.button.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
    this.button.addEventListener('click', () => this.toggle());
    const headerInfo = document.querySelector('.header-info');
    if (headerInfo) headerInfo.appendChild(this.button);
  }

  createPanel() {
    this.panel = document.createElement('div');
    this.panel.className = 'quick-settings-panel';
    this.panel.setAttribute('role', 'dialog');
    this.panel.setAttribute('aria-label', 'Quick settings');

    this.panel.innerHTML = `
      <div class="qs-header">
        <h3>Settings</h3>
        <button class="qs-close" aria-label="Close">&times;</button>
      </div>
      <div class="qs-body">
        <div class="qs-section">
          <div class="qs-section-title">Display</div>
          <label class="qs-toggle">
            <span>Reduced motion</span>
            <input type="checkbox" id="qs-reduced-motion" ${this.prefersReducedMotion() ? 'checked' : ''}>
            <span class="qs-switch"></span>
          </label>
          <label class="qs-toggle">
            <span>High contrast</span>
            <input type="checkbox" id="qs-high-contrast">
            <span class="qs-switch"></span>
          </label>
          <label class="qs-toggle">
            <span>Compact mode</span>
            <input type="checkbox" id="qs-compact" ${this.getSetting('compact') ? 'checked' : ''}>
            <span class="qs-switch"></span>
          </label>
        </div>
        <div class="qs-section">
          <div class="qs-section-title">Monitoring</div>
          <label class="qs-toggle">
            <span>Health polling</span>
            <input type="checkbox" id="qs-health-polling" checked>
            <span class="qs-switch"></span>
          </label>
          <label class="qs-toggle">
            <span>Auto-reconnect</span>
            <input type="checkbox" id="qs-auto-reconnect" checked>
            <span class="qs-switch"></span>
          </label>
        </div>
        <div class="qs-section">
          <div class="qs-section-title">Cognitum Account</div>
          <div class="qs-row" style="flex-direction: column; align-items: stretch; gap: 6px;">
            <span id="qs-signin-status" style="font-size: 0.9em; opacity: 0.85;">Checking...</span>
            <div style="display: flex; gap: 8px;">
              <button class="qs-btn" id="qs-signin" hidden>Sign in with Cognitum</button>
              <button class="qs-btn-danger" id="qs-signout" hidden>Sign out</button>
            </div>
          </div>
        </div>
        <div class="qs-section">
          <div class="qs-section-title">API Access</div>
          <div class="qs-row" style="flex-direction: column; align-items: stretch; gap: 6px;">
            <span>Bearer token (set only if the server enforces RUVIEW_API_TOKEN)</span>
            <input type="password" id="qs-api-token" class="qs-text-input" placeholder="Paste token..." autocomplete="off" style="width: 100%; box-sizing: border-box;">
            <div style="display: flex; gap: 8px;">
              <button class="qs-btn" id="qs-api-token-save">Save & Apply</button>
              <button class="qs-btn-danger" id="qs-api-token-clear">Clear</button>
            </div>
            <span id="qs-api-token-status" style="font-size: 0.85em; opacity: 0.75;"></span>
          </div>
        </div>
        <div class="qs-section">
          <div class="qs-section-title">Data</div>
          <div class="qs-row">
            <span>Clear local data</span>
            <button class="qs-btn-danger" id="qs-clear-data">Clear</button>
          </div>
          <div class="qs-row">
            <span>Reset onboarding</span>
            <button class="qs-btn" id="qs-reset-tour">Reset</button>
          </div>
        </div>
      </div>
    `;

    this.panel.querySelector('.qs-close').addEventListener('click', () => this.close());

    window.addEventListener('pageshow', () => { void refreshSignInPanel(this.panel); });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) void refreshSignInPanel(this.panel);
    });

    this.panel.querySelector('#qs-signin')
      .addEventListener('click', () => { window.location.href = '/oauth/start'; });
    this.panel.querySelector('#qs-signout')
      .addEventListener('click', () => { window.location.href = '/oauth/logout'; });

    this.panel.querySelector('#qs-reduced-motion').addEventListener('change', (e) => {
      document.body.classList.toggle('reduced-motion', e.target.checked);
      this.saveSetting('reduced-motion', e.target.checked);
    });

    this.panel.querySelector('#qs-high-contrast').addEventListener('change', (e) => {
      document.body.classList.toggle('high-contrast', e.target.checked);
      this.saveSetting('high-contrast', e.target.checked);
    });

    this.panel.querySelector('#qs-compact').addEventListener('change', (e) => {
      document.body.classList.toggle('compact-mode', e.target.checked);
      this.saveSetting('compact', e.target.checked);
    });

    this.panel.querySelector('#qs-health-polling').addEventListener('change', (e) => {
      if (e.target.checked) {
        document.dispatchEvent(new CustomEvent('health-polling-toggle', { detail: true }));
      } else {
        document.dispatchEvent(new CustomEvent('health-polling-toggle', { detail: false }));
      }
    });

    this.panel.querySelector('#qs-api-token-save').addEventListener('click', () => {
      const input = this.panel.querySelector('#qs-api-token');
      const status = this.panel.querySelector('#qs-api-token-status');
      const token = input.value.trim();
      if (!token) {
        status.textContent = 'Enter a token first, or use Clear to remove one.';
        return;
      }
      try { localStorage.setItem(API_TOKEN_STORAGE_KEY, token); } catch { /* noop */ }
      apiService.setAuthToken(token);
      status.textContent = 'Token saved and applied. Reloading...';
      setTimeout(() => window.location.reload(), 600);
    });

    this.panel.querySelector('#qs-api-token-clear').addEventListener('click', () => {
      const input = this.panel.querySelector('#qs-api-token');
      const status = this.panel.querySelector('#qs-api-token-status');
      try { localStorage.removeItem(API_TOKEN_STORAGE_KEY); } catch { /* noop */ }
      apiService.setAuthToken(null);
      input.value = '';
      status.textContent = 'Token cleared. Reloading...';
      setTimeout(() => window.location.reload(), 600);
    });

    this.panel.querySelector('#qs-clear-data').addEventListener('click', () => {
      try {
        localStorage.clear();
        sessionStorage.clear();
      } catch { /* noop */ }
      this.close();
      window.location.reload();
    });

    this.panel.querySelector('#qs-reset-tour').addEventListener('click', () => {
      try { localStorage.removeItem('ruview-onboarding-done'); } catch { /* noop */ }
      this.close();
      document.dispatchEvent(new CustomEvent('start-onboarding'));
    });

    document.body.appendChild(this.panel);

    this._outsideHandler = (e) => {
      if (this.isOpen && !this.panel.contains(e.target) && !this.button.contains(e.target)) {
        const wifiPanel = document.querySelector('.wifi-settings-panel');
        const wifiGear = document.querySelector('.wifi-gear');
        if (wifiPanel && wifiPanel.contains(e.target)) return;
        if (wifiGear && wifiGear.contains(e.target)) return;
        this.close();
      }
    };
    document.addEventListener('click', this._outsideHandler);

    this.applySavedSettings();
  }

  applySavedSettings() {
    if (this.getSetting('reduced-motion') || this.prefersReducedMotion()) {
      document.body.classList.add('reduced-motion');
      const cb = this.panel.querySelector('#qs-reduced-motion');
      if (cb) cb.checked = true;
    }
    if (this.getSetting('high-contrast')) {
      document.body.classList.add('high-contrast');
      const cb = this.panel.querySelector('#qs-high-contrast');
      if (cb) cb.checked = true;
    }
    if (this.getSetting('compact')) {
      document.body.classList.add('compact-mode');
    }
    const status = this.panel.querySelector('#qs-api-token-status');
    let hasToken = false;
    try { hasToken = !!localStorage.getItem(API_TOKEN_STORAGE_KEY); } catch { /* noop */ }
    if (status) status.textContent = hasToken ? 'A token is currently set.' : 'No token set (auth is off or unnecessary).';
  }

  prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  toggle() {
    this.isOpen ? this.close() : this.open();
  }

  open() {
    this.isOpen = true;
    this.panel.classList.add('open');
    void refreshSignInPanel(this.panel);
  }

  close() {
    this.isOpen = false;
    this.panel.classList.remove('open');
  }

  getSetting(key) {
    try { return JSON.parse(localStorage.getItem(`ruview-setting-${key}`)); }
    catch { return null; }
  }

  saveSetting(key, value) {
    try { localStorage.setItem(`ruview-setting-${key}`, JSON.stringify(value)); }
    catch { /* noop */ }
  }

  dispose() {
    if (this._outsideHandler) document.removeEventListener('click', this._outsideHandler);
    this.button?.remove();
    this.panel?.remove();
    this.wifiSettings?.dispose();
  }
}

// ---- Cognitum browser sign-in (ADR-271) -------------------------------------
export async function refreshSignInPanel(root = document) {
  const status = root.querySelector('#qs-signin-status');
  const signIn = root.querySelector('#qs-signin');
  const signOut = root.querySelector('#qs-signout');
  if (!status || !signIn || !signOut) return null;

  let info;
  try {
    const resp = await fetch('/oauth/status', { credentials: 'same-origin' });
    if (resp.status === 404) {
      status.textContent = 'This server does not support Cognitum sign-in.';
      signIn.hidden = true;
      signOut.hidden = true;
      return null;
    }
    if (!resp.ok) throw new Error(`status ${resp.status}`);
    info = await resp.json();
  } catch (err) {
    status.textContent = `Could not reach the server (${err.message}).`;
    signIn.hidden = true;
    signOut.hidden = true;
    return null;
  }

  if (info.signed_in) {
    status.textContent = `Signed in${info.account ? ` as ${info.account}` : ''}${
      info.scope ? ` - ${info.scope}` : ''
    }`;
    signIn.hidden = true;
    signOut.hidden = false;
  } else if (info.browser_signin) {
    status.textContent = info.auth_required
      ? 'This server requires sign-in.'
      : 'Optional: sign in to use your Cognitum account.';
    signIn.hidden = false;
    signOut.hidden = true;
  } else if (info.auth_required) {
    status.textContent = 'This server uses a shared API token (see API Access below).';
    signIn.hidden = true;
    signOut.hidden = true;
  } else {
    status.textContent = 'This server does not require sign-in.';
    signIn.hidden = true;
    signOut.hidden = true;
  }

  signIn.onclick = () => { window.location.href = '/oauth/start'; };
  signOut.onclick = () => { window.location.href = '/oauth/logout'; };
  return info;
}
