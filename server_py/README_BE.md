# server_py — Python shim LIVE-ESP32 tanpa Rust

Shim FastAPI yang meniru 6 kontrak Rust `sensing-server` agar UI 100% RuView (`web/ui/`) banner hijau **LIVE — ESP32 HARDWARE** tanpa toolchain Rust.

## Kontrak yang ditiru
| # | Endpoint | Deskripsi | Payload |
|---|----------|-----------|---------|
|1| `GET /health` (+ `/health/health`, `/health/live`, `/health/ready`) | health | `{status:"ok", source:"esp32"\|"simulated", uptimeSec, pps, packets}` |
|2| `GET /api/v1/sensing/latest` | latest CSI heuristic | `{rssi, variance, motionBand, breathingBand, presence, confidence, ts, _simulated:false saat LIVE, pps, source}` |
|3| `GET /api/v1/vital-signs` (+ `/api/v1/vitals`) | vitals stub jujur | `{breathingBpm:null|number, heartBpm:null|number, note:"heuristic-only"}` |
|4| `GET /api/v1/model/info` | model stub | `{loaded:false, name:null, mode:"signal-derived"}` — UI badge hijau |
|5| `WS /ws/sensing` | streaming sensing_update | `type:"sensing_update", source:"esp32", _simulated:false, features, classification, signal_field(20x20)` |
|6| `WS /api/v1/stream/pose` | streaming pose | `type:"pose_data", pose_source:"signal-derived", persons:[{confidence:0}]` |

Tambahan alias untuk kompatibilitas vendor UI: `GET /api/v1/status` (`source` + `source_state: live_verified/synthetic`), `GET /api/v1/info`, `GET /api/v1/metrics`, `GET /csi`, `GET /stats`, `WS /api/v1/stream/events`.

Static: `web/ui` di-mount di `/ui` **dan** `/` (index.html). CORS `*`. Tidak ada hardcode `localhost`; UI pakai `window.location.origin` / `window.location.host` → shim compatible dari Docker/LAN.

## Cara run
```powershell
# 1. Install deps (sekali)
pip install -r requirements.txt
# requirements sudah termasuk: fastapi, uvicorn[standard], websockets, numpy, scipy, etc.

# 2. Matikan Node bridge dulu (jangan dobel-bind UDP 5005)
# Node bridge lama dobel-bind 5005 akan gagal kalau Python juga bind. Pilih SATU:
# Opsi A: stop Node sepenuhnya
#   Ctrl+C di terminal `node server/index.js`
# Opsi B: jalankan Node tanpa UDP (hanya HTTP+WS preview)
#   $env:ENABLE_NODE_UDP="0"; npm --prefix server start
#   (server/index.js sudah di-patch guard ENABLE_NODE_UDP)

# 3. Jalankan Python shim di port 3000 (UI + API + WS satu origin)
uvicorn server_py.app:app --host 0.0.0.0 --port 3000 --reload

# Alternatif: HTTP 3000 + UDP 5005 bisa di-override via env
# $env:UDP_PORT="5005"; $env:UDP_HOST="0.0.0.0"; uvicorn server_py.app:app --port 3000 --reload

# 4. Buka UI
# http://localhost:3000/         -> index.html
# http://localhost:3000/ui/      -> sama
# http://localhost:3000/health
```

## Verifikasi manual (curl / ws)

### REST
```powershell
curl http://localhost:3000/health
# {"status":"ok","source":"simulated","uptimeSec":5,"pps":0,"packets":0}  # sebelum ESP kirim
# setelah ESP kirim ADR-018 UDP ke 5005:
# {"status":"ok","source":"esp32","uptimeSec":42,"pps":19,"packets":380}

curl http://localhost:3000/api/v1/sensing/latest | python -m json.tool
# {"rssi":-42.5,"variance":2.31,"motionBand":0.18,"breathingBand":0.07,"presence":true,"confidence":0.82,"ts":172615...,"_simulated":false,"source":"esp32",...}

curl http://localhost:3000/api/v1/vital-signs | python -m json.tool
# {"breathingBpm":14.2,"heartBpm":72.5,"note":"heuristic-only",...}  # null bila belum ada vitals 0xC5110002

curl http://localhost:3000/api/v1/model/info | python -m json.tool
# {"loaded":false,"name":null,"mode":"signal-derived"}

curl http://localhost:3000/api/v1/status | python -m json.tool
# {"source":"esp32","source_state":"live_verified","uptimeSec":42}
```

### WebSocket
```powershell
# PowerShell test WS (butuh `pip install websocket-client` atau pakai wscat)
python -c "
import asyncio, websockets, json
async def t():
    uri='ws://localhost:3000/ws/sensing'
    async with websockets.connect(uri) as ws:
        for i in range(3):
            print(await ws.recv())
        # pose WS
    uri2='ws://localhost:3000/api/v1/stream/pose'
    async with websockets.connect(uri2) as ws:
        print(await ws.recv())
asyncio.run(t())
"

# Secondary proxy (untuk vendor sensing.service.js yang mapping 3000->3001)
# Shim otomatis buka ws://0.0.0.0:3001/ws/sensing bila main port 3000.
# Test:
python -c "import asyncio, websockets; asyncio.run(websockets.connect('ws://localhost:3001/ws/sensing').__aenter__())"  # should succeed
# Disable bila tidak butuh: $env:ENABLE_SECONDARY_PROXY=\"0\"
```

### UDP ingest test (tanpa ESP fisik)
```powershell
# Kirim CSI dummy ADR-018 via Python (magic 0xC5110001, 20B header + 64*2 payload)
python -c "
import socket, struct, os
s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
hdr=struct.pack('<I B B H I I b b 2s', 0xC5110001, 1, 1, 64, 2412, 1, -45, -90, b'\x00\x00')
payload=os.urandom(128)
s.sendto(hdr+payload, ('127.0.0.1', 5005))
print('sent')
"
# lalu cek curl http://localhost:3000/health  -> source esp32, pps>0
```

## UDP detail (`csi_ingest.py`)
- `asyncio.DatagramProtocol` non-blocking di `0.0.0.0:5005`
- Parse 3 magic LE: `0xC5110001` CSI (header 20B + I/Q `n_ant*n_sub*2`), `0xC5110002` vitals 32B, `0xC5110004` WASM
- Vitals 32B: `magic, node, flags(presence/fall/motion), breathingBPM*100 (u16), heartBPM*10000 (u32), rssi(i8), n_persons, motionEnergy(f32), presenceScore(f32), ts_ms(u32)` — passthrough jujur
- Rolling window 5s (`deque` timestamps → pps), variance heuristic via `numpy` (I/Q magnitude `sqrt(I²+Q²)` → `var/20`), threshold `presence = variance > 1.2`
- `motionBand = std(20 recent var)` clamped 0..0.5, `breathingBand = mean*0.06 + motion*0.3` clamped 0..0.3
- Broadcast ke WS clients via `asyncio` callbacks; signal_field 20×20 stub
- F1 heuristik dulu (tanpa torch), F2 `csi-embed-v2.safetensors` (39.7KB) sengaja di-skip, pose stub `confidence 0` signal-derived

## Env flags
| Var | Default | Efek |
|-----|---------|------|
| `UDP_HOST` | `0.0.0.0` | bind host UDP |
| `UDP_PORT` | `5005` | bind port UDP |
| `ENABLE_UDP` | `1` | `0` → disable UDP, jalan simulated-only |
| `ENABLE_SECONDARY_PROXY` | `1` | `0` → matikan WS proxy 3001 |
| `SECONDARY_PROXY_PORT` | `3001` | port proxy untuk vendor mapping 3000→3001 |
| `ENABLE_NODE_UDP` (Node) | `1` | set `0` bila Python shim jalan, agar Node tidak dobel-bind 5005 |

## Konflik Node (sudah dipatch)
`server/index.js` sekarang guard:
```js
const ENABLE_NODE_UDP = process.env.ENABLE_NODE_UDP !== '0' ...
if (ENABLE_NODE_UDP) { udp.bind(...) } else { console.log('[UDP] disabled — Python owns 5005') }
```
**Aturan**: jangan jalankan `node server/index.js` (UDP) dan `uvicorn server_py.app` bersamaan tanpa `ENABLE_NODE_UDP=0`. Shim **harus** jadi satu-satunya listener UDP 5005.

## Troubleshooting
| Gejala | Sebab | Fix |
|--------|-------|-----|
| `OSError: [Errno 10048] bind 5005` | Node masih bind 5005 | Stop Node atau `ENABLE_NODE_UDP=0` |
| Banner tetap `SIMULATED` | Belum ada paket UDP | Cek ESP `target_ip` → IP laptop, firewall `netsh advfirewall firewall add rule name="ESP32 CSI" dir=in action=allow protocol=UDP localport=5005`, atau kirim dummy UDP test di atas |
| WS reconnect loop | UI vendor `sensing.service` map 3000→3001 | Shim sudah proxy 3001 otomatis; cek `ws://localhost:3001/ws/sensing` reachable |
| CORS error | — | Shim sudah `CORSMiddleware allow_origins=["*"]` |
| `web/ui` 404 | Path mount salah | Cek `UI_DIR` log saat startup; pastikan run dari repo root `D:\AI\WiFiSense` |

## File yang dibuat
- `server_py/app.py` — FastAPI + WS + static
- `server_py/csi_ingest.py` — UDP parser + heuristics
- `server_py/README_BE.md` — ini
- `requirements.txt` — tambah `fastapi, uvicorn[standard], python-multipart`
- `server/index.js` — guard `ENABLE_NODE_UDP`
