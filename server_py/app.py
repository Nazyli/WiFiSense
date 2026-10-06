"""
WiFiSense Python shim — FastAPI + uvicorn, meniru 6 kontrak Rust sensing-server
agar UI 100% RuView (web/ui/) banner hijau LIVE-ESP32 tanpa Rust.

Kontrak:
- GET /health, /health/health, /health/live, /health/ready
- GET /api/v1/sensing/latest
- GET /api/v1/vital-signs
- GET /api/v1/model/info
- WS /ws/sensing
- WS /api/v1/stream/pose
+ static /ui dan / (index.html)

Run: pip install -r requirements.txt ; uvicorn server_py.app:app --port 3000 --reload
Secondary WS proxy on 3001 otomatis aktif bila port utama 3000 (untuk sensing.service mapping 3000->3001)
"""
import asyncio
import glob as globmod
import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import csi_ingest

log = logging.getLogger("server_py")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from collections import deque

LOG_BUFFER: deque = deque(maxlen=300)


class MemoryHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOG_BUFFER.append(
                {
                    "ts": int(time.time() * 1000),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
            )
        except Exception:
            pass


logging.getLogger().addHandler(MemoryHandler(level=logging.INFO))
log.addHandler(MemoryHandler(level=logging.INFO))

# --- paths ---
ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "web" / "ui"
if not UI_DIR.exists():
    # fallback for docker / alternate mounts
    UI_DIR = Path.cwd() / "web" / "ui"

START_TIME = time.time()
UDP_HOST = os.getenv("UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("UDP_PORT", "5005"))
ENABLE_UDP = os.getenv("ENABLE_UDP", "1") not in ("0", "false", "False")
ENABLE_SECONDARY = os.getenv("ENABLE_SECONDARY_PROXY", "1") not in ("0", "false", "False")
SECONDARY_PORT = int(os.getenv("SECONDARY_PROXY_PORT", "3001"))
ENABLE_SERIAL = os.getenv("ENABLE_SERIAL", "0") not in ("0", "false", "False")
SERIAL_PORT = os.getenv("SERIAL_PORT", "COM4")
SERIAL_BAUD = int(os.getenv("SERIAL_BAUD", "115200"))

app = FastAPI(title="WiFiSense Python shim", version="0.8.8-py")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WS managers ---
sensing_clients: Set[WebSocket] = set()
pose_clients: Set[WebSocket] = set()
_clients_lock = asyncio.Lock()

async def broadcast_sensing(data: dict):
    # called from csi_ingest via register_broadcast
    dead = []
    for ws in list(sensing_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        sensing_clients.discard(ws)
    # also forward a pose-wrapped version to pose clients for live demo
    if pose_clients:
        pose_msg = csi_ingest.build_pose_stub()
        # ensure pose_msg reflects latest data; rebuild fresh already includes current timestamp
        dead2 = []
        for ws in list(pose_clients):
            try:
                await ws.send_json(pose_msg)
            except Exception:
                dead2.append(ws)
        for ws in dead2:
            pose_clients.discard(ws)

# register early so csi_ingest can broadcast even before startup completes
csi_ingest.register_broadcast(broadcast_sensing)

# --- helpers ---
def _health_payload():
    stats = csi_ingest.get_stats()
    latest = csi_ingest.get_latest()
    vitals = csi_ingest.get_vitals()
    live = csi_ingest.is_live()
    # source = 'serial' bila last frame dari serial, else esp32/simulated
    if stats.get("source") == "serial":
        source = "serial"
    else:
        source = "esp32" if live else "simulated"
    # provision network info (ssid/targetIp from NVS or COM4.json fallback)
    try:
        ssid = csi_ingest.get_ssid()
    except Exception:
        ssid = ""
    try:
        target_ip = csi_ingest.get_target_ip()
    except Exception:
        target_ip = "192.168.1.75"
    try:
        target_port = csi_ingest.get_target_port()
    except Exception:
        target_port = 5005
    # timestamp: prefer latest ts, else vitals ts, else now
    ts = latest.get("ts") or vitals.get("ts") or int(time.time() * 1000)
    # status: healthy bila live, degraded bila simulated; unhealthy only if explicitly offline
    # For guard FE: expects healthy/degraded/unhealthy, bukan "ok"
    # Verify expects healthy saat BE reachable (fresh start packets==0 tetap healthy)
    pps = stats.get("pps", 0)
    packets = stats.get("count", 0)
    csi_status = "healthy" if live else "degraded"
    if live:
        status = "healthy"
    else:
        # fresh start (no packets yet) -> API tetap healthy; degraded hanya bila pernah live lalu drop
        status = "healthy" if packets == 0 else "degraded"
    return {
        "status": status,
        "environment": "development",
        "source": source,
        "uptimeSec": int(time.time() - START_TIME),
        "pps": pps,
        "packets": packets,
        "udpListening": True if ENABLE_UDP else False,
        "udpHost": UDP_HOST,
        "udpPort": UDP_PORT,
        "lastFrom": stats.get("lastFrom"),
        "ssid": ssid,
        "targetIp": target_ip,
        "targetPort": target_port,
        "rssi": latest.get("rssi", -75.0),
        "variance": latest.get("variance", 0.0),
        "motionBand": latest.get("motionBand", 0.0),
        "breathingBand": latest.get("breathingBand", 0.0),
        "presence": latest.get("presence", False),
        "confidence": latest.get("confidence", 0.0),
        "timestamp": ts,
        "breathingBpm": vitals.get("breathingBpm"),
        "heartBpm": vitals.get("heartBpm"),
        # FE DashboardTab expects components + metrics agar tidak undefined
        "components": {"api": {"status": "healthy", "message": "API server is running normally"}, "csi": {"status": csi_status, "message": "CSI " + csi_status}},
        "metrics": {"pps": pps, "packets": packets},
    }

def _sensing_latest_payload():
    latest = csi_ingest.get_latest()
    live = csi_ingest.is_live()
    # ensure ts is ms epoch; if 0 (no data), use now but mark simulated
    ts = latest.get("ts") or int(time.time()*1000)
    # sensing_update full for convenience, but REST spec wants flat fields
    msg = csi_ingest.build_sensing_update_sync()
    return {
        # flat REST fields per deliverable
        "rssi": latest.get("rssi", -75.0),
        "variance": latest.get("variance", 0.0),
        "motionBand": latest.get("motionBand", 0.0),
        "breathingBand": latest.get("breathingBand", 0.0),
        "presence": latest.get("presence", False),
        "confidence": latest.get("confidence", 0.0),
        "ts": ts,
        "_simulated": not live,
        "source": "esp32" if live else "simulated",
        "pps": latest.get("pps", 0),
        "node_id": latest.get("node_id", 1),
        # snake aliases for legacy UI consumers
        "mean_rssi": latest.get("rssi", -75.0),
        "motion_band_power": latest.get("motionBand", 0.0),
        "breathing_band_power": latest.get("breathingBand", 0.0),
        # extended (optional) full features for richer UI
        "features": msg.get("features"),
        "classification": msg.get("classification"),
        "nodes": msg.get("nodes"),
        "signal_field": msg.get("signal_field"),
    }

def _vitals_payload():
    v = csi_ingest.get_vitals()
    live = csi_ingest.is_live()
    return {
        "breathingBpm": v.get("breathingBpm"),
        "heartBpm": v.get("heartBpm"),
        "note": "heuristic-only",
        "presence": v.get("presence", False),
        "fall": v.get("fall", False),
        "motion": v.get("motion", False),
        "n_persons": v.get("n_persons", 0),
        "motionEnergy": v.get("motionEnergy", 0.0),
        "presenceScore": v.get("presenceScore", 0.0),
        "rssi": v.get("rssi"),
        "timestamp": int(time.time()*1000),
        "source": "esp32" if live and v.get("breathingBpm") is not None else "simulated",
        "_simulated": not live,
    }

def _model_info_payload():
    # stub jujur -> badge hijau signal-derived
    return {
        "loaded": False,
        "name": None,
        "mode": "signal-derived",
        "detail": "no .rvf loaded; pose is signal-derived stub (confidence 0)",
    }

# --- REST endpoints ---
@app.get("/health")
async def health():
    return JSONResponse(_health_payload())

# aliases expected by backend-detector / health.service
@app.get("/health/health")
async def health_health():
    return JSONResponse(_health_payload())

@app.get("/health/live")
async def health_live():
    return JSONResponse(_health_payload())

@app.get("/health/ready")
async def health_ready():
    return JSONResponse(_health_payload())

@app.get("/health/metrics")
async def health_metrics():
    s = csi_ingest.get_stats()
    return JSONResponse({**_health_payload(), "stats": s})

@app.get("/health/version")
async def health_version():
    return JSONResponse({"version": "0.8.8-py", "firmware": "0.8.8", "mode": "python-shim"})

@app.get("/api/v1/status")
async def api_status():
    live = csi_ingest.is_live()
    source = "esp32" if live else "simulated"
    # ADR-295 source_state: live_verified vs synthetic
    latest = csi_ingest.get_latest()
    stats = csi_ingest.get_stats()
    vitals = csi_ingest.get_vitals()
    try:
        ssid = csi_ingest.get_ssid()
    except Exception:
        ssid = ""
    try:
        target_ip = csi_ingest.get_target_ip()
    except Exception:
        target_ip = "192.168.1.75"
    try:
        target_port = csi_ingest.get_target_port()
    except Exception:
        target_port = 5005
    ts = latest.get("ts") or vitals.get("ts") or int(time.time() * 1000)
    return JSONResponse({
        "source": source,
        "source_state": "live_verified" if live else "synthetic",
        "status": "ok",
        "uptimeSec": int(time.time() - START_TIME),
        "pps": latest.get("pps", 0),
        "packets": stats.get("count", 0),
        "udpListening": True if ENABLE_UDP else False,
        "udpHost": UDP_HOST,
        "udpPort": UDP_PORT,
        "lastFrom": stats.get("lastFrom"),
        "ssid": ssid,
        "targetIp": target_ip,
        "targetPort": target_port,
        "rssi": latest.get("rssi", -75.0),
        "variance": latest.get("variance", 0.0),
        "motionBand": latest.get("motionBand", 0.0),
        "breathingBand": latest.get("breathingBand", 0.0),
        "presence": latest.get("presence", False),
        "confidence": latest.get("confidence", 0.0),
        "timestamp": ts,
        "breathingBpm": vitals.get("breathingBpm"),
        "heartBpm": vitals.get("heartBpm"),
    })

@app.get("/api/v1/info")
async def api_info():
    latest = csi_ingest.get_latest()
    stats = csi_ingest.get_stats()
    vitals = csi_ingest.get_vitals()
    try:
        ssid = csi_ingest.get_ssid()
    except Exception:
        ssid = ""
    try:
        target_ip = csi_ingest.get_target_ip()
    except Exception:
        target_ip = "192.168.1.75"
    try:
        target_port = csi_ingest.get_target_port()
    except Exception:
        target_port = 5005
    ts = latest.get("ts") or vitals.get("ts") or int(time.time() * 1000)
    return JSONResponse({
        "service": "wifisense-python-shim",
        "version": "0.8.8-py",
        "environment": "development",
        "apiVersion": "v1",
        "ui": "web/ui vendor",
        "ssid": ssid,
        "targetIp": target_ip,
        "targetPort": target_port,
        "udpHost": UDP_HOST,
        "udpPort": UDP_PORT,
        "udpListening": True if ENABLE_UDP else False,
        "lastFrom": stats.get("lastFrom"),
        "rssi": latest.get("rssi", -75.0),
        "variance": latest.get("variance", 0.0),
        "motionBand": latest.get("motionBand", 0.0),
        "breathingBand": latest.get("breathingBand", 0.0),
        "presence": latest.get("presence", False),
        "confidence": latest.get("confidence", 0.0),
        "timestamp": ts,
        "breathingBpm": vitals.get("breathingBpm"),
        "heartBpm": vitals.get("heartBpm"),
        "source": "esp32" if csi_ingest.is_live() else "simulated",
        "pps": latest.get("pps", 0),
    })

@app.get("/api/v1/metrics")
async def api_metrics():
    return JSONResponse(csi_ingest.get_stats())

@app.get("/api/v1/sensing/latest")
async def sensing_latest():
    return JSONResponse(_sensing_latest_payload())

# alias without version prefix (some older UI fetches)
@app.get("/api/sensing/latest")
async def sensing_latest_alias():
    return JSONResponse(_sensing_latest_payload())

@app.get("/api/v1/vital-signs")
async def vital_signs():
    return JSONResponse(_vitals_payload())

@app.get("/api/v1/vitals")
async def vitals_alias():
    return JSONResponse(_vitals_payload())

@app.get("/api/v1/vital_signs")
async def vital_signs_snake():
    return JSONResponse(_vitals_payload())

@app.get("/api/v1/model/info")
async def model_info():
    return JSONResponse(_model_info_payload())

# --- pose REST stubs (UI polls these; WS is primary) ---
@app.get("/api/v1/pose/current")
async def pose_current():
    return JSONResponse(csi_ingest.build_pose_stub())

@app.get("/api/v1/pose/stats")
async def pose_stats(hours: int = 1):
    # stub stats; hours param from ?hours=1
    return JSONResponse({"hours": hours, "stats": {"frames": csi_ingest.get_stats().get("count", 0)}, "pose": csi_ingest.build_pose_stub(), "source": "esp32" if csi_ingest.is_live() else "simulated"})

@app.get("/api/v1/pose/history")
async def pose_history(limit: int = 50):
    return JSONResponse({"history": [csi_ingest.build_pose_stub()], "limit": limit})

# aliases without /v1 for older UI builds
@app.get("/api/pose/current")
async def pose_current_alias():
    return JSONResponse(csi_ingest.build_pose_stub())

@app.get("/api/pose/stats")
async def pose_stats_alias(hours: int = 1):
    return JSONResponse({"hours": hours, "stats": {"frames": csi_ingest.get_stats().get("count", 0)}, "pose": csi_ingest.build_pose_stub()})

@app.get("/api/v1/pose/zones/summary")
async def pose_zones_summary():
    s = csi_ingest.build_pose_stub()
    return JSONResponse({"zones": {"default": {"count": 1, "presence": s["payload"]["classification"]["presence"]}}, "summary": s, "source": "esp32" if csi_ingest.is_live() else "simulated"})

@app.get("/api/v1/pose/zones")
async def pose_zones():
    s = csi_ingest.build_pose_stub()
    return JSONResponse({"zones": ["default"], "counts": {"default": 1}, "pose": s})

@app.get("/api/pose/zones/summary")
async def pose_zones_summary_alias():
    s = csi_ingest.build_pose_stub()
    return JSONResponse({"zones": {"default": {"count": 1, "presence": s["payload"]["classification"]["presence"]}}, "summary": s})

# additional model endpoints for ModelPanel (stubs returning empty so UI doesn't error)
@app.get("/api/v1/models")
async def list_models():
    return JSONResponse({"models": []})

@app.get("/api/v1/models/active")
async def active_model():
    return JSONResponse(None)

@app.get("/api/v1/models/lora/profiles")
async def lora_profiles():
    return JSONResponse({"profiles": []})

# training / recording stubs (TrainingPanel polls these)
@app.get("/api/v1/recording/list")
async def recording_list():
    return JSONResponse({"recordings": [], "total": 0})

@app.get("/api/v1/recording/status")
async def recording_status():
    return JSONResponse({"recording": False, "count": 0})

@app.get("/api/v1/train/status")
async def train_status():
    return JSONResponse({"status": "idle", "training": False, "progress": 0, "epoch": 0})

@app.get("/api/v1/training/status")
async def training_status_alias():
    return JSONResponse({"status": "idle", "training": False, "progress": 0})

# aliases without /v1
@app.get("/api/recording/list")
async def recording_list_alias():
    return JSONResponse({"recordings": []})

@app.get("/api/train/status")
async def train_status_alias():
    return JSONResponse({"status": "idle", "training": False})

# oauth stubs (HUD polls this, no auth in shim)
@app.get("/oauth/status")
async def oauth_status():
    return JSONResponse({"authenticated": False, "oauth": False, "status": "ok", "stub": True})

@app.get("/api/oauth/status")
async def api_oauth_status():
    return JSONResponse({"authenticated": False, "status": "ok"})

# ---------------------------------------------------------------------------
# WiFi Settings → WiFi (test koneksi dulu) — BE panel
# ---------------------------------------------------------------------------
def _default_state_dir() -> str:
    # mirror firmware/provision.py + csi_ingest._default_provision_dir()
    try:
        return csi_ingest._default_provision_dir()  # type: ignore
    except Exception:
        pass
    env = os.environ
    if sys.platform == "win32":
        base = env.get("APPDATA") or os.path.expanduser("~")
    else:
        base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "wifi-densepose", "esp32-provision-state")


def _get_local_ip() -> str:
    # UDP 8.8.8.8 trick + gethostbyname fallback (no internet required to succeed)
    ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't actually send traffic; connect just picks outbound iface
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        ip = None
    if not ip or ip.startswith("127."):
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = None
    if not ip or ip.startswith("127."):
        # last resort: enumerate via hostname -I style? fallback to 127.0.0.1
        ip = ip or "127.0.0.1"
    return ip


def _scan_provision_states(state_dir: str) -> List[Dict[str, Any]]:
    """Scan state_dir/*.json → list of {path, data, mtime, portName}"""
    out: List[Dict[str, Any]] = []
    try:
        if not os.path.isdir(state_dir):
            return out
        for name in os.listdir(state_dir):
            if not name.lower().endswith(".json"):
                continue
            fp = os.path.join(state_dir, name)
            try:
                if not os.path.isfile(fp):
                    continue
                mtime = os.path.getmtime(fp)
                with open(fp, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # derive port name from filename sanitization reverse
                stem = os.path.splitext(name)[0]
                # _state_path_for sanitizes "/"->"_" and ":"->"_" ; reverse heuristic
                # Windows COMx stays as-is; Linux /dev/ttyUSB0 → _dev_ttyUSB0
                if stem.startswith("_"):
                    port_name = stem.replace("_", "/")
                    # fix leading // → /
                    if port_name.startswith("//"):
                        port_name = port_name[1:]
                else:
                    port_name = stem
                # also try to get port field inside json if present
                if isinstance(data, dict) and data.get("port"):
                    port_name = str(data.get("port"))
                out.append({"path": fp, "data": data if isinstance(data, dict) else {}, "mtime": mtime, "portName": port_name, "stem": stem})
            except Exception:
                continue
    except Exception:
        pass
    # newest first
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def _get_serial_ports_list() -> List[Dict[str, Any]]:
    """Return [{port, desc, lastUsed, mac}] via pyserial + fallback scan"""
    state_dir = _default_state_dir()
    states = _scan_provision_states(state_dir)
    # map stem -> state for quick lookup, plus identify newest
    stem_to_state = {s["stem"]: s for s in states}
    newest_stem = states[0]["stem"] if states else None
    # try pyserial
    ports: List[Dict[str, Any]] = []
    serial_found = False
    try:
        from serial.tools import list_ports  # type: ignore

        for p in list_ports.comports():
            serial_found = True
            device = getattr(p, "device", str(p))
            desc = getattr(p, "description", "") or getattr(p, "hwid", "") or "USB JTAG/serial debug unit"
            # sanitize device to stem for lookup
            safe = device.replace("/", "_").replace(":", "_").replace("\\", "_")
            st = stem_to_state.get(safe)
            mac = None
            last_used = False
            if st is not None:
                d = st["data"]
                mac = d.get("filter_mac") or d.get("filterMac") or d.get("mac") or d.get("mac_address")
                last_used = (safe == newest_stem)
            else:
                # also check if any state's portName equals device
                for s in states:
                    if s["portName"] == device:
                        d = s["data"]
                        mac = d.get("filter_mac") or d.get("filterMac") or d.get("mac")
                        last_used = (s["stem"] == newest_stem)
                        break
            ports.append({"port": device, "desc": desc, "lastUsed": bool(last_used), "mac": mac})
    except Exception as e:
        log.debug("list_ports failed: %s", e)
        serial_found = False

    if serial_found and ports:
        # merge: also append phantom state entries that have no matching real port, so UI still sees last-used phantom
        existing = {p["port"] for p in ports}
        # check if any real port already marked lastUsed
        has_last = any(x["lastUsed"] for x in ports)
        for s in states:
            if s["portName"] not in existing:
                d = s["data"]
                mac = d.get("filter_mac") or d.get("filterMac") or d.get("mac") or d.get("mac_address")
                desc = d.get("desc") or d.get("description") or "USB JTAG/serial debug unit"
                ports.append({"port": s["portName"], "desc": desc, "lastUsed": bool(s["stem"] == newest_stem and not has_last), "mac": mac})
        # if still no lastUsed (newest is phantom now appended, but has_last False case already handled)
        # if newest was real but already marked, nothing to do; if newest phantom and has_last was True, phantom should not be true
        # ensure exactly one lastUsed if states exist
        if states and not any(x["lastUsed"] for x in ports):
            # mark newest among all ports if possible
            newest_name = states[0]["portName"]
            for x in ports:
                if x["port"] == newest_name:
                    x["lastUsed"] = True
                    break
            # fallback: first entry
            if not any(x["lastUsed"] for x in ports):
                ports[0]["lastUsed"] = True
        return ports

    # fallback: synthesize from provision state json files
    if states:
        for s in states:
            d = s["data"]
            mac = d.get("filter_mac") or d.get("filterMac") or d.get("mac") or d.get("mac_address")
            # try to get desc from data or fallback
            desc = d.get("desc") or d.get("description") or "USB JTAG/serial debug unit"
            ports.append({"port": s["portName"], "desc": desc, "lastUsed": bool(s["stem"] == newest_stem), "mac": mac})
        return ports

    # ultimate fallback: if no pyserial and no state files, return empty list (UI handles empty)
    return ports


def _detect_auto_port(preferred: Optional[str] = None) -> Optional[str]:
    if preferred:
        return preferred
    lst = _get_serial_ports_list()
    if not lst:
        return None
    # prefer lastUsed true
    for e in lst:
        if e.get("lastUsed"):
            return str(e.get("port"))
    return str(lst[0].get("port"))


def _run_provision(extra_args: List[str], timeout: int = 45) -> Dict[str, Any]:
    """Run firmware/provision.py with given extra_args; return {ok, stdout, stderr, code}"""
    provision_py = ROOT / "firmware" / "provision.py"
    if not provision_py.is_file():
        # fallback cwd
        alt = Path.cwd() / "firmware" / "provision.py"
        if alt.is_file():
            provision_py = alt
        else:
            return {"ok": False, "stderr": f"provision.py not found at {provision_py}", "code": -1, "stdout": ""}
    cmd = [sys.executable, str(provision_py)] + extra_args
    log.info("provision cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ok = proc.returncode == 0
        return {"ok": ok, "stdout": proc.stdout or "", "stderr": proc.stderr or "", "code": proc.returncode, "cmd": cmd}
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "stdout": (e.stdout.decode() if isinstance(e.stdout, bytes) else str(e.stdout or "")), "stderr": f"timeout {timeout}s", "code": -1, "cmd": cmd}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1, "cmd": cmd}


def _esptool_reset(port: str) -> Dict[str, Any]:
    """RESET via esptool run (best-effort); return {ok, stdout, stderr}"""
    # common: python -m esptool --port COMx run
    # also try with --chip auto
    cmds = [
        [sys.executable, "-m", "esptool", "--port", port, "run"],
        [sys.executable, "-m", "esptool", "--chip", "auto", "--port", port, "run"],
    ]
    last: Dict[str, Any] = {"ok": False, "stderr": "no attempt", "stdout": ""}
    for cmd in cmds:
        try:
            log.info("esptool reset: %s", " ".join(cmd))
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            last = {"ok": proc.returncode == 0, "stdout": proc.stdout or "", "stderr": proc.stderr or "", "code": proc.returncode, "cmd": cmd}
            if proc.returncode == 0:
                return last
        except Exception as e:
            last = {"ok": False, "stderr": str(e), "stdout": "", "cmd": cmd}
    return last


def _sync_nvs_csv(fields: Dict[str, Any]) -> None:
    """Best-effort: update nvs_config.csv di ROOT agar health/targetIp sinkron setelah provision.
    fields: e.g. {"target_ip": "192.168.1.75", "ssid": "..."} di-csi_cfg namespace.
    """
    try:
        candidates = [ROOT / "nvs_config.csv", Path.cwd() / "nvs_config.csv"]
        # deduplicate
        seen = set()
        paths: List[Path] = []
        for p in candidates:
            rp = p.resolve()
            if str(rp) not in seen:
                seen.add(str(rp))
                paths.append(p)
        updated = False
        for p in paths:
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8")
                lines = text.splitlines()
                # parse header
                if not lines or "key,type" not in lines[0]:
                    continue
                import csv as _csv
                import io as _io
                buf = _io.StringIO()
                writer = _csv.writer(buf, lineterminator="\n")
                reader = _csv.DictReader(_io.StringIO(text))
                rows = list(reader)
                # map key -> row
                row_by_key = {r.get("key"): r for r in rows if r.get("key")}
                for k, v in fields.items():
                    if v is None or str(v) == "":
                        continue
                    csv_key = k  # already target_ip etc
                    if csv_key in row_by_key:
                        row_by_key[csv_key]["value"] = str(v)
                    else:
                        # add new row
                        new_row = {"key": csv_key, "type": "data", "encoding": "string" if csv_key in ("ssid","password","target_ip") else "u16", "value": str(v)}
                        if csv_key == "target_port":
                            new_row["encoding"] = "u16"
                        rows.append(new_row)
                    updated = True
                if updated:
                    # rewrite
                    buf2 = _io.StringIO()
                    w2 = _csv.writer(buf2, lineterminator="\n")
                    w2.writerow(["key","type","encoding","value"])
                    # preserve namespace row first if exists
                    ns_rows = [r for r in rows if r.get("key") == "csi_cfg"]
                    other = [r for r in rows if r.get("key") != "csi_cfg"]
                    for r in ns_rows + other:
                        w2.writerow([r.get("key",""), r.get("type",""), r.get("encoding",""), r.get("value","")])
                    p.write_text(buf2.getvalue(), encoding="utf-8")
                    log.info("nvs_config.csv synced %s fields=%s", p, fields)
                    break  # only update first found
            except Exception as e:
                log.debug("sync nvs csv %s failed: %s", p, e)
                continue
    except Exception as e:
        log.debug("sync nvs csv outer failed: %s", e)


def _serial_stop():
    try:
        csi_ingest.stop_serial_reader()
    except Exception as e:
        log.debug("serial stop failed: %s", e)


def _serial_start():
    try:
        if ENABLE_SERIAL:
            csi_ingest.start_serial_reader(SERIAL_PORT, SERIAL_BAUD)
    except Exception as e:
        log.debug("serial start failed: %s", e)


class ConfigTestRequest(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = None
    channel: Optional[int] = None
    hopChannels: Optional[Union[str, List[int]]] = None
    hop_channels: Optional[Union[str, List[int]]] = None
    port: Optional[str] = None
    targetIp: Optional[str] = None
    target_ip: Optional[str] = None
    # allow extra
    class Config:
        extra = "allow"
        populate_by_name = True


class ConfigApplyRequest(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = None
    channel: Optional[int] = None
    hopChannels: Optional[Union[str, List[int]]] = None
    hop_channels: Optional[Union[str, List[int]]] = None
    port: Optional[str] = None
    targetIp: Optional[str] = None
    target_ip: Optional[str] = None
    targetPort: Optional[int] = None
    target_port: Optional[int] = None

    class Config:
        extra = "allow"
        populate_by_name = True


class ReTargetRequest(BaseModel):
    port: Optional[str] = None

    class Config:
        extra = "allow"


def _build_provision_args_from_body(body: Dict[str, Any], include_dry_run: bool = False) -> List[str]:
    args: List[str] = []
    # port is required for provision
    port = body.get("port") or body.get("Port")
    if port:
        args += ["--port", str(port)]
    ssid = body.get("ssid")
    if ssid is not None:
        args += ["--ssid", str(ssid)]
    pwd = body.get("password")
    if pwd is not None:
        args += ["--password", str(pwd)]
    # target ip variants
    tip = body.get("targetIp") or body.get("target_ip") or body.get("target-ip")
    if tip is not None:
        args += ["--target-ip", str(tip)]
    tport = body.get("targetPort") or body.get("target_port")
    if tport is not None:
        args += ["--target-port", str(tport)]
    ch = body.get("channel")
    if ch is not None and str(ch).strip() != "":
        args += ["--channel", str(ch)]
    # hop channels: handle list or string
    hop = body.get("hopChannels")
    if hop is None:
        hop = body.get("hop_channels")
    if hop is None:
        hop = body.get("hop_channels") or body.get("hopChannels")
    # also support legacy hopChannels as comma string
    if hop is not None:
        if isinstance(hop, (list, tuple)):
            hop_str = ",".join(str(int(x)) for x in hop if str(x).strip() != "")
        else:
            hop_str = str(hop).strip()
        if hop_str:
            args += ["--hop-channels", hop_str]
    if include_dry_run:
        args += ["--dry-run"]
    return args


@app.get("/api/v1/serial/ports")
async def serial_ports():
    lst = _get_serial_ports_list()
    return JSONResponse(lst)


@app.get("/api/v1/network/local-ip")
async def network_local_ip():
    local_ip = _get_local_ip()
    try:
        target_ip = csi_ingest.get_target_ip()
    except Exception:
        target_ip = "192.168.1.75"
    mismatch = (local_ip != target_ip)
    return JSONResponse({"localIp": local_ip, "targetIp": target_ip, "mismatch": bool(mismatch), "udpHost": UDP_HOST, "udpPort": UDP_PORT})


@app.post("/api/v1/config/test")
async def config_test(body: ConfigTestRequest):
    data = body.model_dump(by_alias=False) if hasattr(body, "model_dump") else body.dict()  # type: ignore
    # merge extra fields that pydantic may have dropped? Config extra=allow keeps them in model_extra
    if hasattr(body, "model_extra") and body.model_extra:
        for k, v in body.model_extra.items():
            if k not in data:
                data[k] = v
    port = data.get("port") or _detect_auto_port(None)
    if not port:
        return JSONResponse({"ok": False, "reason": "port diperlukan (tidak ada COM terdeteksi)"}, status_code=400)
    data["port"] = port
    # normalize hopChannels alias
    if data.get("hop_channels") and not data.get("hopChannels"):
        data["hopChannels"] = data.get("hop_channels")
    # mode handling (channel vs wifi)
    mode_raw = str(data.get("mode") or "").strip().lower()
    if mode_raw in ("wifi", "channel"):
        mode = mode_raw
    else:
        ssid_val = str(data.get("ssid") or "").strip()
        has_ch = data.get("channel") is not None and str(data.get("channel")).strip() != ""
        hop = data.get("hopChannels") or data.get("hop_channels")
        has_hop = hop is not None and str(hop).strip() != ""
        if not ssid_val and (has_ch or has_hop):
            mode = "channel"
        else:
            mode = "wifi"
    try:
        csi_ingest.set_ingest_mode(mode)
    except Exception:
        pass
    # build provision dry-run args
    prov_args = _build_provision_args_from_body(data, include_dry_run=True)
    # ensure --port present
    if "--port" not in prov_args:
        prov_args = ["--port", str(port)] + prov_args
    # COM exclusivity: stop serial before provision
    _serial_stop()
    result = _run_provision(prov_args, timeout=30)
    # restart serial (best-effort)
    try:
        _serial_start()
    except Exception:
        pass
    if not result.get("ok"):
        reason = (result.get("stderr") or result.get("stdout") or "provision dry-run gagal")[:800]
        return JSONResponse({"ok": False, "reason": reason, "detail": result})
    # poll /health/health 8s pps>0
    deadline = time.time() + 8.0
    last_pps = 0
    last_from = None
    ok_live = False
    while time.time() < deadline:
        try:
            s = csi_ingest.get_stats()
            pps = int(s.get("pps", 0) or 0)
            last_from = s.get("lastFrom")
            last_pps = pps
            if pps > 0 and last_from:
                ok_live = True
                break
        except Exception:
            pass
        await asyncio.sleep(0.5)
    if ok_live:
        return JSONResponse({"ok": True, "pps": last_pps, "lastFrom": last_from, "provision": result})
    # provision ok but no live packets – masih return ok:false dengan reason informatif, tapi provision sukses
    return JSONResponse({"ok": False, "reason": "dry-run sukses tapi tidak ada paket CSI dalam 8s (pps=0). Pastikan ESP sudah reset & UDP 5005 terbuka", "pps": last_pps, "lastFrom": last_from, "provision": result})


@app.post("/api/v1/config/apply")
@app.post("/api/v1/config/provision")
@app.post("/api/v1/config/wifi")
@app.post("/api/v1/serial/provision")
async def config_apply(body: ConfigApplyRequest):
    data = body.model_dump(by_alias=False) if hasattr(body, "model_dump") else body.dict()  # type: ignore
    if hasattr(body, "model_extra") and body.model_extra:
        for k, v in body.model_extra.items():
            if k not in data:
                data[k] = v
    port = data.get("port") or _detect_auto_port(None)
    if not port:
        return JSONResponse({"ok": False, "reason": "port diperlukan"}, status_code=400)
    data["port"] = port
    if data.get("hop_channels") and not data.get("hopChannels"):
        data["hopChannels"] = data.get("hop_channels")
    # mode handling
    mode_raw = str(data.get("mode") or "").strip().lower()
    if mode_raw in ("wifi", "channel"):
        mode = mode_raw
    else:
        ssid_val = str(data.get("ssid") or "").strip()
        has_ch = data.get("channel") is not None and str(data.get("channel")).strip() != ""
        hop = data.get("hopChannels") or data.get("hop_channels")
        has_hop = hop is not None and str(hop).strip() != ""
        if not ssid_val and (has_ch or has_hop):
            mode = "channel"
        else:
            mode = "wifi"
    try:
        csi_ingest.set_ingest_mode(mode)
    except Exception:
        pass
    prov_args = _build_provision_args_from_body(data, include_dry_run=False)
    if "--port" not in prov_args:
        prov_args = ["--port", str(port)] + prov_args
    # if only port without any config value, provision would error; try to add --force-partial if needed
    # but apply should have ssid etc; if not, add force-partial to avoid trio error
    has_cfg = any(k in prov_args for k in ("--ssid", "--password", "--target-ip", "--channel", "--hop-channels"))
    if not has_cfg:
        prov_args += ["--force-partial"]
    # COM exclusivity
    _serial_stop()
    result = _run_provision(prov_args, timeout=45)
    if not result.get("ok"):
        reason = (result.get("stderr") or result.get("stdout") or "provision gagal")[:800]
        try:
            _serial_start()
        except Exception:
            pass
        return JSONResponse({"ok": False, "reason": reason, "detail": result})
    # RESET via esptool run (best-effort) — keep serial closed during reset
    reset_res = _esptool_reset(str(port))
    try:
        _serial_start()
    except Exception:
        pass
    # sync nvs_config.csv agar health/targetIp langsung sinkron (untuk TestClient & UI badge)
    try:
        sync_fields: Dict[str, Any] = {}
        if data.get("ssid"):
            sync_fields["ssid"] = data.get("ssid")
        tip = data.get("targetIp") or data.get("target_ip")
        if tip:
            sync_fields["target_ip"] = tip
        if sync_fields:
            _sync_nvs_csv(sync_fields)
    except Exception:
        pass
    # after apply, health ssid update – fetch via csi_ingest
    try:
        ssid_now = csi_ingest.get_ssid()
    except Exception:
        ssid_now = data.get("ssid")
    try:
        target_now = csi_ingest.get_target_ip()
    except Exception:
        target_now = data.get("targetIp") or data.get("target_ip")
    return JSONResponse({"ok": True, "port": port, "ssid": ssid_now, "targetIp": target_now, "provision": result, "reset": reset_res, "health": _health_payload()})


@app.post("/api/v1/config/re-target")
async def config_retarget(body: Optional[ReTargetRequest] = None):
    # body may be None or empty
    preferred_port: Optional[str] = None
    if body is not None:
        try:
            d = body.model_dump() if hasattr(body, "model_dump") else body.dict()  # type: ignore
        except Exception:
            d = {}
        preferred_port = d.get("port")
        if hasattr(body, "model_extra") and body.model_extra:
            preferred_port = preferred_port or body.model_extra.get("port")
    local_ip = _get_local_ip()
    try:
        target_ip = csi_ingest.get_target_ip()
    except Exception:
        target_ip = "192.168.1.75"
    mismatch = (local_ip != target_ip)
    if not mismatch:
        return JSONResponse({"ok": True, "alreadyAligned": True, "localIp": local_ip, "targetIp": target_ip, "mismatch": False, "message": "sudah sinkron"})
    # need to provision --target-ip <localIp> --port <auto>
    port = _detect_auto_port(preferred_port)
    if not port:
        return JSONResponse({"ok": False, "reason": "mismatch terdeteksi tapi tidak ada COM port (colok ESP & coba lagi)", "localIp": local_ip, "targetIp": target_ip, "mismatch": True}, status_code=400)
    prov_args = ["--port", str(port), "--target-ip", str(local_ip), "--force-partial"]
    _serial_stop()
    result = _run_provision(prov_args, timeout=30)
    if not result.get("ok"):
        reason = (result.get("stderr") or result.get("stdout") or "provision re-target gagal")[:800]
        try:
            _serial_start()
        except Exception:
            pass
        return JSONResponse({"ok": False, "reason": reason, "localIp": local_ip, "targetIp": target_ip, "mismatch": True, "detail": result, "port": port})
    reset_res = _esptool_reset(str(port))
    try:
        _serial_start()
    except Exception:
        pass
    # sync csv agar mismatch badge hilang
    try:
        _sync_nvs_csv({"target_ip": local_ip})
    except Exception:
        pass
    # after provision, targetIp should now be localIp (state file updated)
    try:
        new_target = csi_ingest.get_target_ip()
    except Exception:
        new_target = local_ip
    return JSONResponse({"ok": True, "localIp": local_ip, "previousTargetIp": target_ip, "targetIp": new_target, "mismatch": (local_ip != new_target), "port": port, "provision": result, "reset": reset_res})


# --- server logs buffer endpoint ---
@app.get("/api/v1/logs")
@app.get("/logs")
@app.get("/api/logs")
async def get_logs(limit: int = 100, level: Optional[str] = None):
    try:
        lim = int(limit)
    except Exception:
        lim = 100
    lim = max(1, min(300, lim))
    logs = list(LOG_BUFFER)
    if level:
        lvl = str(level).strip().upper()
        if lvl:
            logs = [x for x in logs if str(x.get("level", "")).upper() == lvl]
    sliced = logs[-lim:] if len(logs) > lim else logs
    return JSONResponse({"logs": sliced, "total": len(LOG_BUFFER)})


# generic fallback for any other /api/v1/* that UI may poll — avoid 404 spam
@app.get("/api/v1/{path:path}")
async def api_v1_fallback(path: str):
    return JSONResponse({"status": "ok", "stub": True, "path": f"/api/v1/{path}", "note": "python-shim stub (hemat, tanpa training)"})


@app.post("/api/v1/{path:path}")
async def api_v1_fallback_post(path: str):
    return JSONResponse({"detail": "Not Found"}, status_code=404)

@app.get("/oauth/{path:path}")
async def oauth_fallback(path: str):
    return JSONResponse({"status": "ok", "stub": True, "path": f"/oauth/{path}"})

@app.get("/csi")
async def csi_debug():
    latest = csi_ingest.get_latest()
    stats = csi_ingest.get_stats()
    if latest.get("ts", 0) == 0:
        return JSONResponse({"error": "no data yet", "stats": stats})
    return JSONResponse(csi_ingest.build_sensing_update_sync())

@app.get("/stats")
async def stats():
    s = csi_ingest.get_stats()
    return JSONResponse(s)

@app.get("/")
async def root():
    # serve index.html if UI exists, else json
    idx = UI_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"status": "ok", "service": "wifisense-python-shim", "ui": "missing web/ui", "health": _health_payload()})

# --- WS endpoints ---
@app.websocket("/ws/sensing")
async def ws_sensing(ws: WebSocket):
    await ws.accept()
    async with _clients_lock:
        sensing_clients.add(ws)
    # push last known immediately
    try:
        init_msg = csi_ingest.build_sensing_update_sync()
        await ws.send_json(init_msg)
    except:
        pass
    # also handle incoming pings (browser may send)
    try:
        while True:
            # wait for client messages or broadcast - we just keep connection alive
            # Use receive_text with timeout via asyncio wait
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                # respond to ping
                if data:
                    try:
                        import json
                        j = json.loads(data)
                        if j.get("type") == "ping":
                            await ws.send_json({"type": "pong", "timestamp": int(time.time()*1000)})
                    except:
                        pass
            except asyncio.TimeoutError:
                # send ping to keep alive
                try:
                    await ws.send_json({"type": "ping", "timestamp": int(time.time()*1000)})
                except:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("ws/sensing error: %s", e)
    finally:
        async with _clients_lock:
            sensing_clients.discard(ws)

@app.websocket("/api/v1/stream/pose")
async def ws_pose(ws: WebSocket):
    # tolerate query params like ?token= etc (FastAPI strips them)
    await ws.accept()
    async with _clients_lock:
        pose_clients.add(ws)
    # push initial pose stub
    try:
        await ws.send_json(csi_ingest.build_pose_stub())
        await ws.send_json({"type": "connection_established", "payload": {"status": "connected", "pose_source": "signal-derived"}})
    except:
        pass
    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                # handle ping / update_config etc
                if data:
                    import json
                    try:
                        j = json.loads(data)
                        if j.get("type") == "ping":
                            await ws.send_json({"type": "pong", "timestamp": int(time.time()*1000)})
                        elif j.get("type") == "get_status":
                            await ws.send_json({"type": "status", "pose_source": "signal-derived", "mode": "signal-derived"})
                    except:
                        pass
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({"type": "ping", "timestamp": int(time.time()*1000)})
                except:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.debug("ws/pose error: %s", e)
    finally:
        async with _clients_lock:
            pose_clients.discard(ws)

# optional alias WS for events (frontend may try)
@app.websocket("/api/v1/stream/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    try:
        await ws.send_json({"type": "connection_established", "payload": {"status": "connected"}})
        while True:
            await asyncio.sleep(30)
            try:
                await ws.send_json({"type": "ping", "timestamp": int(time.time()*1000)})
            except:
                break
    except WebSocketDisconnect:
        pass

@app.websocket("/ws/pose")
async def ws_pose_alias(ws: WebSocket):
    # some docs use /ws/pose
    await ws_pose(ws)

# --- static mounts (after API routes, so /health etc matched first) ---
# Mount /ui explicitly
if UI_DIR.exists():
    # mount /ui
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
    # also serve any other static file at root via fallback route
    # FastAPI StaticFiles at "/" must be last; we add a catch-all FileResponse via mount
    # We mount root static as well but after API - it will serve index.html for "/"
    # Note: mounting at "/" after other routes still works; API routes take precedence
    try:
        app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="root-ui")
    except Exception as e:
        log.warning("root static mount failed: %s", e)
else:
    log.warning("UI_DIR not found at %s - static serving disabled", UI_DIR)

# --- startup ---
@app.on_event("startup")
async def on_startup():
    log.info("Python shim starting - UI_DIR=%s exists=%s", UI_DIR, UI_DIR.exists())
    log.info("CORS *, health source=%s", "esp32" if csi_ingest.is_live() else "simulated")
    if ENABLE_UDP:
        try:
            transport, proto = await csi_ingest.start_udp_listener(UDP_HOST, UDP_PORT)
            # keep reference to prevent GC
            app.state.udp_transport = transport
            app.state.udp_protocol = proto
            log.info("UDP listening %s:%d", UDP_HOST, UDP_PORT)
        except OSError as e:
            # port already bound (e.g. Node bridge still running)
            log.error("UDP bind %s:%d failed: %s - STOP Node bridge (node server/index.js) or set ENABLE_UDP=0", UDP_HOST, UDP_PORT, e)
            log.error("Hint: `node server/index.js` and Python shim cannot both bind 5005. Stop Node: Ctrl+C or set env ENABLE_NODE_UDP=0")
        except Exception as e:
            log.error("UDP startup failed: %s", e)
    else:
        log.info("UDP disabled via ENABLE_UDP=0 - running in simulated mode only")

    if ENABLE_SERIAL:
        try:
            # sync call is OK (threaded reader, don't block event loop)
            reader = csi_ingest.start_serial_reader(SERIAL_PORT, SERIAL_BAUD)
            app.state.serial_reader = reader
            log.info("[SERIAL] startup reader %s @%d -> %s", SERIAL_PORT, SERIAL_BAUD, "ok" if reader else "disabled (no pyserial)")
        except Exception as e:
            log.error("[SERIAL] startup failed: %s", e)
            app.state.serial_reader = None
    else:
        log.info("Serial sniff disabled (ENABLE_SERIAL=0)")

    # Secondary WS proxy on 3001 for sensing.service mapping (3000->3001)
    if ENABLE_SECONDARY:
        # Only spawn if main port looks like 3000 (heuristic: env PORT or default 3000)
        main_port = int(os.getenv("HTTP_PORT", os.getenv("PORT", "3000")))
        # Also detect uvicorn CLI port via env? Fallback: if secondary port != main, always spawn
        if main_port == 3000:
            asyncio.create_task(_start_secondary_proxy())

_secondary_server = None

async def _start_secondary_proxy():
    """Start secondary WS proxy on 0.0.0.0:3001 that mirrors /ws/sensing
    Uses `websockets` library if available, otherwise skip with warning.
    This handles the vendor sensing.service.js that maps 3000->3001.
    """
    global _secondary_server
    try:
        import websockets
        from websockets.asyncio.server import serve
    except Exception as e:
        log.warning("websockets not installed - secondary proxy 3001 disabled (%s). UI may need to use window.location.host WS directly.", e)
        return

    async def handler(ws):
        # websockets 12+ uses (websocket) signature, path via ws.request.path if needed
        # Accept only /ws/sensing, else echo
        path = ""
        try:
            # try to get path from request
            req = getattr(ws, "request", None)
            if req is not None:
                path = getattr(req, "path", "") or getattr(req, "target", "")
        except:
            pass
        # Log connection
        log.info("[secondary 3001] WS connected %s path=%s", ws.remote_address, path)
        # Treat any connection as sensing WS
        # Send init
        try:
            init = csi_ingest.build_sensing_update_sync()
            await ws.send(__import__("json").dumps(init))
        except:
            pass
        # register a temporary broadcast cb for this ws
        async def forward(data):
            try:
                await ws.send(__import__("json").dumps(data))
            except:
                pass
        csi_ingest.register_broadcast(forward)
        try:
            async for msg in ws:
                # handle ping from client
                try:
                    import json as _j
                    j = _j.loads(msg)
                    if j.get("type") == "ping":
                        await ws.send(_j.dumps({"type":"pong","timestamp":int(time.time()*1000)}))
                except:
                    pass
        except Exception as e:
            log.debug("[secondary] handler error: %s", e)
        finally:
            # remove forward cb (simple: not removing from list to avoid complexity - it'll just fail silently next broadcast)
            log.info("[secondary 3001] WS closed %s", ws.remote_address)

    try:
        _secondary_server = await serve(handler, "0.0.0.0", SECONDARY_PORT, ping_interval=20, ping_timeout=10)
        log.info("[secondary] WS proxy listening ws://0.0.0.0:%d/ws/sensing (for vendor sensing.service 3000->3001 mapping)", SECONDARY_PORT)
    except OSError as e:
        log.warning("[secondary] bind 0.0.0.0:%d failed: %s - perhaps already bound", SECONDARY_PORT, e)
    except Exception as e:
        log.warning("[secondary] failed to start: %s", e)

@app.on_event("shutdown")
async def on_shutdown():
    # stop serial reader
    try:
        csi_ingest.stop_serial_reader()
    except Exception:
        pass
    # close UDP
    tr = getattr(app.state, "udp_transport", None)
    if tr:
        try:
            tr.close()
        except:
            pass
    global _secondary_server
    if _secondary_server:
        try:
            _secondary_server.close()
            await _secondary_server.wait_closed()
        except:
            pass
