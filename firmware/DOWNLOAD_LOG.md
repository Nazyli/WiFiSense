# DOWNLOAD_LOG — Firmware Opsi B (Prebuilt)

> Tanggal: 2026-09-13 01:22 UTC+7 (Asia/Jakarta)
> Chip target: ESP32-S3 (QFN56 rev0.2) 16MB flash / 8MB PSRAM — MAC <YOUR_DEVICE_MAC>
> Port aktif: COM4 (USB VID_303A PID_1001 USB Serial Device) — terverifikasi CONFIGURED ✅
> SSID: `FLAMBOYAN'S` / password `<YOUR_WIFI_PASSWORD>`

## 1. Ringkasan Hasil

**SEMUA URL PREBUILT .bin GAGAL — tidak ada release prebuilt untuk kedua repo. File `merged.bin` placeholder dibuat, status NOT READY. Perlu build manual via ESP-IDF (Opsi A) atau tunggu upload manual ke `firmware/merged.bin`.**

- `Steven063/ESP32-CSI-Tool` → 404 Not Found (repo tidak ada; ejaan salah di instruksi awal — yang benar `StevenMHernandez/ESP32-CSI-Tool`)
- `StevenMHernandez/ESP32-CSI-Tool` → 0 releases (api.github.com/repos/.../releases → `[]`)
- `espressif/esp-csi` → 0 releases (repo resmi Espressif juga tidak publish binary; hanya source + examples, build via ESP-IDF)
- `ruvnet/RuView` → 30 releases tapi semua `assets: 0` (tanpa binary lampiran)
- Alternatif `https://github.com/ESP32-CSI-Tool` → tidak ada (404)

Kesimpulan: Opsi B prebuilt ~2MB tidak tersedia per 2026-09-13. Harus build dari source.

## 2. Urutan Coba (sesuai instruksi)

### a) Steven063/ESP32-CSI-Tool (instruksi awal)

```
GET https://api.github.com/repos/Steven063/ESP32-CSI-Tool/releases/latest
→ 404 {"message":"Not Found"}

gh api repos/Steven063/ESP32-CSI-Tool/releases/latest
→ 404 Not Found

Invoke-RestMethod https://api.github.com/repos/Steven063/ESP32-CSI-Tool
→ 404
```

Diagnosis: repo `Steven063/ESP32-CSI-Tool` tidak eksis. Hasil `gh search` menunjukkan yang benar adalah `StevenMHernandez/ESP32-CSI-Tool`.

### b) Koreksi: StevenMHernandez/ESP32-CSI-Tool

```
GET https://api.github.com/repos/StevenMHernandez/ESP32-CSI-Tool/releases/latest
→ 404 {"message":"Not Found","documentation_url":"https://docs.github.com/rest/releases/releases#get-the-latest-release"}

GET https://api.github.com/repos/StevenMHernandez/ESP32-CSI-Tool/releases
→ [] (0 releases)

GET https://api.github.com/repos/StevenMHernandez/ESP32-CSI-Tool/tags → ada tag tapi tanpa release asset
```

Repo description: "Extract Channel State Information from WiFi-enabled ESP32" — hanya source `active_ap`, `active_sta`, `passive`. Tidak publish `.bin`.

### c) Alternatif espressif/esp-csi

```
GET https://api.github.com/repos/espressif/esp-csi/releases/latest → 404
GET https://api.github.com/repos/espressif/esp-csi/releases → [] (0)
Browsing https://github.com/espressif/esp-csi → hanya folder examples/get-started, esp-radar, esp-crab — tidak ada Releases
```

README espressif/esp-csi menegaskan: semua support CSI tapi via build ESP-IDF, bukan prebuilt.

### d) Fallback zip source (berhasil)

Karena prebuilt tidak ada, download source zip sebagai fallback untuk build lokal:

```
Invoke-WebRequest https://github.com/espressif/esp-csi/archive/refs/heads/master.zip
  → D:\AI\WiFiSense\firmware\esp-csi-master.zip
  → Size: 25,026,658 bytes (24 MB)
  → SHA256: D3EBAB4ED32D9A28AB04B7A719B2EAB303BCE311471D518583667BF6E5C9B903
  → Extracted: firmware/esp-csi-tmp/esp-csi-master/ (examples: get-started/csi_recv, csi_recv_router, csi_send, console_test, wifi_sensing_demo)

GitHub API rate OK, bukan blocked — hanya memang tidak ada asset .bin.
```

`firmware/esp-csi-master.zip` dipertahankan sebagai cache sumber. Hapus `esp-csi-tmp` setelah baca jika butuh hemat disk, atau pakai untuk build.

## 3. File Saat Ini di firmware/

```
D:\AI\WiFiSense\firmware\
  README.md                1722 B  (dokumentasi asli)
  esp-csi-master.zip       25,026,658 B  SHA256 D3EBAB4E...
  esp-csi-tmp/             extracted source (opsional, bisa hapus)
  DOWNLOAD_LOG.md          (file ini)
  READY.md                 status NOT READY
  merged.bin               PLACEHOLDER 4096 B — BUKAN firmware valid, jangan flash!
```

Tidak ada `bootloader.bin` / `partition-table.bin` / `firmware.bin` valid. `merged.bin` placeholder dibuat agar struktur siap; esptool `image_info` akan gagal (expected).

## 4. Placeholder merged.bin

- Path: `D:\AI\WiFiSense\firmware\merged.bin` (4 KB, header tekstual)
- Isi: 0xE9 dummy + pesan "PLACEHOLDER — build required"
- Validasi: `python -m esptool --chip esp32s3 image_info firmware/merged.bin` → expected fail "Invalid image header"
- Tindakan user: hapus file ini, ganti dengan `merged.bin` asli hasil `idf.py build` (lihat docs/OPSI-B-DOWNLOAD.md) lalu flash.

## 5. Next Step untuk User

1. **Opsi A (recommended):** Build dari source — lihat `docs/PLAN-OPSI-A.md` (ESP-IDF 5.4 + `idf.py set-target esp32s3` + `idf.py build` di `_ruview` atau `esp-csi-tmp/esp-csi-master/examples/get-started/csi_recv_router`)
2. **Opsi B manual:** Ikuti `docs/OPSI-B-DOWNLOAD.md` — drag-drop binary asli ke `firmware/merged.bin`, lalu flash:
   ```powershell
   [System.IO.Ports.SerialPort]::getPortNames()   # pastikan COM4
   python -m esptool --chip esp32s3 --port COM4 chip-id   # verifikasi MAC <YOUR_DEVICE_MAC>
   .\scripts\flash.ps1 -Port COM4 -Merged -Baud 460800
   ```
   Jika tidak ada binary, build tetap diperlukan — tidak ada link magic 2MB.

## 6. Log Mentah Perintah

```powershell
[System.IO.Ports.SerialPort]::getPortNames() → COM4
Get-CimInstance Win32_SerialPort → DeviceID COM4 / USB\VID_303A&PID_1001&MI_00\6&5CD5794&0&0000
python -m esptool --chip esp32s3 --port COM4 chip-id → Chip ESP32-S3 QFN56 rev0.2 PSRAM 8MB MAC <YOUR_DEVICE_MAC> ✅
gh search repos "ESP32-CSI-Tool" → StevenMHernandez/ESP32-CSI-Tool (correct)
curl api.github.com/repos/StevenMHernandez/ESP32-CSI-Tool/releases → []
curl api.github.com/repos/espressif/esp-csi/releases → []
Invoke-WebRequest esp-csi master.zip → 25MB SHA256 D3EBAB4E...
gh api repos/ruvnet/RuView/releases → 30 releases assets 0
Get-FileHash esp-csi-master.zip → D3EBAB4ED32D9A28AB04B7A719B2EAB303BCE311471D518583667BF6E5C9B903
```

## 7. Catatan SSID FLAMBOYAN'S

SSID mengandung apostrophe `'`. Di PowerShell wajib kutip ganda: `"FLAMBOYAN'S"` / di `menuconfig` isi literal `FLAMBOYAN'S`. Jangan pakai single-quote PowerShell `'FLAMBOYAN'S'` (akan terpotong). Password `<YOUR_WIFI_PASSWORD>`.

---
*Generated by @fixer 2026-09-13 — Opsi B prebuilt not found; fallback source cached.*
