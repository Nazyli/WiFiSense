# ESP32_VERIFY — Lane ESP32 WiFiSense

> Tanggal: 2026-09-13 Asia/Jakarta | Chip: ESP32-S3 QFN56 rev0.2 16MB flash / 8MB PSRAM — MAC `<YOUR_DEVICE_MAC>` — Port `COM4` | Bundle: **RuView v0.8.8-esp32 S3 8MB** (kompatibel 16MB fisik) | Operator: @fixer

## 1. File Verifikasi (ls)

```
firmware/*.bin  (5 file, semua ada):
  bootloader.bin         18880 B  SHA256 7B8E80AF12BCC36E74509FAA58F691CC9E40892DB7DE7BFF808BCBE3AD06ACF4 ✅
  partition-table.bin     3072 B  SHA256 67222C257C0477501FD4002275638DC4262B34EB68235B8289FB1337054D322B ✅
  ota_data_initial.bin    8192 B  SHA256 7D2C7AC4888BFD75CD5F56E8D61F69595121183AFC81556C876732FD3782C62F ✅
  esp32-csi-node.bin   1127104 B  SHA256 BAF6F86DC593156A19F837C56A1A1B235123D2EDACF5F582363302097E3AE8F2 ✅
  firmware.bin         1127104 B  (copy esp32-csi-node.bin, kompatibilitas script lama) ✅

firmware/bundle-extract/        8 file (READY.md §14)
firmware/bundle-16mb-extract/   duplikat identik (BUNDLE-16MB-LOG.md)
firmware/READY.md               ada
firmware/BUNDLE-16MB-LOG.md     ada
nvs_config.csv                  ada (root, lihat §4)
firmware/provision.py           520 baris — --help OK (utf8), --dry-run OK
scripts/flash.ps1               ada (akan di-align ke 4-file di HARDWARE.md)
scripts/monitor.ps1             ada
```

**Catatan ZIP:** `esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip` (778550 B, SHA256 `132D3D4FE3F23625ECCBF6B4C2F404B31CB94F754BB2638D98CF2D0F65F8DE46`) terverifikasi di READY.md §13 & BUNDLE-16MB-LOG.md §2 — file ZIP sekarang gitignored (`.gitignore: firmware/*.zip, *.zip, firmware/*.bin`) sehingga tidak tercantum di `git ls-files`; binary lokal tetap valid di bundle-extract & firmware root. Bundle 16MB tidak pernah dirilis upstream (331 releases, 0 hasil `*16mb*`, BUNDLE-16MB-LOG.md §1/§3) — 8MB valid untuk chip 16MB.

## 2. Hash Match

| File | Expected SHA256 | Lokal | Status |
|------|-----------------|-------|--------|
| Bundle ZIP `s3-8mb` | `132D3D4F...65F8DE46` (READY.md:5, SHA256SUMS.txt) | bundle-extract diverifikasi | ✅ match (ZIP gitignored, extract hash ✅) |
| `bootloader.bin` | `7b8e80af...06acf4` | `7B8E80AF...06ACF4` | ✅ |
| `partition-table.bin` | `67222c25...4d322b` | `67222C25...4D322B` | ✅ |
| `ota_data_initial.bin` | `7d2c7ac4...782c62f` | `7D2C7AC4...782C62F` | ✅ |
| `esp32-csi-node.bin` | `baf6f86d...e3ae8f2` (SHA256SUMS.txt) | `BAF6F86D...E3AE8F2` | ✅ |
| `version.txt` | `0.8.8` | `0.8.8` | ✅ |
| esptool | `v5.4.0` | `v5.4.0` terdeteksi | ✅ |

> Semua hash cocok dengan `SHA256SUMS.txt` canonical & BUNDLE-16MB-LOG.md §2. `Get-FileHash` lokal menghasilkan hash identik.

## 3. Chip & Port

- Chip fisik: **ESP32-S3 QFN56 rev0.2 16MB / 8MB PSRAM** — `flash_id` mendeteksi 16MB (READY.md:22), flash dengan bundle 8MB pakai `--flash_size 8MB` atau `detect` (jangan paksa 16MB).
- MAC: `<YOUR_DEVICE_MAC>` (READY.md:3, BUNDLE-16MB-LOG.md)
- Port: `COM4` (fallback `COM3` jika CDC pindah setelah reset — lihat HARDWARE.md §42-66 & scripts/flash.ps1).
- Download mode: **S3 Native USB CDC** — tahan **BOOT (GPIO0) + tap RESET (EN)** (§42-58 HARDWARE.md).

## 4. Provision — nvs_config.csv & provision.py

**nvs_config.csv** (`D:\AI\WiFiSense\nvs_config.csv`, 148 B):
```csv
key,type,encoding,value
csi_cfg,namespace,,
ssid,data,string,FLAMBOYAN'S
password,data,string,<YOUR_WIFI_PASSWORD>
target_ip,data,string,192.168.1.75
```

Namespace `csi_cfg` — WiFi SSID `FLAMBOYAN'S`, target aggregator `192.168.1.75:5005` (default port 5005). Field tambahan tersedia via `provision.py`: `--tdm-slot/--tdm-total`, `--edge-tier/--pres-thresh/--fall-thresh`, `--channel/--filter-mac` (ADR-039/060/073/066 — lihat `provision.py --help`).

**Provision command contoh (COM4, dry-run verified):**
```powershell
# --help OK (PYTHONIOENCODING=utf-8 untuk hindari cp1252 error →)
$env:PYTHONIOENCODING="utf-8"; python -X utf8 firmware\provision.py --help

# dry-run: generate NVS tanpa flash (hasil 2026-09-13: 24576 B, state persisted)
$env:PYTHONIOENCODING="utf-8"
python -X utf8 firmware\provision.py --port COM4 --ssid "FLAMBOYAN'S" --password "<YOUR_WIFI_PASSWORD>" --target-ip 192.168.1.75 --target-port 5005 --dry-run
# -> NVS binary saved to nvs_provision.bin (24576 bytes)
# -> Flash manually: python -m esptool --chip auto --port COM4 write_flash 0x9000 nvs_provision.bin
# -> State persisted to %APPDATA%\wifi-densepose\esp32-provision-state\COM4.json

# flash nyata (butuh COM4 tersedia, tanpa dry-run):
python -X utf8 firmware\provision.py --port COM4 --chip esp32s3 --ssid "FLAMBOYAN'S" --password "<YOUR_WIFI_PASSWORD>" --target-ip 192.168.1.75 --target-port 5005
# atau dengan TDM/ADR:
python -X utf8 firmware\provision.py --port COM4 --ssid "FLAMBOYAN'S" --password <YOUR_WIFI_PASSWORD> --target-ip 192.168.1.75 --target-port 5005 --tdm-slot 0 --tdm-total 1 --edge-tier 2 --channel 6

# atau via CSV manual (fallback §496 provision.py):
# nvs_config.csv -> nvs.bin 0x6000, lalu esptool write_flash 0x9000
```

Additive-by-default: state per-port di `%APPDATA%\wifi-densepose\esp32-provision-state\COM4.json` — re-invoke tanpa `--ssid` akan merge state lama (lihat provision.py:74-174).

## 5. Flash Command Valid untuk COM4 (4-file, preserve NVS)

> **Jangan flash otomatis** dalam lane ini — command di bawah untuk eksekusi manual saat COM4 tersedia & board dalam download mode.

```powershell
# 1) cek port & chip-id (harus MAC <YOUR_DEVICE_MAC>)
[System.IO.Ports.SerialPort]::getPortNames()
python -m esptool --chip esp32s3 --port COM4 chip-id
python -m esptool --chip esp32s3 --port COM4 flash-id   # expect 16MB detected

# 2) masuk download mode S3 Native USB CDC (HARDWARE.md §46-58):
#    Tahan BOOT terus -> tap RESET (<0.5s) -> lepas BOOT setelah 1s -> cek Device Manager -> USB JTAG/serial debug unit (COM4)

# 3) flash 4-file (recommended, preserve NVS di 0x9000)
python -m esptool --chip esp32s3 --port COM4 --baud 460800 write_flash `
  0x0000 firmware\bootloader.bin `
  0x8000 firmware\partition-table.bin `
  0xf000 firmware\ota_data_initial.bin `
  0x20000 firmware\esp32-csi-node.bin

# alternatif eksplisit 8MB (jika esptool detect 16MB tapi bundle 8MB):
python -m esptool --chip esp32s3 --port COM4 --baud 460800 --flash_size 8MB write_flash --flash_mode dio --flash_freq 80m `
  0x0000 firmware\bootloader.bin 0x8000 firmware\partition-table.bin 0xf000 firmware\ota_data_initial.bin 0x20000 firmware\esp32-csi-node.bin

# via script (wrapper di atas):
.\scripts\flash.ps1 -Port COM4
# jika COM4 hilang setelah reset CDC:
.\scripts\flash.ps1 -Port COM3 -Baud 115200

# Catatan: scripts/flash.ps1 default lama flash 0x10000 (3-file) — HARDWARE.md sudah diluruskan ke 4-file 0x20000 (lihat §6).
# Jangan pakai --flash_size 16MB manual — biarkan detect/8MB (READY.md:22, BUNDLE-16MB-LOG.md §1).
```

Offset valid: `0x0` bootloader, `0x8000` partition-table, `0xf000` ota_data_initial, `0x20000` app — sesuai READY.md §34-38 & BUNDLE-16MB-LOG.md §4/§7.

## 6. Monitor Command

```powershell
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
# atau
python -m serial.tools.miniterm COM4 115200 --raw
# exit miniterm: Ctrl+] lalu Ctrl+C
# fallback .NET SerialPort otomatis jika miniterm tidak ada (monitor.ps1:44-104)
```

## 7. Burn-in 5 Menit (Syarat READY.md:53)

> Validasi 5-menit tanpa parser/transport error sebelum kalibrasi.

1. Setelah flash, `monitor` harus keluar log boot **RuView 0.8.8** & stream `CSI_DATA` / `CSI` (bukan panic/error).
2. Jalankan monitor 5 menit penuh:
   ```powershell
   .\scripts\monitor.ps1 -Port COM4 -Baud 115200
   ```
   atau `miniterm` — biarkan 300 detik.
3. Kriteria lulus:
   - Tidak ada `error|fail|panic` merah (monitor.ps1 highlight).
   - Tidak ada transport error / parser error dari aggregator (`server_py` log).
   - CSI frame rate stabil (router 2.4GHz ch 1/6/11, BW 20MHz — HARDWARE.md §88-94).
4. Jika gagal: tekan RESET sekali, ulangi; jika tetap error → cek kabel data, `flash_id`, serta ulang flash 4-file dengan baud 115200.
5. Hanya setelah burn-in lulus → lanjut kalibrasi (ADR-039 threshold dll).

## 8. Git & Binary Policy

- `.gitignore` sudah ignore: `firmware/*.bin`, `firmware/*.zip`, `*.zip`, `esp32-csi-node-*.zip`, `_ruview/` — **jangan commit binary** (tugas §4: hanya docs/manifest).
- File lane ESP32 yang di-commit: `firmware/ESP32_VERIFY.md` (baru), `docs/HARDWARE.md` (koreksi flash offset), `firmware/READY.md`, `firmware/BUNDLE-16MB-LOG.md`, `nvs_config.csv`, `firmware/provision.py`, `scripts/*` (tanpa `.bin/.zip`).
- `git check-ignore -v firmware/bootloader.bin` → `.gitignore:74:firmware/*.bin` — expected.
- Tidak ada perubahan ke `server_py/` atau `web/ui/` (lane lain) — scope terpenuhi.

## 9. Perintah Rekomendasi Ringkas (copy-paste)

```powershell
# verify
Get-ChildItem firmware\*.bin | Format-Table Name, Length
Get-FileHash firmware\bootloader.bin -Algorithm SHA256
Get-Content firmware\READY.md
Get-Content nvs_config.csv
$env:PYTHONIOENCODING="utf-8"; python -X utf8 firmware\provision.py --help
$env:PYTHONIOENCODING="utf-8"; python -X utf8 firmware\provision.py --port COM4 --ssid "FLAMBOYAN'S" --password <YOUR_WIFI_PASSWORD> --target-ip 192.168.1.75 --target-port 5005 --dry-run

# flash manual (butuh download mode BOOT+RESET)
python -m esptool --chip esp32s3 --port COM4 --baud 460800 write_flash 0x0000 firmware\bootloader.bin 0x8000 firmware\partition-table.bin 0xf000 firmware\ota_data_initial.bin 0x20000 firmware\esp32-csi-node.bin

# provision setelah flash
python -X utf8 firmware\provision.py --port COM4 --ssid "FLAMBOYAN'S" --password <YOUR_WIFI_PASSWORD> --target-ip 192.168.1.75 --target-port 5005

# monitor + burn-in 5 menit
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
```

---
*Generated by @fixer 2026-09-13 — verify-only lane, no auto-flash, hashes matched, dry-run OK.*
