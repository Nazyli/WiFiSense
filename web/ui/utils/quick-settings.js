// Quick Settings Panel - Centralized configuration for all UI features
// Accessible via gear icon in header

import { apiService, API_TOKEN_STORAGE_KEY } from '../services/api.service.js';
import { API_CONFIG } from '../config/api.config.js';

export class QuickSettings {
  constructor(app) {
    this.app = app;
    this.button = null;
    this.panel = null;
    this.isOpen = false;
    // WiFi provision state — duplicated from SettingsPanel.js for 1-click gear access
    this.EXPECTED_TARGET_IP = '192.168.1.75';
    this.WIFI_DRAFT_KEY = 'wifisense-wifi-draft';
    this._lastHealthTargetIp = null;
    this.wifiDraft = this.getDefaultWifiDraft();
    this.wifiTest = { running: false, lastPps: 0, lastFrom: null, pass: null };
    this.loadWifiDraft();
  }

  // A stored token is applied at api.service.js module load (before any
  // request fires) — this panel only saves/clears it.
  init() {
    this.createButton();
    this.createPanel();
  }

  // ── WiFi helpers (ported from SettingsPanel.js) ────────────────────────
  getDefaultWifiDraft() {
    return {
      ssid: 'WIFI_RUMAH',
      password: '<YOUR_WIFI_PASSWORD>',
      channel: 'auto',
      hop: false,
      targetIp: this.EXPECTED_TARGET_IP || '192.168.1.75',
      comPort: ''
    };
  }

  loadWifiDraft() {
    try {
      // Share draft with SettingsPanel: primary key 'wifisense-wifi-draft'
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
      // also try the SettingPanel container-specific keys if present
      if (!raw) {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.startsWith('wifisense-wifi-draft-')) { raw = localStorage.getItem(k); break; }
        }
      }
      if (raw) {
        const parsed = JSON.parse(raw);
        this.wifiDraft = { ...this.getDefaultWifiDraft(), ...parsed };
        if (this.wifiDraft.channel !== 'auto') {
          const c = String(this.wifiDraft.channel);
          this.wifiDraft.channel = ['1', '6', '11', 'auto'].includes(c) ? c : 'auto';
        }
      }
    } catch { /* noop */ }
  }

  saveWifiDraft() {
    try {
      const s = JSON.stringify(this.wifiDraft);
      localStorage.setItem(this.WIFI_DRAFT_KEY, s);
      try { localStorage.setItem('wifisense-wifi-draft-quick-settings', s); } catch {}
      try { localStorage.setItem('wifiDraft', s); } catch {}
      // also mirror to generic legacy key so SettingsPanel sees it
      try { localStorage.setItem('wifisense-wifi-draft-settings-panel', s); } catch {}
    } catch { /* noop */ }
  }

  updateWifiDraftField(key, value) {
    this.wifiDraft[key] = value;
    this.saveWifiDraft();
    this.updateWifiMismatchBadge();
  }

  updateWifiMismatchBadge() {
    const mismatchBadge = this.panel?.querySelector('#qs-wifi-mismatch-badge');
    const matchBadge = this.panel?.querySelector('#qs-wifi-match-badge');
    if (!mismatchBadge || !matchBadge) return;
    const targetIp = (this.wifiDraft.targetIp || this.EXPECTED_TARGET_IP).trim();
    const liveTarget = this._lastHealthTargetIp;
    const compareIp = liveTarget || targetIp;
    const isMismatch = compareIp !== this.EXPECTED_TARGET_IP;
    const draftMismatch = targetIp !== this.EXPECTED_TARGET_IP;
    const showMismatch = isMismatch || draftMismatch;
    mismatchBadge.style.display = showMismatch ? 'inline-flex' : 'none';
    matchBadge.style.display = showMismatch ? 'none' : 'inline-flex';
    const ipInput = this.panel.querySelector('#qs-wifi-target-ip');
    if (ipInput) {
      ipInput.value = targetIp;
      ipInput.title = showMismatch ? `Mismatch: expected ${this.EXPECTED_TARGET_IP}` : 'MATCH';
      ipInput.style.borderColor = showMismatch ? 'rgba(239,68,68,0.8)' : '';
    }
  }

  async fetchSerialPorts() {
    const sel = this.panel?.querySelector('#qs-wifi-com-port');
    const status = this.panel?.querySelector('#qs-wifi-status');
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
      const statusEl = this.panel?.querySelector('#qs-wifi-status');
      if (statusEl) statusEl.textContent = `Gagal muat COM: ${e.message}`;
    }
  }

  async refreshWifiHealth() {
    try {
      const url = `${API_CONFIG.BASE_URL}/health/health`;
      const resp = await fetch(url, { headers: { Accept: 'application/json' } });
      if (!resp.ok) return;
      const data = await resp.json().catch(() => null);
      if (!data) return;
      if (data.targetIp) this._lastHealthTargetIp = String(data.targetIp).trim();
      else if (data.target_ip) this._lastHealthTargetIp = String(data.target_ip).trim();
      this.updateWifiMismatchBadge();
    } catch { /* noop */ }
  }

  updateWifiRetargetState() {
    const btn = this.panel?.querySelector('#qs-wifi-retarget');
    if (!btn) return;
    const hasCom = !!(this.wifiDraft.comPort && String(this.wifiDraft.comPort).trim());
    btn.disabled = !hasCom;
    btn.title = hasCom ? '1-klik Re-target laptop IP (butuh COM nyambung)' : 'Pilih COM port dahulu (butuh COM nyambung)';
    btn.style.opacity = hasCom ? '1' : '0.5';
    btn.style.cursor = hasCom ? 'pointer' : 'not-allowed';
  }

  setWifiStatus(msg, isError = false) {
    const el = this.panel?.querySelector('#qs-wifi-status');
    if (!el) return;
    el.textContent = msg || '';
    el.style.color = isError ? '#ef4444' : '#6b7a8d';
    if (msg) el.style.display = 'block';
  }

  renderWifiTestBadge({ pass, pps, from, source }) {
    const badge = this.panel?.querySelector('#qs-wifi-test-badge');
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
    const btn = this.panel?.querySelector('#qs-wifi-test');
    const badge = this.panel?.querySelector('#qs-wifi-test-badge');
    if (this.wifiTest.running) return;
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
        if (btn) {
          const remain = Math.max(0, Math.ceil((durationMs - (Date.now() - start)) / 1000));
          btn.textContent = `Testing… ${remain}s`;
        }
        await new Promise(res => setTimeout(res, intervalMs));
      }
      const pass = best.pass && best.pps > 0;
      const finalPps = best.pps || (lastHealth ? Number(lastHealth.pps || 0) : 0);
      const finalFrom = best.from || (lastHealth ? (lastHealth.lastFrom || lastHealth.last_from || '192.168.1.92') : '192.168.1.92');
      const finalSource = best.source || (lastHealth ? lastHealth.source : null);
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
    } finally {
      this.wifiTest.running = false;
      if (btn) { btn.disabled = false; btn.textContent = 'Test (dry-run)'; }
    }
  }

  async handleWifiApply() {
    const btn = this.panel?.querySelector('#qs-wifi-apply');
    if (btn) { btn.disabled = true; btn.textContent = 'Applying…'; }
    this.setWifiStatus('Apply (provision real) → POST ...');
    this.saveWifiDraft();
    const payload = {
      ssid: this.wifiDraft.ssid,
      password: this.wifiDraft.password,
      channel: this.wifiDraft.channel === 'auto' ? null : Number(this.wifiDraft.channel),
      hop: !!this.wifiDraft.hop,
      hop_channels: this.wifiDraft.hop ? (this.wifiDraft.channel === 'auto' ? '1,6,11' : String(this.wifiDraft.channel)) : null,
      target_ip: this.wifiDraft.targetIp || this.EXPECTED_TARGET_IP,
      targetIp: this.wifiDraft.targetIp || this.EXPECTED_TARGET_IP,
      comPort: this.wifiDraft.comPort,
      port: this.wifiDraft.comPort,
      dryRun: false
    };
    const endpoints = [
      '/api/v1/config/provision',
      '/api/v1/config/wifi',
      '/api/v1/serial/provision',
      '/api/v1/config/apply'
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
        if (r.status === 404) continue;
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
    const btn = this.panel?.querySelector('#qs-wifi-retarget');
    const com = (this.wifiDraft.comPort || '').trim();
    if (!com) {
      this.setWifiStatus('Re-target butuh COM nyambung — pilih COMx dahulu', true);
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = 'Re-targeting…'; }
    this.setWifiStatus('1-klik Re-target laptop IP → POST /api/v1/config/re-target ...');
    const payload = {
      port: com,
      comPort: com,
      targetIp: this.EXPECTED_TARGET_IP,
      target_ip: this.EXPECTED_TARGET_IP
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
      this.wifiDraft.targetIp = this.EXPECTED_TARGET_IP;
      this.saveWifiDraft();
      this.updateWifiUI();
      this.setWifiStatus(`Re-target OK → ${this.EXPECTED_TARGET_IP} (COM ${com}) — ${j.message || 'done'}`);
    } catch (e) {
      this.setWifiStatus(`Re-target gagal: ${e.message} — pastikan COM nyambung & BE lane ready`, true);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Re-target laptop IP'; }
      this.updateWifiRetargetState();
    }
  }

  updateWifiUI() {
    if (!this.panel) return;
    const ssidEl = this.panel.querySelector('#qs-wifi-ssid');
    const passEl = this.panel.querySelector('#qs-wifi-password');
    const chEl = this.panel.querySelector('#qs-wifi-channel');
    const hopEl = this.panel.querySelector('#qs-wifi-hop');
    const ipEl = this.panel.querySelector('#qs-wifi-target-ip');
    const comEl = this.panel.querySelector('#qs-wifi-com-port');
    if (ssidEl) ssidEl.value = this.wifiDraft.ssid || '';
    if (passEl) passEl.value = this.wifiDraft.password || '';
    if (chEl) chEl.value = this.wifiDraft.channel || 'auto';
    if (hopEl) hopEl.checked = !!this.wifiDraft.hop;
    if (ipEl) ipEl.value = this.wifiDraft.targetIp || this.EXPECTED_TARGET_IP;
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
    this.updateWifiMismatchBadge();
    this.updateWifiRetargetState();
  }

  setupWifiHandlers() {
    const ssidEl = this.panel.querySelector('#qs-wifi-ssid');
    const passEl = this.panel.querySelector('#qs-wifi-password');
    const chEl = this.panel.querySelector('#qs-wifi-channel');
    const hopEl = this.panel.querySelector('#qs-wifi-hop');
    const comEl = this.panel.querySelector('#qs-wifi-com-port');
    const refreshBtn = this.panel.querySelector('#qs-wifi-refresh-ports');
    const testBtn = this.panel.querySelector('#qs-wifi-test');
    const applyBtn = this.panel.querySelector('#qs-wifi-apply');
    const retargetBtn = this.panel.querySelector('#qs-wifi-retarget');
    ssidEl?.addEventListener('input', (e) => this.updateWifiDraftField('ssid', e.target.value));
    ssidEl?.addEventListener('change', (e) => this.updateWifiDraftField('ssid', e.target.value));
    passEl?.addEventListener('input', (e) => this.updateWifiDraftField('password', e.target.value));
    passEl?.addEventListener('change', (e) => this.updateWifiDraftField('password', e.target.value));
    chEl?.addEventListener('change', (e) => this.updateWifiDraftField('channel', e.target.value));
    hopEl?.addEventListener('change', (e) => this.updateWifiDraftField('hop', e.target.checked));
    comEl?.addEventListener('change', (e) => {
      this.updateWifiDraftField('comPort', e.target.value);
      this.updateWifiRetargetState();
    });
    refreshBtn?.addEventListener('click', () => this.fetchSerialPorts());
    testBtn?.addEventListener('click', () => this.handleWifiTestDryRun());
    applyBtn?.addEventListener('click', () => this.handleWifiApply());
    retargetBtn?.addEventListener('click', () => this.handleWifiReTarget());
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

    const draft = this.wifiDraft;
    const ssidVal = (draft.ssid || '').replace(/"/g, '&quot;');
    const passVal = (draft.password || '').replace(/"/g, '&quot;');
    const ch = String(draft.channel || 'auto');
    const hopChecked = draft.hop ? 'checked' : '';
    const targetIpVal = (draft.targetIp || this.EXPECTED_TARGET_IP).replace(/"/g, '&quot;');

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
        <div class="qs-section" id="qs-wifi-section">
          <div class="qs-section-title">WiFi</div>
          <div style="font-size:11px;color:#9aa8c0;background:rgba(15,20,35,0.6);border:1px dashed rgba(56,68,89,0.5);border-radius:6px;padding:6px 8px;margin-bottom:10px;line-height:1.5;">1. Colok USB S3 → Device Manager → Ports COMx → pilih COMx → 2. Target IP auto 192.168.1.75 → 3. Test dry-run pps&gt;0 → Apply</div>
          <div class="qs-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-ssid" style="font-size:12px;opacity:0.9;">SSID</label>
            <input type="text" id="qs-wifi-ssid" class="qs-text-input" placeholder="WIFI_RUMAH" value="${ssidVal}" style="width:100%;box-sizing:border-box;">
          </div>
          <div class="qs-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-password" style="font-size:12px;opacity:0.9;">Password</label>
            <input type="password" id="qs-wifi-password" class="qs-text-input" placeholder="••••••••" value="${passVal}" style="width:100%;box-sizing:border-box;">
          </div>
          <div class="qs-row">
            <label for="qs-wifi-channel" style="font-size:12px;opacity:0.9;">Channel</label>
            <select id="qs-wifi-channel" class="qs-text-input" style="flex:0 0 100px;">
              <option value="auto" ${ch === 'auto' ? 'selected' : ''}>auto</option>
              <option value="1" ${ch === '1' ? 'selected' : ''}>1</option>
              <option value="6" ${ch === '6' ? 'selected' : ''}>6</option>
              <option value="11" ${ch === '11' ? 'selected' : ''}>11</option>
            </select>
          </div>
          <label class="qs-toggle">
            <span>Hop</span>
            <input type="checkbox" id="qs-wifi-hop" ${hopChecked}>
            <span class="qs-switch"></span>
          </label>
          <div class="qs-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-target-ip" style="font-size:12px;opacity:0.9;">Target IP</label>
            <div style="display:flex;gap:8px;align-items:center;">
              <input type="text" id="qs-wifi-target-ip" class="qs-text-input" readonly value="${targetIpVal}" title="Auto laptop IP" style="flex:1;">
              <span id="qs-wifi-match-badge" style="display:none;font-size:10px;font-weight:700;padding:2px 6px;border-radius:10px;background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.5);color:#4ade80;">✓ MATCH</span>
              <span id="qs-wifi-mismatch-badge" style="display:none;font-size:10px;font-weight:700;padding:2px 6px;border-radius:10px;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.5);color:#f87171;">⚠ MISMATCH</span>
            </div>
          </div>
          <div class="qs-row" style="flex-direction:column;align-items:stretch;gap:4px;margin-bottom:8px;">
            <label for="qs-wifi-com-port" style="font-size:12px;opacity:0.9;">COM Port</label>
            <div style="display:flex;gap:8px;">
              <select id="qs-wifi-com-port" class="qs-text-input" style="flex:1;"><option value="">-- pilih COM --</option></select>
              <button class="qs-btn" id="qs-wifi-refresh-ports" title="Refresh COM list">↻</button>
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

    // Bind events
    this.panel.querySelector('.qs-close').addEventListener('click', () => this.close());

    // Re-check sign-in state whenever the page could be showing a stale view:
    // `pageshow` fires on a back/forward-cache restore (where no script re-runs
    // and no fetch would otherwise happen), and `visibilitychange` covers
    // signing in or out in another tab. Opening the panel alone is not enough —
    // the panel may already be open, or the page may be restored wholesale.
    window.addEventListener('pageshow', () => { void refreshSignInPanel(this.panel); });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) void refreshSignInPanel(this.panel);
    });

    // ADR-271 sign-in. Bound here as well as in refreshSignInPanel so a click
    // works even if the status fetch has not resolved yet.
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
      const healthService = this.app?.components?.dashboard?.healthSubscription;
      if (e.target.checked) {
        // Resume would need import - just dispatch event
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

    // WiFi wiring — duplicated from SettingsPanel for 1-click gear access
    this.setupWifiHandlers();
    this.updateWifiUI();

    document.body.appendChild(this.panel);

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (this.isOpen && !this.panel.contains(e.target) && !this.button.contains(e.target)) {
        this.close();
      }
    });

    // Apply saved settings on init
    this.applySavedSettings();
    // Non-blocking WiFi fetches (BE may be down)
    this.fetchSerialPorts().catch(() => {});
    this.refreshWifiHealth().catch(() => {});
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
    // Refresh on every open, not once at construction: the session may have
    // been established in another tab, or expired since the page loaded.
    // Fire-and-forget — a failure renders as a message in the panel, and must
    // not stop the panel opening.
    void refreshSignInPanel(this.panel);
    // Refresh WiFi health/badge on open as well
    void this.refreshWifiHealth();
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
    this.button?.remove();
    this.panel?.remove();
  }
}

// ---- Cognitum browser sign-in (ADR-271) -------------------------------------
//
// `/oauth/status` is intentionally UNGATED: a signed-out browser cannot ask a
// gated endpoint whether sign-in is available. It returns capability flags and,
// when a session exists, who it belongs to — never a credential.
//
// Sign-in is a full-page navigation, not fetch(): the server replies 302 to
// auth.cognitum.one, and the browser must follow it and carry the transaction
// cookie. An XHR would follow the redirect invisibly and land nowhere useful.
export async function refreshSignInPanel(root = document) {
  const status = root.querySelector('#qs-signin-status');
  const signIn = root.querySelector('#qs-signin');
  const signOut = root.querySelector('#qs-signout');
  if (!status || !signIn || !signOut) return null;

  let info;
  try {
    const resp = await fetch('/oauth/status', { credentials: 'same-origin' });
    // 404 = a server predating ADR-271. Say so plainly rather than offering a
    // button that will 404.
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
    // Auth is on but OAuth is not — the static-token panel below is the path.
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
