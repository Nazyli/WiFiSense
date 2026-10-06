# Spec: Mode Sniff Serial + Radio Connect WiFi / Sniff Channel

Tanggal: 2026-09-13 | Status: disetujui user (desain), spec menunggu review | Opsi: B (sniff via USB/serial, laptop sama)

## 1. Latar & keputusan

- `Test` saat ini hanya cek link UDP (`pps>0`), tidak validasi SSID. 1 SSID = 1 channel AP, jadi Hop sambil connect
  memutus koneksi sesaat (off-channel, pps drop).
- Keputusan user: pendekatan A (radio eksplisit), penamaan diserahkan, channel mode mendukung spesifik
  maupun semua channel (hop 1,6,11).
- Fakta kode: firmware sudah `esp_wifi_set_promiscuous(true)` + stream `CSI_DATA` via serial 115200;
  `csi_ingest` hanya dengar UDP; tidak ada parser serial Python; tidak ada mode AP di firmware.

## 2. UX: radio di panel WiFi

Radio di atas form, `wifiDraft.mode: 'wifi' | 'channel'` (default `'wifi'`, draft lama aman).
Nama radio: `Connect WiFi` / `Sniff Channel`.

- Mode `Connect WiFi`: SSID + password tampil; channel hidden (kirim null/auto ngikut AP); hop hidden.
- Mode `Sniff Channel`: SSID/password hidden; dropdown channel `1 / 6 / 11 / Semua (hop)` tampil;
  baris Target IP + badge MATCH/MISMATCH + tombol Re-target hidden (tidak ada link UDP pembanding);
  COM Port tetap (satu port untuk flash + baca serial).
- `Test` validasi per mode: wifi wajib SSID terisi; channel wajib COM dipilih. Draft lama dengan
  channel `'auto'` yang dibuka di mode channel dianggap `'all'`. Status live + badge
  tetap di `#qs-wifi-status` / `#qs-wifi-test-badge`. Berlaku di `quick-settings.js` dan `SettingsPanel.js`.

## 3. Kontrak Apply (POST /api/v1/config/*)

- wifi: `{mode:'wifi', ssid, password, channel:null, target_ip, port}` (seperti sekarang).
- channel spesifik: `{mode:'channel', channel:6, port}` tanpa ssid/password/target_ip.
- channel semua: `{mode:'channel', hop_channels:'1,6,11', port}` tanpa ssid/password/target_ip.
- `provision.py build_nvs_csv` sudah dukung semua kombinasi (ssid opsional, `csi_channel` / `hop_count`+
  `chan_list`+`dwell_ms=200`) tanpa perubahan.
- Mode dipersist ke provision state per-port agar backend tahu mode aktif (`get_ingest_mode()`,
  default `'wifi'` bila state tak ada).

## 4. Backend ingest (`server_py/csi_ingest.py`, `server_py/app.py`)

- Ekstrak `ingest_frame(data: bytes, src: str)` dari `datagram_received` (csi_ingest.py:639-704):
  update `_stats`/`lastTs` -> `_update_pps` -> dispatch magic -> `_handle_csi`/`_handle_vitals` ->
  `_build_sensing_update` + broadcast. UDP handler dan serial reader sama-sama memanggilnya.
- `start_serial_reader(port, baud)`: thread pyserial `Readline` -> parser toleran
  `CSI_DATA, len=.., rssi=.., channel=.., [...]` -> bentuk `parse_csi_packet` -> `_handle_csi`.
  Baris tak dikenal di-log (level debug/info) agar bisa iterasi bila format firmware beda.
- Reader ingest bila (a) mode provisioned == `'channel'`, ATAU (b) tidak ada frame UDP dalam 5 detik
  terakhir (fallback otomatis: misal user pilih Sniff Channel di UI lalu langsung Test sebelum Apply,
  atau link wifi putus tapi USB masih stream). Di mode wifi + link UDP hidup, serial diabaikan
  (anti double-count pps). Label `source` = asal frame terakhir.
- `_handle_csi` menerima label sumber; `get_stats`/`_health_payload` memetakan `source: 'serial'`
  bila frame terakhir dari serial. Seluruh REST/WS (health, sensing/latest, csi, stats, ws) tidak berubah.
- `app.py`: env `ENABLE_SERIAL` (default 0), `SERIAL_PORT` (default COM4), `SERIAL_BAUD` (default 115200);
  hook `on_startup` setelah UDP listener; cleanup di `on_shutdown`.
- Eksklusivitas COM: reader ditutup sebelum `_run_provision` / `_esptool_reset`, dibuka lagi setelah;
  toleran COM hilang sesaat pasca-reset S3 (re-open dengan backoff). Monitor manual / Node bridge
  tidak boleh bareng (sudah didokumentasikan di FLASHING.md:11).

## 5. Verifikasi

- `py_compile` + `node --check` kedua file frontend; `git diff` review.
- `ENABLE_SERIAL=1 SERIAL_PORT=COM4 uvicorn server_py.app:app --port 3000 --reload` (monitor mati).
- Apply mode channel spesifik -> Test PASS `via serial pps>0` -> `GET /health/health` = `source: serial`.
- Apply mode channel semua (hop) -> pps>0.
- Regresi: Apply wifi lama tetap OK, Test wifi tetap cek UDP, badge MATCH/MISMATCH wifi tetap jalan.
- Risiko: format `CSI_DATA` aktual firmware 0.8.8 belum terverifikasi di lapangan; mitigasi = parser
  toleran + log baris tak dikenal, iterasi dari log user.

## 6. Non-tujuan

Mode AP (opsi C), perubahan firmware, baud selain 115200 default, multi-port serial, e2e broadening.
