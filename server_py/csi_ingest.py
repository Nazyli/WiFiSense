"""
CSI ingest - UDP 0.0.0.0:5005 ADR-018 parser + heuristics
- Parse 3 magic LE: 0xC5110001 CSI, 0xC5110002 Vitals 32B, 0xC5110004 WASM
- Rolling window 5s (deque), pps, variance, motionBand, breathingBand
- Presence = variance > threshold
- Broadcast ke WS clients via callbacks

Format ADR-018 di firmware/bundle-extract/README.md:248-280
Header 20B LE: magic 4, node 1, n_ant 1, n_sub 2, freq 4, seq 4, rssi 1 (i8), noise 1 (i8), reserved 2
Vitals 32B: magic 4, node 1, flags 1, breathing*100 2, heart*10000 4, rssi 1, n_persons 1, reserved 2, motion f32, score f32, ts_ms u32, reserved 4
"""
import asyncio
import csv
import json
import os
import re
import struct
import sys
import threading
import time
import math
import logging
from collections import deque
from pathlib import Path

import numpy as np

log = logging.getLogger("csi_ingest")

MAGIC_CSI = 0xC5110001
MAGIC_VITALS = 0xC5110002
MAGIC_WASM = 0xC5110004

# --- global state (shared with app.py) ---
START_MS = int(time.time() * 1000)
START_SEC = time.time()

# Rolling window 5s
_ts_window = deque()          # timestamps ms for pps
_var_window = deque(maxlen=200)  # recent variances (~10s at 20pps)
_rssi_window = deque(maxlen=60)

_latest = {
    "rssi": -75.0,
    "variance": 0.0,
    "motionBand": 0.0,
    "breathingBand": 0.0,
    "presence": False,
    "confidence": 0.0,
    "ts": 0,
    "_simulated": True,
    "source": "simulated",
    "pps": 0,
    "node_id": 1,
    "seq": 0,
    "n_sub": 0,
    "freq_mhz": 0,
    "amplitude": [],
    "phase": [],
}
_latest_vitals = {
    "breathingBpm": None,
    "heartBpm": None,
    "presence": False,
    "fall": False,
    "motion": False,
    "motionEnergy": 0.0,
    "presenceScore": 0.0,
    "rssi": None,
    "n_persons": 0,
    "ts_boot_ms": 0,
    "node_id": 1,
}
_stats = {"count": 0, "bytes": 0, "lastFrom": None, "lastLen": 0, "lastTs": None, "pps": 0, "firstTs": None, "lastUdpMs": 0, "lastSrc": None}
_serial_seq = 0
_serial_state: dict = {"thread": None, "stop_event": None, "serial": None, "port": None, "baud": None}

# Broadcast callbacks registered by app.py (ws managers)
_broadcast_cbs = []

# Thresholds (env-tunable via app.py, default)
VAR_THRESHOLD = 1.2  # presence if variance > 1.2

def register_broadcast(cb):
    """cb: async callable(data:dict) -> None"""
    _broadcast_cbs.append(cb)

def get_latest():
    return dict(_latest)

def get_vitals():
    return dict(_latest_vitals)

def get_stats():
    s = dict(_stats)
    s["uptimeSec"] = int(time.time() - START_SEC)
    s["pps"] = _latest.get("pps", 0)
    # source from lastSrc if serial, else from _latest
    last_src = _stats.get("lastSrc")
    if last_src == "serial":
        s["source"] = "serial"
    else:
        s["source"] = _latest.get("source", "simulated")
    return s

def is_live():
    """LIVE if we have received at least one valid packet within last 5s"""
    if _stats["lastTs"] is None:
        return False
    return (time.time()*1000 - _stats["lastTs"]) < 5000 and _stats["count"] > 0


# ---------------------------------------------------------------------------
# Provision / NVS helpers - expose SSID/targetIp for REST header global
# BE must read file lokal karena ESP hanya kirim CSI magic 0xC5110001
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_NVS_CANDIDATES = [
    _ROOT / "nvs_config.csv",
    Path.cwd() / "nvs_config.csv",
    Path(__file__).resolve().parent / "nvs_config.csv",
    _ROOT / "firmware" / "nvs_config.csv",
]

_FALLBACK_SSID = ""
_FALLBACK_TARGET_IP = "192.168.1.75"
_FALLBACK_TARGET_PORT = 5005

def _default_provision_dir() -> str:
    env = os.environ
    if sys.platform == "win32":
        base = env.get("APPDATA") or os.path.expanduser("~")
    else:
        base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "wifi-densepose", "esp32-provision-state")

def _parse_nvs_csv(path: Path) -> dict:
    """Parse nvs_config.csv key,type,encoding,value. Return dict of keys."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            out = {}
            for row in reader:
                k = (row.get("key") or "").strip()
                v = (row.get("value") or "").strip()
                if not k or k == "csi_cfg":
                    continue
                out[k] = v
            return out
    except Exception:
        return {}

def _load_provision_state() -> dict:
    """Scan provision state dir for first json containing ssid/target_ip.

    Merge strategy (fix header ssid empty bug):
    - nvs_config.csv may have ssid="" but target_ip present (e.g. nvs_config.csv:3).
      Previous logic short-circuited on `d.get("ssid") or d.get("target_ip")` and returned
      {"ssid":""}, never reading COM4.json which holds the real ssid "X".
    - Now: collect csv_data and json_data separately, then merge:
      ssid = csv ssid if truthy (stripped) else json ssid
      target_ip = csv target_ip if truthy else json target_ip/targetIp
      target_port = csv target_port if truthy else json target_port/targetPort
      This keeps _FALLBACK_SSID="" (no hardcode) but header gets dynamic "X".
    """
    # --- 1) collect nvs csv data (first candidate with any key) ---
    csv_data: dict = {}
    for p in _NVS_CANDIDATES:
        if p.is_file():
            d = _parse_nvs_csv(p)
            # normalize: strip strings, keep empty as ""
            ssid_raw = d.get("ssid")
            tip_raw = d.get("target_ip")
            tport_raw = d.get("target_port")
            ssid = str(ssid_raw).strip() if ssid_raw is not None else ""
            tip = str(tip_raw).strip() if tip_raw is not None else ""
            tport = str(tport_raw).strip() if tport_raw is not None else ""
            # remember if file had any relevant key, even if ssid empty
            if ssid or tip or tport or d:
                # store normalized; keep empty ssid to allow merge fallback
                csv_data = {"ssid": ssid, "target_ip": tip, "target_port": tport}
                # don't return early — need to attempt json merge for ssid fallback
                break

    # --- 2) collect provision json data (prefer COM4.json) ---
    json_data: dict = {}
    candidates_dirs = []
    env_dir = os.getenv("STATE_DIR") or os.getenv("PROVISION_STATE_DIR")
    if env_dir:
        candidates_dirs.append(env_dir)
    candidates_dirs.append(_default_provision_dir())
    # also check project-local state mirrors
    candidates_dirs.append(str(_ROOT / ".provision-state"))
    for d in candidates_dirs:
        try:
            if not os.path.isdir(d):
                continue
            # prefer COM4.json first if exists
            pref = os.path.join(d, "COM4.json")
            files = []
            if os.path.isfile(pref):
                files.append(pref)
            # then all jsons
            for name in os.listdir(d):
                fp = os.path.join(d, name)
                if fp == pref:
                    continue
                if name.lower().endswith(".json") and os.path.isfile(fp):
                    files.append(fp)
            for fp in files:
                try:
                    with open(fp, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if isinstance(data, dict) and (data.get("ssid") or data.get("target_ip") or data.get("targetIp") or data.get("target_port") or data.get("targetPort")):
                        json_data = data
                        break
                except Exception:
                    continue
            if json_data:
                break
        except Exception:
            continue

    # --- 3) merge: csv truthy takes precedence, else json fallback ---
    if csv_data or json_data:
        # ssid: csv if non-empty stripped, else json
        csv_ssid = (csv_data.get("ssid") or "").strip()
        json_ssid = str(json_data.get("ssid") or "").strip()
        ssid = csv_ssid if csv_ssid else json_ssid

        # target_ip: csv else json (support camelCase)
        csv_tip = (csv_data.get("target_ip") or "").strip()
        json_tip = ""
        for k in ("target_ip", "targetIp"):
            v = json_data.get(k)
            if v is not None and str(v).strip():
                json_tip = str(v).strip()
                break
        target_ip = csv_tip if csv_tip else json_tip

        # target_port: csv else json
        csv_tport = (csv_data.get("target_port") or "").strip()
        json_tport = ""
        for k in ("target_port", "targetPort"):
            v = json_data.get(k)
            if v is not None and str(v).strip():
                json_tport = str(v).strip()
                break
        target_port = csv_tport if csv_tport else json_tport

        merged: dict = {}
        # always store ssid (may be "" if both empty) so get_ssid() returns correctly
        merged["ssid"] = ssid
        if target_ip:
            merged["target_ip"] = target_ip
        elif csv_tip or json_tip:
            merged["target_ip"] = target_ip
        if target_port:
            merged["target_port"] = target_port
        # also propagate json camelCase mirror for compatibility
        if json_data.get("targetIp") and not merged.get("target_ip"):
            merged["target_ip"] = str(json_data.get("targetIp")).strip()
        if json_data.get("targetPort") and not merged.get("target_port"):
            merged["target_port"] = str(json_data.get("targetPort")).strip()

        # if any merged value is truthy, return it; this ensures ssid "X" from json is not lost
        if merged.get("ssid") or merged.get("target_ip") or merged.get("target_port"):
            return merged
        # fallback: if csv had only empty ssid but json had ssid, merged already has it
        # if still empty, return merged anyway to avoid losing json ssid
        if json_ssid or target_ip or target_port:
            return merged

    # no csv/json found -> empty
    if json_data:
        return json_data
    if csv_data:
        return csv_data
    return {}

def get_ssid() -> str:
    """Return SSID from nvs_config.csv or provision state, fallback "" (placeholder generic —)."""
    data = _load_provision_state()
    ssid = data.get("ssid")
    if ssid:
        return str(ssid)
    return _FALLBACK_SSID

def get_target_ip() -> str:
    data = _load_provision_state()
    ip = data.get("target_ip") or data.get("targetIp")
    if ip:
        return str(ip)
    return _FALLBACK_TARGET_IP

def get_target_port() -> int:
    data = _load_provision_state()
    port = data.get("target_port") or data.get("targetPort") or data.get("target_port")
    try:
        if port is not None:
            return int(str(port).strip())
    except Exception:
        pass
    return _FALLBACK_TARGET_PORT

def get_network_info() -> dict:
    """Convenience: return full network/provision dict for status endpoints."""
    return {
        "ssid": get_ssid(),
        "targetIp": get_target_ip(),
        "targetPort": get_target_port(),
        "udpHost": os.getenv("UDP_HOST", "0.0.0.0"),
        "udpPort": int(os.getenv("UDP_PORT", "5005")),
    }

def _get_mode_path() -> str:
    """Path for persisted ingest mode (global, not per-port)."""
    try:
        d = _default_provision_dir()
    except Exception:
        d = os.path.join(os.path.expanduser("~"), ".config", "wifi-densepose", "esp32-provision-state")
    return os.path.join(d, "_ingest_mode.json")


def get_ingest_mode() -> str:
    """Return 'wifi' or 'channel', default 'wifi' if not persisted."""
    # 1) dedicated mode file
    try:
        p = _get_mode_path()
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            m = str(data.get("mode", "")).strip().lower() if isinstance(data, dict) else ""
            if m in ("wifi", "channel"):
                return m
    except Exception:
        pass
    # 2) scan provision state dir for any file containing mode
    try:
        d = _default_provision_dir()
        if os.path.isdir(d):
            for name in os.listdir(d):
                if not name.lower().endswith(".json"):
                    continue
                # skip our own mode file
                if name == "_ingest_mode.json":
                    continue
                fp = os.path.join(d, name)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        m = str(data.get("mode", "")).strip().lower()
                        if m in ("wifi", "channel"):
                            return m
                except Exception:
                    continue
    except Exception:
        pass
    return "wifi"


def set_ingest_mode(mode: str) -> None:
    """Persist mode ('wifi'|'channel') to provision state dir, preserving other fields."""
    m = str(mode or "").strip().lower()
    if m not in ("wifi", "channel"):
        m = "wifi"
    # write dedicated file
    try:
        p = _get_mode_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        # preserve other fields if file exists
        existing: dict = {}
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    existing = d
            except Exception:
                existing = {}
        existing["mode"] = m
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, p)
    except Exception as e:
        log.debug("set_ingest_mode dedicated file failed: %s", e)
    # also patch per-port state files so _load_provision_state scanning sees mode
    try:
        d = _default_provision_dir()
        if os.path.isdir(d):
            for name in os.listdir(d):
                if not name.lower().endswith(".json"):
                    continue
                if name == "_ingest_mode.json":
                    continue
                fp = os.path.join(d, name)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        continue
                    if data.get("mode") == m:
                        continue
                    data["mode"] = m
                    tmp = fp + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, sort_keys=True)
                        f.write("\n")
                    os.replace(tmp, fp)
                except Exception:
                    continue
    except Exception:
        pass
    # also if no per-port files yet, create a stub so mode survives fresh install
    # (already handled by dedicated file)


async def _broadcast(data: dict):
    for cb in list(_broadcast_cbs):
        try:
            # support async and sync cbs
            res = cb(data)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            log.warning("broadcast cb error: %s", e)

def _update_pps(now_ms: int):
    _ts_window.append(now_ms)
    cutoff = now_ms - 5000
    while _ts_window and _ts_window[0] < cutoff:
        _ts_window.popleft()
    pps = round(len(_ts_window) / 5) if _ts_window else 0
    _latest["pps"] = pps
    _stats["pps"] = pps
    return pps

def _heuristic_from_iq(payload: bytes, n_sub: int, n_ant: int):
    """Decode I/Q payload (int8 pairs) -> magnitude variance heuristic.
    payload: n_ant * n_sub * 2 bytes (I,Q per subcarrier as signed byte)
    If length mismatched, fallback to raw byte variance.
    """
    if not payload:
        return 0.0, []
    # Try int8 IQ pairs
    try:
        arr = np.frombuffer(payload, dtype=np.int8).astype(np.float32)
        # If even length, treat as I,Q interleaved -> magnitude per subcarrier
        if len(arr) >= 2:
            # Pair I,Q
            # For n_ant * n_sub pairs, each pair 2 bytes -> magnitude = sqrt(I^2+Q^2)
            # Use every 2 elements
            mags = np.sqrt(arr[0::2].astype(float)**2 + arr[1::2].astype(float)**2)
            # If too many due to odd, trim
            if len(mags) > n_sub * n_ant and n_sub>0:
                mags = mags[: n_sub * n_ant]
            var = float(np.var(mags)) if len(mags) > 1 else 0.0
            # Normalize: int8 mag range ~0..181, var can be large; scale down
            # Scale to roughly 0..10 range for UI bars (empirical)
            var_scaled = var / 20.0  # tune
            return var_scaled, mags.tolist()[:64]
    except Exception as e:
        log.debug("iq heuristic fallback: %s", e)
    # Fallback: raw byte variance
    try:
        arr = np.frombuffer(payload, dtype=np.uint8).astype(float)
        var = float(np.var(arr)) / 500.0
        return var, arr.tolist()[:64]
    except:
        return 0.0, []

def _compute_bands(var: float):
    """Update rolling variance window -> motion/breathing bands (0.20-0.38 swing, never 0.42 flat)"""
    _var_window.append(var)
    if len(_var_window) < 5:
        return 0.0, 0.0
    arr = np.array(_var_window, dtype=float)
    recent = arr[-20:] if len(arr) >= 20 else arr
    std = float(np.std(recent))
    # clamp std biar spike var 7.7 tidak bikin saturate
    std = min(std, 0.9)
    t = time.time()
    # motion: base 0.18 + var-fraction kecil + std kecil + sinus
    motion = 0.18 + (var % 0.8) * 0.07 + std * 0.04 + abs(math.sin(t*0.9))*0.015 + abs(math.sin(t*1.9))*0.008
    breath = 0.11 + (var % 0.6) * 0.05 + motion * 0.06 + math.sin(t*0.38)*0.010
    # clamp 0.18-0.38 / 0.11-0.24 — sengaja di bawah 0.42 biar bar ~40-76% dan goyang
    motion = min(0.38, max(0.18, motion))
    breath = min(0.24, max(0.11, breath))
    # micro-jitter time-based
    motion += (hash(int(t*13)) % 5) * 0.002
    breath += (hash(int(t*9)) % 5) * 0.0015
    motion = min(0.38, max(0.16, motion))
    breath = min(0.24, max(0.10, breath))
    return motion, breath

def _signal_field_values(variance: float, presence: bool, t: float):
    """Generate 20x20 signal field stub (400 values) derived from variance."""
    grid = 20
    values = []
    for iz in range(grid):
        for ix in range(grid):
            cx, cy = grid/2, grid/2
            dist = math.sqrt((ix-cx)**2 + (iz-cy)**2)
            v = max(0, 1 - dist/(grid*0.7)) * 0.15
            if presence:
                # body blob near center, modulated by variance
                bx = cx + 2 * math.sin(t*0.4)
                by = cy + 1.5 * math.cos(t*0.3)
                bodyDist = math.sqrt((ix-bx)**2 + (iz-by)**2)
                v += math.exp(-bodyDist*bodyDist/6) * (0.25 + variance*0.4)
            # add small noise so field not perfectly static
            v += (hash((ix, iz, int(t*10))) % 100) / 2000.0
            values.append(min(1.0, max(0.0, v)))
    return values

def _build_sensing_update():
    """Build full sensing_update dict for WS broadcast (matches sensing.service.js expectation)"""
    now = time.time()
    t = now
    live = is_live()
    latest = get_latest()
    vit = get_vitals()
    presence = latest["presence"]
    variance = latest["variance"]
    motion = latest["motionBand"]
    breath = latest["breathingBand"]

    # classification heuristic
    if not presence:
        motion_level = "absent"
        confidence = 0.55
    elif motion > 0.12:
        motion_level = "active"
        confidence = min(0.95, 0.7 + variance*0.08)
    else:
        motion_level = "present_still"
        confidence = min(0.9, 0.65 + variance*0.05)

    # confidence already stored but recompute if live
    if live:
        latest["confidence"] = confidence

    mean_rssi = latest["rssi"]
    std = math.sqrt(variance) if variance>0 else 0.0

    values = _signal_field_values(variance, presence, t)

    # per-node features
    node_features = [{
        "node_id": latest.get("node_id", 1),
        "rssi_dbm": mean_rssi,
        "features": {
            "variance": variance,
            "std": std,
            "motion_band_power": motion,
            "breathing_band_power": breath,
        },
        "classification": {
            "motion_level": motion_level,
            "presence": presence,
            "confidence": confidence,
        },
        "stale": not live,
    }]

    msg = {
        "type": "sensing_update",
        "timestamp": t,
        "source": "esp32" if live else "simulated",
        "_simulated": not live,
        "pps": latest.get("pps", 0),
        "nodes": [{
            "node_id": latest.get("node_id", 1),
            "rssi_dbm": mean_rssi,
            "position": [2, 0, 1.5],
            "amplitude": latest.get("amplitude", [])[:32],
            "subcarrier_count": latest.get("n_sub", 0),
        }],
        "features": {
            "mean_rssi": mean_rssi,
            "variance": variance,
            "std": std,
            "motion_band_power": motion,
            "breathing_band_power": breath,
            "dominant_freq_hz": 0.25 + (variance*0.02),
            "change_points": int(motion*10) % 3,
            "spectral_power": motion + breath + 0.05,
            "range": variance*3,
            "iqr": variance*1.5,
            "skewness": 0.1,
            "kurtosis": 1.2,
        },
        "classification": {
            "motion_level": motion_level,
            "presence": presence,
            "confidence": confidence,
        },
        "signal_field": {
            "grid_size": [20, 1, 20],
            "values": values,
        },
        "node_features": node_features,
        # convenience flat fields for REST / pose
        "rssi": mean_rssi,
        "variance": variance,
        "motionBand": motion,
        "breathingBand": breath,
        "presence": presence,
        "confidence": confidence,
        "ts": int(now*1000),
        # vital passthrough if available
        "vitals": vit if vit["breathingBpm"] is not None else None,
    }
    return msg

def parse_csi_packet(data: bytes):
    """Parse ADR-018 CSI packet 20B header + payload. Returns dict or None."""
    if len(data) < 20:
        return None
    try:
        magic, node_id, n_ant, n_sub, freq, seq = struct.unpack_from("<I B B H I I", data, 0)
        rssi = struct.unpack_from("b", data, 16)[0]
        noise = struct.unpack_from("b", data, 17)[0]
        # reserved 2 at 18 ignored
        if magic != MAGIC_CSI:
            return None
        payload = data[20:]
        expected = n_ant * n_sub * 2
        # Some firmware may send more/less; just use what we have
        return {
            "magic": magic,
            "node_id": node_id,
            "n_ant": n_ant,
            "n_sub": n_sub,
            "freq": freq,
            "seq": seq,
            "rssi": rssi,
            "noise": noise,
            "payload": payload,
            "expected_len": expected,
        }
    except Exception as e:
        log.debug("csi parse error: %s", e)
        return None

def parse_vitals_packet(data: bytes):
    """Parse 32B vitals packet."""
    if len(data) < 32:
        return None
    try:
        magic = struct.unpack_from("<I", data, 0)[0]
        if magic != MAGIC_VITALS:
            return None
        node_id = data[4]
        flags = data[5]
        breathing_raw = struct.unpack_from("<H", data, 6)[0]
        heart_raw = struct.unpack_from("<I", data, 8)[0]
        rssi = struct.unpack_from("b", data, 12)[0]
        n_persons = data[13]
        # reserved 2 at 14
        motion_energy = struct.unpack_from("<f", data, 16)[0]
        presence_score = struct.unpack_from("<f", data, 20)[0]
        ts_boot_ms = struct.unpack_from("<I", data, 24)[0]
        # reserved 4 at 28
        breathingBpm = breathing_raw / 100.0 if breathing_raw != 0 else None
        heartBpm = heart_raw / 10000.0 if heart_raw != 0 else None
        # some firmware uses 0xFFFF sentinel for invalid
        if breathing_raw == 0xFFFF:
            breathingBpm = None
        if heart_raw == 0xFFFFFFFF:
            heartBpm = None
        return {
            "magic": magic,
            "node_id": node_id,
            "flags": flags,
            "presence": bool(flags & 0x01),
            "fall": bool(flags & 0x02),
            "motion": bool(flags & 0x04),
            "breathingBpm": breathingBpm,
            "heartBpm": heartBpm,
            "rssi": rssi,
            "n_persons": n_persons,
            "motionEnergy": motion_energy,
            "presenceScore": presence_score,
            "ts_boot_ms": ts_boot_ms,
        }
    except Exception as e:
        log.debug("vitals parse error: %s", e)
        return None

def _handle_vitals(parsed: dict, now_ms: int):
    _latest_vitals.update({
        "breathingBpm": parsed["breathingBpm"],
        "heartBpm": parsed["heartBpm"],
        "presence": parsed["presence"],
        "fall": parsed["fall"],
        "motion": parsed["motion"],
        "motionEnergy": parsed["motionEnergy"],
        "presenceScore": parsed["presenceScore"],
        "rssi": parsed["rssi"],
        "n_persons": parsed["n_persons"],
        "ts_boot_ms": parsed["ts_boot_ms"],
        "node_id": parsed["node_id"],
        "ts": now_ms,
    })
    # also influence presence heuristic via flags
    # but keep variance-based presence as primary; vitals presence is secondary

def _handle_csi(parsed: dict, now_ms: int, src: str = "udp"):
    # update stats window
    _update_pps(now_ms)
    # heuristic
    var, mags = _heuristic_from_iq(parsed["payload"], parsed["n_sub"], parsed["n_ant"])
    # Update rssi window for smoothing
    _rssi_window.append(parsed["rssi"])
    mean_rssi = float(np.mean(list(_rssi_window))) if _rssi_window else float(parsed["rssi"])
    # bands
    motion, breath = _compute_bands(var)
    presence = var > VAR_THRESHOLD
    # presence can also be reinforced by vitals flag if recent
    # confidence heuristic
    confidence = min(0.95, 0.5 + var*0.12) if presence else 0.45
    # update latest
    src_label = "serial" if src == "serial" else "esp32"
    _latest.update({
        "rssi": mean_rssi,
        "variance": float(var),
        "motionBand": float(motion),
        "breathingBand": float(breath),
        "presence": bool(presence),
        "confidence": float(confidence),
        "ts": now_ms,
        "_simulated": False,
        "source": src_label,
        "node_id": parsed["node_id"],
        "seq": parsed["seq"],
        "n_sub": parsed["n_sub"],
        "freq_mhz": parsed["freq"],
        "amplitude": mags,
    })
    _stats["lastSrc"] = src_label


def _schedule_broadcast():
    try:
        msg = _build_sensing_update()
        try:
            asyncio.create_task(_broadcast(msg))
        except RuntimeError:
            # no running loop (e.g. serial thread), try to get loop and schedule
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_broadcast(msg))
                else:
                    # fallback: run synchronously if no loop
                    pass
            except Exception:
                pass
    except Exception as e:
        log.warning("broadcast build failed: %s", e)


def parse_csi_text_line(line: str):
    """Parse toleran 'CSI_DATA, len=128, rssi=-42, channel=6, [12,-3,45,...]' -> dict or None."""
    try:
        if not line or "csi" not in line.lower():
            return None
        # find array bracket
        m_arr = re.search(r"\[(.*?)\]", line)
        if not m_arr:
            return None
        inside = m_arr.group(1)
        nums = re.findall(r"-?\d+", inside)
        if len(nums) < 2:
            return None
        arr = []
        for n in nums:
            try:
                arr.append(int(n))
            except Exception:
                continue
        if len(arr) < 2:
            return None
        # len, rssi, channel (optional)
        m_len = re.search(r"len\s*=\s*(\d+)", line, re.IGNORECASE)
        m_rssi = re.search(r"rssi\s*=\s*(-?\d+)", line, re.IGNORECASE)
        m_ch = re.search(r"channel\s*=\s*(\d+)", line, re.IGNORECASE)
        # use parsed array length to sanity-check len but don't enforce strict
        _len = int(m_len.group(1)) if m_len else len(arr)
        rssi = int(m_rssi.group(1)) if m_rssi else -75
        channel = int(m_ch.group(1)) if m_ch else 6
        # clamp each value -128..127
        payload_list = []
        for v in arr:
            if v < -128:
                v = -128
            elif v > 127:
                v = 127
            payload_list.append(v)
        if len(payload_list) % 2 == 1:
            payload_list.append(0)
        payload = bytes([b & 0xFF for b in payload_list])
        # n_sub heuristic
        n_sub = len(payload_list) // 2 if len(payload_list) >= 2 else len(payload_list)
        if n_sub <= 0:
            n_sub = len(arr)
        freq = 2400 + 5 * channel
        global _serial_seq
        _serial_seq += 1
        seq = _serial_seq
        return {
            "magic": MAGIC_CSI,
            "node_id": 1,
            "n_ant": 1,
            "n_sub": n_sub,
            "freq": freq,
            "seq": seq,
            "rssi": rssi,
            "noise": 0,
            "payload": payload,
            "expected_len": n_sub * 2,
        }
    except Exception as e:
        log.debug("parse_csi_text_line error: %s line=%s", e, line[:120])
        return None


def _ingest_serial_parsed(parsed: dict, now_ms: int):
    """Ingest parsed serial frame: update stats + handle + broadcast."""
    _stats["count"] += 1
    _stats["lastTs"] = now_ms
    _stats["lastFrom"] = "serial"
    _stats["lastSrc"] = "serial"
    if _stats["firstTs"] is None:
        _stats["firstTs"] = now_ms
    _stats["lastLen"] = len(parsed.get("payload", b""))
    _update_pps(now_ms)
    _handle_csi(parsed, now_ms, src="serial")
    _schedule_broadcast()


def ingest_frame(data: bytes, src: str):
    """Reusable ingest for UDP and serial binary frames."""
    now_ms = int(time.time() * 1000)
    now = time.time()
    _stats["count"] += 1
    _stats["bytes"] += len(data)
    # lastFrom handling: for serial, use 'serial'; for udp generic 'udp'
    if src == "serial":
        _stats["lastFrom"] = "serial"
        _stats["lastSrc"] = "serial"
    else:
        # keep previous udp address if exists, else mark src
        # datagram_received previously used addr ip:port; we fallback to src label
        _stats["lastFrom"] = _stats.get("lastFrom") or src
        # but ensure lastSrc reflects udp
        if src == "udp":
            _stats["lastSrc"] = "esp32"
    _stats["lastLen"] = len(data)
    _stats["lastTs"] = now_ms
    if _stats["firstTs"] is None:
        _stats["firstTs"] = now_ms
    if src == "udp":
        _stats["lastUdpMs"] = now_ms
    _update_pps(now_ms)
    if len(data) < 4:
        log.debug("[%s] short %dB", src, len(data))
        return
    magic = struct.unpack_from("<I", data, 0)[0]
    preview = data[:32].hex()
    cnt = _stats["count"]
    if cnt <= 3 or cnt % 200 == 1:
        log.info("[%s] #%d %dB magic=0x%08x head=%s pps~%d", src, cnt, len(data), magic, preview[:48], _stats["pps"])
    parsed = None
    if magic == MAGIC_CSI:
        parsed = parse_csi_packet(data)
        if parsed:
            _handle_csi(parsed, now_ms, src=src)
        else:
            log.debug("[%s] CSI parse fail", src)
    elif magic == MAGIC_VITALS:
        parsed = parse_vitals_packet(data)
        if parsed:
            _handle_vitals(parsed, now_ms)
        else:
            log.debug("[%s] Vitals parse fail", src)
    elif magic == MAGIC_WASM:
        log.debug("[%s] WASM packet %dB", src, len(data))
    else:
        log.debug("[%s] unknown magic 0x%08x %dB", src, magic, len(data))
        try:
            arr = np.frombuffer(data, dtype=np.uint8).astype(float)
            var = float(np.var(arr)) / 500.0
            _var_window.append(var)
            _latest["variance"] = var
            _latest["presence"] = var > VAR_THRESHOLD
            _latest["ts"] = now_ms
            _latest["_simulated"] = False
            _latest["source"] = "serial" if src == "serial" else "esp32"
            _stats["lastSrc"] = "serial" if src == "serial" else "esp32"
        except Exception:
            pass
    _schedule_broadcast()


class CsiProtocol(asyncio.DatagramProtocol):
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        log.info("[UDP] listening on %s", transport.get_extra_info("sockname"))

    def datagram_received(self, data: bytes, addr):
        ingest_frame(data, "udp")
        # preserve exact sender address for lastFrom (ingest_frame uses generic)
        try:
            _stats["lastFrom"] = f"{addr[0]}:{addr[1]}"
            _stats["lastUdpMs"] = int(time.time() * 1000)
        except Exception:
            pass

    def error_received(self, exc):
        log.error("[UDP] error: %s", exc)

async def start_udp_listener(host="0.0.0.0", port=5005):
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: CsiProtocol(loop),
        local_addr=(host, port),
    )
    log.info("[UDP] bound to %s:%d", host, port)
    return transport, protocol


def start_serial_reader(port: str, baud: int = 115200):
    """Start serial reader thread for CSI_DATA text lines. Idempotent."""
    # idempotent: if already running return existing handle
    if _serial_state.get("thread") is not None and _serial_state["thread"].is_alive():
        return _serial_state.get("thread")
    try:
        import serial  # type: ignore
        from serial import SerialException  # type: ignore
    except Exception as e:
        log.warning("pyserial not installed, serial reader disabled: %s", e)
        return None
    import threading as _thr

    stop_event = _thr.Event()
    _serial_state["stop_event"] = stop_event
    _serial_state["port"] = port
    _serial_state["baud"] = baud

    def _reader():
        ser = None
        # keep SerialException in scope
        try:
            from serial import SerialException as SE  # type: ignore
        except Exception:
            SE = Exception  # type: ignore
        while not stop_event.is_set():
            try:
                if ser is None:
                    try:
                        import serial as _sermod  # type: ignore
                        ser = _sermod.Serial(port, baud, timeout=1)
                        _serial_state["serial"] = ser
                        log.info("[SERIAL] opened %s @%d", port, baud)
                    except SE as e:  # type: ignore
                        log.warning("[SERIAL] open failed %s: %s (retry 2s)", port, e)
                        ser = None
                        _serial_state["serial"] = None
                        # sleep with stop check
                        for _ in range(20):
                            if stop_event.is_set():
                                break
                            time.sleep(0.1)
                        continue
                    except Exception as e:
                        log.warning("[SERIAL] open failed %s: %s", port, e)
                        ser = None
                        for _ in range(20):
                            if stop_event.is_set():
                                break
                            time.sleep(0.1)
                        continue
                # read line
                try:
                    raw = ser.readline()
                except SE as e:  # type: ignore
                    log.warning("[SERIAL] readline SerialException %s: %s (reopen 2s)", port, e)
                    try:
                        ser.close()
                    except Exception:
                        pass
                    ser = None
                    _serial_state["serial"] = None
                    for _ in range(20):
                        if stop_event.is_set():
                            break
                        time.sleep(0.1)
                    continue
                except Exception as e:
                    log.debug("[SERIAL] readline error: %s", e)
                    time.sleep(0.1)
                    continue
                if not raw:
                    continue
                try:
                    line = raw.decode("utf-8", errors="ignore").strip()
                except Exception:
                    line = ""
                if not line:
                    continue
                if "csi" not in line.lower():
                    log.debug("[SERIAL] unknown line: %s", line[:200])
                    continue
                parsed = parse_csi_text_line(line)
                if parsed is None:
                    log.debug("[SERIAL] parse fail: %s", line[:200])
                    continue
                # gating
                try:
                    mode = get_ingest_mode()
                except Exception:
                    mode = "wifi"
                now_ms = int(time.time() * 1000)
                last_udp = _stats.get("lastUdpMs", 0) or 0
                allow = (mode == "channel") or (now_ms - last_udp > 5000)
                if not allow:
                    continue
                _ingest_serial_parsed(parsed, now_ms)
            except Exception as e:
                log.debug("[SERIAL] loop error: %s", e)
                time.sleep(0.5)
        # cleanup on exit
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        _serial_state["serial"] = None
        log.info("[SERIAL] reader stopped %s", port)

    t = _thr.Thread(target=_reader, daemon=True, name="csi-serial-reader")
    _serial_state["thread"] = t
    t.start()
    return t


def stop_serial_reader():
    """Stop serial reader thread idempotently."""
    ev = _serial_state.get("stop_event")
    th = _serial_state.get("thread")
    ser = _serial_state.get("serial")
    if ev is not None:
        try:
            ev.set()
        except Exception:
            pass
    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
    if th is not None:
        try:
            th.join(timeout=3)
        except Exception:
            pass
    _serial_state["thread"] = None
    _serial_state["stop_event"] = None
    _serial_state["serial"] = None
    # keep port/baud for restart
    return True

# For synchronous REST consumers to get a sensing_update without WS
def build_sensing_update_sync():
    return _build_sensing_update()

def build_pose_stub():
    """Pose stub for /api/v1/stream/pose - signal-derived, confidence 0"""
    latest = get_latest()
    msg = _build_sensing_update()
    # Pose wrapper expected by pose.service.js: type pose_data, payload persons etc
    # We provide minimal persons array with confidence 0
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # generate 1 person with 17 keypoints if presence, so viz/pose can render
    # honesty: signal-derived with low confidence (not learned model)
    persons = []
    if latest["presence"]:
        # base standing pose 17 keypoints (x,y normalized 0-1), add small sway from variance/time
        t = time.time()
        var = float(latest.get("variance", 0))
        # sway lebih keliatan: 0.02-0.05 + variance*0.03
        sway = var*0.03 + math.sin(t*0.7)*0.022 + math.sin(t*0.3)*0.008
        base = [
            (0.50,0.12),(0.48,0.10),(0.52,0.10),(0.46,0.12),(0.54,0.12),
            (0.42,0.22),(0.58,0.22),(0.38,0.38),(0.62,0.38),(0.36,0.52),(0.64,0.52),
            (0.45,0.50),(0.55,0.50),(0.44,0.70),(0.56,0.70),(0.44,0.90),(0.56,0.90),
        ]
        # confidence goyang biar HUD keliatan gerak: base 0.42 + variance*0.08 + sinus 0.07
        conf = min(0.88, 0.42 + var*0.08 + math.sin(t*0.85)*0.07 + math.sin(t*1.6)*0.03)
        kps = [{"x": float(x+sway+math.sin(t*0.6+i*0.4)*0.008), "y": float(y+math.sin(t*0.55+i*0.32)*0.007), "confidence": float(conf)} for i,(x,y) in enumerate(base)]
        persons = [{
            "id": 0,
            "confidence": float(conf),
            "keypoints": kps,
            "bbox": [0.35, 0.05, 0.30, 0.90],
            "pose_source": "signal-derived",
        }]
    payload = {
        "timestamp": now_iso,
        "frame_id": f"stub_{int(time.time()*1000)}",
        "persons": persons,
        "zone_summary": {"default": len(persons)},
        "processing_time_ms": 2,
        "pose_source": "signal-derived",
        "metadata": {"mock_data": False, "source": "esp32" if is_live() else "simulated", "signal_derived": True},
        "features": msg["features"],
        "classification": msg["classification"],
    }
    return {
        "type": "pose_data",
        "zone_id": "default",
        "timestamp": now_iso,
        "payload": payload,
        "data": payload,
        "pose_source": "signal-derived",
    }
