# READY — Firmware Status

> Chip: ESP32-S3 QFN56 rev0.2 16MB flash / 8MB PSRAM — MAC <YOUR_DEVICE_MAC> — Port COM4
> Tanggal: 2026-09-13 Asia/Jakarta
> Bundle: RuView v0.8.8-esp32 **S3 8MB flash** (kompatibel dengan chip fisik 16MB)

## Status: 🟡 READY 8MB-on-16MB (16MB bundle tidak dirilis, 8MB valid)

Bundle **16MB flash tidak pernah dirilis** upstream (diverifikasi 331 releases, `*16mb*` = 0 hasil, log lengkap di `BUNDLE-16MB-LOG.md`). Variasi yang ada hanya `s3-8mb` dan `s3-4mb` (plus `c6-4mb`). File yang benar untuk chip 16MB adalah **`esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip`** yang sudah ada — partition table 8MB aman di flash fisik 16MB (sisa 8MB tidak terpakai).

### Verifikasi

- **ZIP:** `D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip` — 778550 B — SHA256 `132D3D4FE3F23625ECCBF6B4C2F404B31CB94F754BB2638D98CF2D0F65F8DE46` ✅ (cocok SHA256SUMS.txt canonical)
- **Extract:** `firmware\bundle-extract\` (original) + duplikat `firmware\bundle-16mb-extract\` — 8 file — hash ✅:
  - `bootloader.bin` 18880 B `7b8e80af...` ✅
  - `partition-table.bin` 3072 B `67222c25...` ✅
  - `ota_data_initial.bin` 8192 B `7d2c7ac4...` ✅
  - `esp32-csi-node.bin` 1127104 B `baf6f86d...` ✅
  - `version.txt` = `0.8.8`
- **Firmware root:** `firmware\bootloader.bin`, `partition-table.bin`, `ota_data_initial.bin`, `esp32-csi-node.bin`, `firmware.bin` (copy) — overwrite & terverifikasi
- **Log 16MB:** `firmware\BUNDLE-16MB-LOG.md` — 11 URL diuji, semua 404 expected, 0 asset 16mb di GitHub
- **Flash size note:** `esptool --chip esp32s3 --port COM4 flash_id` mendeteksi `16MB`, flash dengan bundle 8MB pakai `--flash_size 8MB` atau `detect` (jangan paksa 16MB di write_flash). Contoh valid di `BUNDLE-16MB-LOG.md §4`.

### Next Step (tanpa flash otomatis)

Task @fixer ini **tidak melakukan flash** (sesuai instruksi). Untuk flash manual:

```powershell
# cek port
[System.IO.Ports.SerialPort]::getPortNames()
python -m esptool --chip esp32s3 --port COM4 chip-id   # harus MAC <YOUR_DEVICE_MAC>

# flash 4-file (preserve NVS, recommended)
python -m esptool --chip esp32s3 --port COM4 --baud 460800 write_flash `
  0x0000 firmware\bootloader.bin `
  0x8000 firmware\partition-table.bin `
  0xf000 firmware\ota_data_initial.bin `
  0x20000 firmware\esp32-csi-node.bin

# atau via script
.\scripts\flash.ps1 -Port COM4
# jika COM4 hilang setelah reset: .\scripts\flash.ps1 -Port COM3 -Baud 115200
```

Setelah flash, monitor:

```powershell
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
# atau
python -m serial.tools.miniterm COM4 115200 --raw
```

Harus keluar log CSI / boot RuView 0.8.8. Validasi 5-menit burn-in tanpa parser/transport error sebelum kalibrasi.

### Catatan ESP-IDF

User sedang download ESP-IDF v5.4 ke `C:\Espressif` (~4-6GB) manual — tidak diinstal oleh @fixer. Jika butuh build custom partition 16MB penuh, gunakan ESP-IDF tersebut + `idf.py set-target esp32s3` + edit `partitions.csv`.

---
*Updated by @fixer 2026-09-13 — READY 8MB-on-16MB, 16MB bundle not existent.*
