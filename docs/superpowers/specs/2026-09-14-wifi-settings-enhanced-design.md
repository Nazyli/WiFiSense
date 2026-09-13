# WiFi Settings Enhanced — Design Spec

**Date:** 2026-09-14
**Scope:** Enhanced WiFi Panel (Approach B)
**Files:** web/ui/utils/quick-settings.js, web/ui/components/SettingsPanel.js

## 1. Architecture & Scope
- Single panel enhancement in WifiSettings (quick-settings.js) + mirror to SettingsPanel.js for consistency. No new panel.
- New state wifiDraft.edgeTier (0/1/2) persisted in localStorage (wifisense-wifi-draft) with additive merge (like ssid/password) — Apply does not overwrite target_ip if unchanged.
- Backend reuse: POST /api/v1/config/apply -> firmware/provision.py --edge-tier X --port COMx, and GET /health + GET /api/v1/network/local-ip for live data. No new endpoints.
- Keep dynamic Target IP fix (192.168.0.140 vs hardcoded 192.168.1.75) from previous patch.

## 2. UI Components
- **Sensing Mode row** under COM Port: radio group [Hemat | Seimbang* | Responsif] with subtext pps ~1 / ~5 / ~15 and tooltip beban WiFi. Maps to tier 0/1/2. Default 1 if missing. Click updates wifiDraft.edgeTier, requires Apply to flash.
- **Live mini-bar** below Target IP: pps | var | presence indicator, polling /health every 1s (reuse fetchNetworkIp). Green when presence true, gray otherwise. Shows -- when health unreachable.
- **SSID guard**: if ssid contains _5GHz or 5G -> yellow warning "ESP32-S3 hanya 2.4GHz — ganti ke FLAMBOYAN'S_EXT" below SSID input. Non-blocking.
- Target IP instruction code tag updated dynamically to ${actualIp}:5005.

## 3. Data Flow & Error Handling
- Flow: init -> fetchNetworkIp + refreshWifiHealth -> render mini-bar -> user selects preset -> Apply -> POST /api/v1/config/apply {ssid, password, target_ip, edge_tier, port} -> backend provision.py --edge-tier -> flash NVS 0x9000 -> hard_reset -> health returns new tier.
- Error: COM not selected -> Apply disabled + toast "Pilih COM dulu"; 5GHz warning -> warning only; health fetch fail -> mini-bar shows --; provision fail -> toast error, draft kept in localStorage.

## 4. Testing
- Manual: COM4 connected -> Hemat->Apply -> health pps ~1; Responsif->Apply -> pps ~15; set SSID *_5GHz -> warning appears; Target IP stays 192.168.0.140 MATCH after refresh.
- Unit: node --check both JS files.
- No DB migration; localStorage default edgeTier=1.

## Decisions
- Chose Enhanced WiFi Panel (B) over Minimal (A) and Split Advanced (C) to fix 5GHz misconfig, pps confusion, and Target IP mismatch in one place.

