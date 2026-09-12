// WiFiSense Node bridge — UDP CSI (ESP32) + Serial -> WebSocket/HTTP
// ESP32 RuView 0.8.8 kirim CSI via UDP ke laptop 192.168.1.75:5005 (ADR-018 binary)
// Jalankan: npm install && npm start
// Env: UDP_PORT=5005 HTTP_PORT=3000 WS_PORT=8080 SERIAL_PORT=COM4 (optional)

import dgram from 'dgram';
import { SerialPort } from 'serialport';
import { ReadlineParser } from '@serialport/parser-readline';
import { WebSocketServer } from 'ws';
import express from 'express';
import cors from 'cors';

const SERIAL_PORT = process.env.SERIAL_PORT || '';
const BAUD = parseInt(process.env.BAUD || '115200', 10);
const HTTP_PORT = parseInt(process.env.HTTP_PORT || '3000', 10);
const WS_PORT = parseInt(process.env.WS_PORT || '8080', 10);
const UDP_PORT = parseInt(process.env.UDP_PORT || '5005', 10);
const UDP_HOST = process.env.UDP_HOST || '0.0.0.0';
// Guard: Python shim (server_py) harus jadi SATU-SATUNYA listener UDP 5005.
// Node bridge dobel-bind akan gagal / race. Set ENABLE_NODE_UDP=0 bila Python jalan.
const ENABLE_NODE_UDP = process.env.ENABLE_NODE_UDP !== '0' && process.env.ENABLE_NODE_UDP !== 'false' && process.env.ENABLE_NODE_UDP !== 'False';

const app = express();
app.use(cors());
app.use(express.json());

let latestCSI = null;
let clients = 0;
let udpStats = { count: 0, bytes: 0, lastFrom: null, lastLen: 0, lastTs: null, pps: 0, firstTs: null };
let _ppsWindow = [];

app.get('/', (req, res) => res.json({ status: 'ok', service: 'wifisense-bridge', udp: `udp://${UDP_HOST}:${UDP_PORT}`, ws: `ws://localhost:${WS_PORT}`, latest: latestCSI ? 'available' : 'none', stats: udpStats }));
app.get('/csi', (req, res) => res.json(latestCSI || { error: 'no data yet' }));
app.get('/stats', (req, res) => res.json({ ...udpStats, uptimeSec: udpStats.firstTs ? Math.round((Date.now() - udpStats.firstTs) / 1000) : 0 }));
app.get('/health', (req, res) => res.json({ ok: true, udpListening: udpListening, packets: udpStats.count }));

app.listen(HTTP_PORT, () => console.log(`[HTTP] http://localhost:${HTTP_PORT}`));

const wss = new WebSocketServer({ port: WS_PORT });
wss.on('connection', (ws) => {
  clients++;
  console.log(`[WS] client connected (${clients})`);
  if (latestCSI) ws.send(JSON.stringify(latestCSI));
  ws.on('close', () => { clients--; console.log(`[WS] client disconnected (${clients})`); });
});
console.log(`[WS] ws://localhost:${WS_PORT}`);

function broadcast(obj) {
  latestCSI = obj;
  let msg;
  try { msg = JSON.stringify(obj); } catch { return; }
  for (const c of wss.clients) {
    try { if (c.readyState === 1) c.send(msg); } catch { /* abaikan client mati */ }
  }
}

process.on('uncaughtException', (e) => console.error(`[FATAL] uncaught: ${e.message}`));

// Serial — optional, hanya jika SERIAL_PORT di-set (ESP sekarang via UDP, bukan serial)
if (SERIAL_PORT) {
  try {
    const port = new SerialPort({ path: SERIAL_PORT, baudRate: BAUD, autoOpen: false });
    const parser = port.pipe(new ReadlineParser({ delimiter: '\n' }));
    port.open((err) => {
      if (err) {
        console.warn(`[Serial] gagal buka ${SERIAL_PORT} ${BAUD}: ${err.message}`);
        return;
      }
      console.log(`[Serial] listening ${SERIAL_PORT} @ ${BAUD}`);
    });
    parser.on('data', (line) => {
      line = line.trim();
      if (!line) return;
      if (line.includes('CSI')) {
        console.log(`[CSI-serial] ${line.slice(0, 120)}`);
        broadcast({ type: 'csi-serial', raw: line, ts: Date.now() });
      }
    });
    port.on('error', (e) => console.error(`[Serial] error: ${e.message}`));
  } catch (e) {
    console.warn(`[Serial] init failed: ${e.message}`);
  }
} else {
  console.log('[Serial] skip (SERIAL_PORT kosong — ESP via UDP)');
}

// UDP CSI listener — ESP32 RuView 0.8.8 kirim ADR-018 binary ke 192.168.1.75:5005
// !! DANGER: jangan dobel-bind 5005 dengan Python shim. Python shim (server_py) adalah SATU-SATUNYA listener sekarang.
// Node UDP dimatikan bila ENABLE_NODE_UDP=0  (set saat `uvicorn server_py.app:app --port 3000` jalan)
let udpListening = false;
let udp = null;
if (ENABLE_NODE_UDP) {
  udp = dgram.createSocket('udp4');
  udp.on('error', (e) => console.error(`[UDP] error: ${e.message}`));
  udp.on('listening', () => {
    udpListening = true;
    const a = udp.address();
    console.log(`[UDP] listening ${a.address}:${a.port} (tunggu paket dari ESP 192.168.1.92)`);
  });
  udp.on('message', (msg, rinfo) => {
    const now = Date.now();
    udpStats.count++;
    udpStats.bytes += msg.length;
    udpStats.lastFrom = `${rinfo.address}:${rinfo.port}`;
    udpStats.lastLen = msg.length;
    udpStats.lastTs = now;
    if (!udpStats.firstTs) udpStats.firstTs = now;
    _ppsWindow.push(now);
    const cut = now - 5000;
    while (_ppsWindow.length && _ppsWindow[0] < cut) _ppsWindow.shift();
    udpStats.pps = Math.round(_ppsWindow.length / 5);

    const magic = msg.length >= 4 ? msg.readUInt32LE(0).toString(16) : 'short';
    const preview = msg.subarray(0, Math.min(32, msg.length)).toString('hex');
    if (udpStats.count <= 3 || udpStats.count % 100 === 1) {
      console.log(`[UDP] #${udpStats.count} ${msg.length}B dari ${rinfo.address}:${rinfo.port} magic=0x${magic} head=${preview.slice(0, 48)}... pps~${udpStats.pps}`);
    }
    const obj = { type: 'csi-udp', len: msg.length, from: `${rinfo.address}:${rinfo.port}`, magic: `0x${magic}`, previewHex: preview, ts: now, pps: udpStats.pps };
    broadcast(obj);
  });
  udp.bind(UDP_PORT, UDP_HOST);
} else {
  console.log('[UDP] disabled via ENABLE_NODE_UDP=0 — Python shim (server_py) owns UDP 5005. Node bridge hanya HTTP+WS.');
  // keep udpListening false so /health reports correctly
}
