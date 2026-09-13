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
import logging
import os
import time
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import csi_ingest

log = logging.getLogger("server_py")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

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
    source = "esp32" if live else "simulated"
    # provision network info (ssid/targetIp from NVS or COM4.json fallback)
    try:
        ssid = csi_ingest.get_ssid()
    except Exception:
        ssid = "FLAMBOYAN'S"
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
        "components": {"api": "healthy", "csi": csi_status},
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
        ssid = "FLAMBOYAN'S"
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
        ssid = "FLAMBOYAN'S"
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

# generic fallback for any other /api/v1/* that UI may poll — avoid 404 spam
@app.get("/api/v1/{path:path}")
async def api_v1_fallback(path: str):
    return JSONResponse({"status": "ok", "stub": True, "path": f"/api/v1/{path}", "note": "python-shim stub (hemat, tanpa training)"})

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
