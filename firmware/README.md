# Firmware — ESP32-S3 CSI Node

Folder ini untuk binary & source firmware CSI.

## File yang diharapkan

```
firmware/
├─ bootloader.bin          (0x0000)
├─ partition-table.bin     (0x8000)
├─ firmware.bin            (0x10000)  atau esp32-csi-node.bin
└─ merged.bin              (alternatif single-file 0x0)
```

## Sumber firmware

### Opsi 1 — RuView (recommended)

Repo: https://github.com/ruvnet/RuView

Jika clone `_ruview` sukses, firmware ada di:

```
_ruview/firmware/esp32-csi-node/
_ruview/esp32-csi-node/
_ruview/src/esp32/
```

Build via ESP-IDF:

```powershell
cd _ruview/firmware/esp32-csi-node
idf.py set-target esp32s3
idf.py menuconfig  # set WiFi SSID/PASS, enable CSI
idf.py build
# hasil di build/bootloader/bootloader.bin, build/partition_table/..., build/esp32-csi-node.bin
xcopy build\bootloader\bootloader.bin ..\..\firmware\ /Y
xcopy build\partition_table\partition-table.bin ..\..\firmware\ /Y
xcopy build\esp32-csi-node.bin ..\..\firmware\firmware.bin /Y
```

### Opsi 2 — ESP32-CSI-Tool / esp-csi (prebuilt) — STATUS 2026-09-13: TIDAK ADA PREBUILT

> **Update 2026-09-13 @fixer:** Prebuilt ~2MB **tidak tersedia**. Repo `Steven063/ESP32-CSI-Tool` salah eja (404). Yang benar `StevenMHernandez/ESP32-CSI-Tool` → 0 releases. `espressif/esp-csi` juga 0 releases. `ruvnet/RuView` 30 releases tapi assets 0. Lihat `DOWNLOAD_LOG.md` & `READY.md`.

- Repo benar: https://github.com/StevenMHernandez/ESP32-CSI-Tool (source only, `active_ap` / `active_sta` / `passive` — build via ESP-IDF)
- Alternatif Espressif: https://github.com/espressif/esp-csi (source `examples/get-started/csi_recv_router`, `console_test` — sudah ter-cache sebagai `firmware/esp-csi-master.zip` 25MB SHA256 D3EBAB4E...)
- Jika kelak ada release, download `.bin` dan drop ke `firmware/merged.bin`, lalu:
  ```powershell
  Get-FileHash firmware\merged.bin -Algorithm SHA256
  python -m esptool --chip esp32s3 image-info firmware\merged.bin
  .\scripts\flash.ps1 -Port COM4 -Merged
  ```
  Detail lengkap: `docs/OPSI-B-DOWNLOAD.md`

**Saat ini:** `firmware/merged.bin` adalah placeholder 4KB (SHA256 B158A2CB...) — **jangan flash**. Hapus & ganti dengan binary asli >1MB sebelum flash. Status `READY.md` = 🔴 NOT READY.

### Opsi 3 — Download manual (jika git gagal)

Clone manual via browser:

1. Buka https://github.com/ruvnet/RuView
2. Code -> Download ZIP
3. Extract, copy `firmware/*.bin` ke sini

Atau via git di PowerShell:

```powershell
git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview
```

## Flash (COM4 — MAC <YOUR_DEVICE_MAC>, 16MB flash / 8MB PSRAM)

Cek port dulu (bisa pindah COM3 setelah hard reset):

```powershell
[System.IO.Ports.SerialPort]::getPortNames()
python -m esptool --chip esp32s3 --port COM4 chip-id  # harus ESP32-S3 MAC <YOUR_DEVICE_MAC>
```

Lihat `scripts/flash.ps1`:

```powershell
.\scripts\flash.ps1 -Port COM4          # 3-file (bootloader 0x0, partition 0x8000, firmware 0x10000)
.\scripts\flash.ps1 -Port COM4 -Merged  # merged.bin 0x0 (recommended jika sudah punya merged.bin)
# jika COM4 hilang: .\scripts\flash.ps1 -Port COM3 -Merged -Baud 115200
# tahan BOOT + tap RESET jika "Connecting..."
```

> SSID `FLAMBOYAN'S` mengandung `'` — di `menuconfig` dan PowerShell wajib kutip ganda `"FLAMBOYAN'S"` (password `<YOUR_WIFI_PASSWORD>`). Status placeholder lihat `firmware/READY.md`, log download lihat `firmware/DOWNLOAD_LOG.md`, langkah manual Opsi B lihat `docs/OPSI-B-DOWNLOAD.md`.

## Cat clone gagal

Jika `_ruview` tidak ada (internet blocked / timeout), folder ini tetap placeholder. Ikuti Opsi 3 download manual.
