// WiFiSense Node bridge — Serial CSI -> WebSocket
// Minimal scaffolding, tanpa heavy deps wajib install.
// Jalankan: npm install && npm start
// Default: baca serial COM3 115200, broadcast ke ws://localhost:8080

import { SerialPort } from 'serialport';
import { ReadlineParser } from '@serialport/parser-readline';
import { WebSocketServer } from 'ws';
import express from 'express';
import cors from 'cors';

const SERIAL_PORT = process.env.SERIAL_PORT || 'COM3';
const BAUD = parseInt(process.env.BAUD || '115200', 10);
const HTTP_PORT = parseInt(process.env.HTTP_PORT || '3000', 10);
const WS_PORT = parseInt(process.env.WS_PORT || '8080', 10);

const app = express();
app.use(cors());
app.use(express.json());

let latestCSI = null;
let clients = 0;

app.get('/', (req, res) => res.json({ status: 'ok', service: 'wifisense-bridge', ws: `ws://localhost:${WS_PORT}`, latest: latestCSI ? 'available' : 'none' }));
app.get('/csi', (req, res) => res.json(latestCSI || { error: 'no data yet' }));

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
  const msg = JSON.stringify(obj);
  for (const c of wss.clients) if (c.readyState === 1) c.send(msg);
}

// Serial — optional, jangan crash jika port tidak ada
try {
  const port = new SerialPort({ path: SERIAL_PORT, baudRate: BAUD, autoOpen: false });
  const parser = port.pipe(new ReadlineParser({ delimiter: '\n' }));
  port.open((err) => {
    if (err) {
      console.warn(`[Serial] gagal buka ${SERIAL_PORT} ${BAUD}: ${err.message}`);
      console.warn(`Set SERIAL_PORT env atau cek Device Manager. Server tetap jalan tanpa serial.`);
      return;
    }
    console.log(`[Serial] listening ${SERIAL_PORT} @ ${BAUD}`);
  });
  parser.on('data', (line) => {
    line = line.trim();
    if (!line) return;
    // Contoh format RuView: CSI_DATA,xx,yy,[...]
    if (line.includes('CSI')) {
      console.log(`[CSI] ${line.slice(0, 120)}`);
      broadcast({ type: 'csi', raw: line, ts: Date.now() });
    } else {
      // log biasa
      // console.log(`[Serial] ${line}`);
      broadcast({ type: 'log', raw: line, ts: Date.now() });
    }
  });
  port.on('error', (e) => console.error(`[Serial] error: ${e.message}`));
} catch (e) {
  console.warn(`[Serial] init failed: ${e.message}`);
}
