# OPSI B — Download Firmware Prebuilt ESP32-S3 CSI (Fallback Manual)

> Status 2026-09-13: **Prebuilt ~2MB tidak tersedia via Releases.** Semua repo berikut **0 releases dengan asset**: `StevenMHernandez/ESP32-CSI-Tool`, `espressif/esp-csi`, `ruvnet/RuView` (assets 0). Instruksi lama `Steven063/ESP32-CSI-Tool` salah eja (404). Dokumen ini menjelaskan cara manual drag-drop jika binary didapat dari build lokal / teman / CI, plus cara build sendiri.

## 1. Kenapa Tidak Bisa Auto-Download

Task @fixer sudah coba urutan sesuai instruksi:

- `https://github.com/Steven063/ESP32-CSI-Tool/releases` → 404 (repo tidak ada)
- `https://api.github.com/repos/StevenMHernandez/ESP32-CSI-Tool/releases/latest` → 404 / `releases: []`
- `https://github.com/espressif/esp-csi/releases` → 0 releases
- `https://api.github.com/repos/ruvnet/RuView/releases` → 30 releases tapi `assets: 0` untuk semua tag

Verifikasi via `gh search repos "ESP32-CSI-Tool"` menemukan yang benar `StevenMHernandez/ESP32-CSI-Tool` (pushed 2024-07-16, has_releases null). Tidak ada `.bin` yang bisa `Invoke-WebRequest`.

Solusi: build dari source (ESP-IDF) atau minta binary dari yang sudah build.

## 2. Sumber Binary (jika ada di masa depan)

Simpan link ini, cek berkala — jika suatu hari publish release:

| Sumber | URL Releases | File yang dicari | Catatan |
|--------|--------------|------------------|---------|
| StevenMHernandez CSI Tool | https://github.com/StevenMHernandez/ESP32-CSI-Tool/releases | `*.bin` (~1–3 MB) | Butuh filter `esp32s3` |
| esp-csi Espressif | https://github.com/espressif/esp-csi/releases | `csi_recv_router.bin` etc | Biasanya tetap source only |
| RuView | https://github.com/ruvnet/RuView/releases | `esp32-csi-node.bin`, `merged.bin` | Sering tanpa asset, harus build |

Cara cek via PowerShell:

```powershell
$ProgressPreference='SilentlyContinue'
try { Invoke-RestMethod https://api.github.com/repos/StevenMHernandez/ESP32-CSI-Tool/releases/latest -TimeoutSec 15 | Select-Object tag_name, assets } catch { Write-Host "belum ada release" }
gh api repos/espressif/esp-csi/releases --jq "length"
gh search repos "ESP32-CSI-Tool" --limit 5
```

Jika suatu saat ada asset, download via:

```powershell
$ProgressPreference='SilentlyContinue'
# contoh jika ada release (pseudo — ganti URL asli saat tersedia)
Invoke-WebRequest -Uri "https://github.com/StevenMHernandez/ESP32-CSI-Tool/releases/download/vX.Y.Z/esp32s3-merged.bin" -OutFile "D:\AI\WiFiSense\firmware\merged.bin" -UseBasicParsing
Get-ChildItem D:\AI\WiFiSense\firmware\merged.bin | Format-Table Length
Get-FileHash D:\AI\WiFiSense\firmware\merged.bin -Algorithm SHA256
python -m esptool --chip esp32s3 image-info D:\AI\WiFiSense\firmware\merged.bin
```

## 3. Cara Manual: Drag-Drop ke firmware/merged.bin (saat ini — placeholder)

Karena belum ada prebuilt, folder `firmware/` sekarang berisi **placeholder 4 KB** (`SHA256 B158A2CB...`). Hapus dulu sebelum drop yang asli.

### Langkah

1. **Hapus placeholder:**
   ```powershell
   Remove-Item D:\AI\WiFiSense\firmware\merged.bin -Force -ErrorAction SilentlyContinue
   Get-ChildItem D:\AI\WiFiSense\firmware\ | Format-Table Name, Length
   ```

2. **Dapatkan binary asli** (pilih satu):
   - **Build sendiri (recommended):** lihat §5 di bawah — hasil `idf.py build` menghasilkan `build/*.bin` dan `merged.bin`.
   - **Dari teman/CI:** minta file `merged.bin` (≈1.5–3.5 MB, chip esp32s3, 16MB flash). Pastikan berasal dari `set-target esp32s3`.
   - **Dari Releases masa depan:** download seperti §2.

3. **Drag-drop via Explorer:**
   - Buka Explorer → `D:\AI\WiFiSense\firmware\`
   - Drag file `merged.bin` asli ke folder ini (atau copy):
     ```powershell
     Copy-Item -Path "C:\Users\YourName\Downloads\merged.bin" -Destination "D:\AI\WiFiSense\firmware\merged.bin" -Force
     # atau jika punya 3 file terpisah:
     Copy-Item build\bootloader\bootloader.bin D:\AI\WiFiSense\firmware\ -Force
     Copy-Item build\partition_table\partition-table.bin D:\AI\WiFiSense\firmware\ -Force
     Copy-Item build\esp32-csi-node.bin D:\AI\WiFiSense\firmware\firmware.bin -Force
     ```

4. **Verifikasi file:**
   ```powershell
   Get-ChildItem D:\AI\WiFiSense\firmware\*.bin | Format-Table Name, Length, LastWriteTime -AutoSize
   Get-FileHash D:\AI\WiFiSense\firmware\merged.bin -Algorithm SHA256 | Format-List
   python -m esptool --chip esp32s3 image-info D:\AI\WiFiSense\firmware\merged.bin
   # EXPECTED: Image size: ~1500000..3500000 bytes, chip esp32s3, segments 3-5, entry 0x4037xxxx, NO "Unexpected chip ID"
   # Jika masih 4096 B atau error chip ID → masih placeholder / salah chip (S2 vs S3)

   # Alternatif check merged vs 3-file:
   python -m esptool --chip esp32s3 --port COM4 flash-id   # optional, cek flash size detect 16MB
   ```

5. **Update READY.md:**
   ```powershell
   # Edit D:\AI\WiFiSense\firmware\READY.md → ubah Status NOT READY → READY, isi size + hash baru
   ```

## 4. Cara Flash Setelah File Valid

**Jangan flash placeholder!** Hanya setelah verifikasi §3 point 4 lolos.

```powershell
# 1. Cek port (COM4 biasa, bisa pindah COM3 setelah hard reset)
[System.IO.Ports.SerialPort]::getPortNames()
Get-CimInstance Win32_SerialPort | Format-List DeviceID,Description,PNPDeviceID
# Harus keluar COM4 USB Serial Device VID_303A PID_1001

# 2. Verifikasi chip (MAC ekspektasi <YOUR_DEVICE_MAC>)
python -m esptool --chip esp32s3 --port COM4 chip-id
# Expected: Chip ESP32-S3 QFN56 rev0.2 8MB PSRAM MAC <YOUR_DEVICE_MAC>

# 3. Flash merged (single file 0x0)
.\scripts\flash.ps1 -Port COM4 -Merged -Baud 460800
# Jika "Failed to connect / Connecting...":
# - Tahan BOOT (GPIO0) → tap RESET → lepas BOOT (masuk Download Mode, PID 1001)
# - Coba baud rendah:
.\scripts\flash.ps1 -Port COM4 -Merged -Baud 115200
# - Coba COM3 jika COM4 hilang setelah reset:
[System.IO.Ports.SerialPort]::getPortNames(); .\scripts\flash.ps1 -Port COM3 -Merged

# 4. Monitor CSI
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
# atau
python -m serial.tools.miniterm COM4 115200 --raw
# Expected log: "connected to ap SSID:FLAMBOYAN'S" + "CSI_DATA len=128 rssi=..."
```

Untuk 3-file mode (jika punya bootloader + partition + firmware terpisah):

```powershell
.\scripts\flash.ps1 -Port COM4 -Baud 460800
# atau manual:
python -m esptool --chip esp32s3 --port COM4 --baud 460800 --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect 0x0 firmware\bootloader.bin 0x8000 firmware\partition-table.bin 0x10000 firmware\firmware.bin
```

## 5. Build Sendiri Jika Tidak Ada Prebuilt (Opsi A — 30–60 menit)

Karena prebuilt tidak ada, ini jalur yang pasti jalan. Ringkas dari `docs/PLAN-OPSI-A.md`:

### 5a. Pakai source esp-csi yang sudah ter-cache (24 MB)

Repo sudah di-download ke `firmware/esp-csi-master.zip` dan extract di `firmware/esp-csi-tmp/esp-csi-master`. Cocok untuk S3:

```powershell
cd D:\AI\WiFiSense\firmware\esp-csi-tmp\esp-csi-master\examples\get-started\csi_recv_router
# butuh ESP-IDF 5.4 di C:\Espressif
C:\Espressif\esp-idf\v5.4\export.ps1
idf.py set-target esp32s3
idf.py menuconfig  # enable CONFIG_ESP_WIFI_CSI_ENABLED + SSID FLAMBOYAN'S / <YOUR_WIFI_PASSWORD> (kutip ganda!)
idf.py build
# hasil: build/bootloader/bootloader.bin, build/partition_table/partition-table.bin, build/csi_recv_router.bin
Copy-Item build\bootloader\bootloader.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\partition_table\partition-table.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\csi_recv_router.bin D:\AI\WiFiSense\firmware\firmware.bin -Force
# buat merged sendiri:
python -m esptool --chip esp32s3 merge_bin --fill-flash-size 4MB -o D:\AI\WiFiSense\firmware\merged.bin --flash_mode dio --flash_freq 80m --flash_size 16MB 0x0 build\bootloader\bootloader.bin 0x8000 build\partition_table\partition-table.bin 0x10000 build\csi_recv_router.bin
```

### 5b. Pakai RuView (lebih lengkap, ada console_test + webSerial)

```powershell
cd D:\AI\WiFiSense
git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview
cd _ruview/firmware/esp32-csi-node
C:\Espressif\esp-idf\v5.4\export.ps1
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
Copy-Item build\bootloader\bootloader.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\partition_table\partition-table.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\*.bin D:\AI\WiFiSense\firmware\ -Force
```

Lihat detail troubleshooting di `docs/PLAN-OPSI-A.md` (§6 Troubleshooting: path tanpa spasi, disable antivirus, Python 3.11, C: free 10GB).

### 5c. SSID FLAMBOYAN'S

SSID mengandung `'`. Di PowerShell, `menuconfig`, dan `sdkconfig` wajib literal `FLAMBOYAN'S` dalam kutip ganda. Di `Select-String` / `sdkconfig` akan muncul `CONFIG_WIFI_SSID="FLAMBOYAN'S"`.

```powershell
# cara cek setelah menuconfig:
Select-String -Path sdkconfig -Pattern "WIFI_SSID|CSI_ENABLED"
# harus: CONFIG_ESP_WIFI_CSI_ENABLED=y
```

## 6. FAQ

**Q: Kenapa merged.bin saya 4 KB?**  
A: Itulah placeholder @fixer. Hapus, ganti dengan binary asli >1 MB.

**Q: esptool image_info error "Unexpected chip ID"?**  
A: File masih placeholder atau untuk chip lain (S2/C3). Build ulang dengan `idf.py set-target esp32s3`.

**Q: COM4 hilang jadi COM3 setelah hard_reset?**  
A: Normal untuk ESP32-S3 native USB. Cek `getPortNames()` lagi, ganti argumen `-Port COM3`.

**Q: Flash butuh 16MB flash_size, tapi esptool detect 4MB?**  
A: Board ini 16MB fisik, tapi `flash_size detect` kadang 4MB jika salah mode. Force `--flash_size 16MB` saat `merge_bin` / `write_flash` tidak masalah; firmware tetap jalan jika partition.csv sesuai.

**Q: Bisa pakai Arduino IDE tanpa ESP-IDF 5GB?**  
A: Bisa untuk test Blink, tapi CSI butuh ESP-IDF `CONFIG_ESP_WIFI_CSI_ENABLED`. Arduino core belum expose CSI stabil — tetap butuh IDF.

## 7. Checklist Sebelum Tanya "Kok Gagal?"

- [ ] `firmware/merged.bin` >1 MB & `image-info` clean?
- [ ] Port COM4/COM3 terdeteksi VID 303A PID 1001?
- [ ] `chip-id` MAC <YOUR_DEVICE_MAC>?
- [ ] Build dengan `esp32s3` bukan `esp32`?
- [ ] SSID `FLAMBOYAN'S` pakai kutip ganda?

---
*Cache source: `firmware/esp-csi-master.zip` SHA256 D3EBAB4ED32D9A28AB04B7A719B2EAB303BCE311471D518583667BF6E5C9B903 (24 MB) — sudah siap untuk §5a tanpa download ulang.*
