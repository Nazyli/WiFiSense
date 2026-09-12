# READY — Status Firmware ESP32-S3 COM4

> Update: 2026-09-13 01:23 WIB — oleh @fixer

## Status: 🔴 NOT READY — Placeholder, jangan flash

**Alasan:** Tidak ada prebuilt `merged.bin` valid ditemukan. File `firmware/merged.bin` saat ini adalah **placeholder 4 KB** dengan SHA256 `B158A2CB71ECC0B64D3AC806012F5C6D304D4CC02A4B3267291B72C25B564686`. `esptool image_info` gagal dengan `Unexpected chip ID` (expected `Invalid image header`) — konfirmasi file bukan firmware ESP32-S3 asli.

Flash placeholder akan gagal / brick soft — **jangan jalankan `.\scripts\flash.ps1 -Port COM4 -Merged` sebelum file diganti dengan binary asli**.

## Verifikasi Hardware ✅

- **Port aktif:** COM4 terdeteksi (`[System.IO.Ports.SerialPort]::getPortNames() → COM4`, `Get-CimInstance Win32_SerialPort → USB\VID_303A&PID_1001&MI_00\6&5CD5794&0&0000`)
- **Chip:** ESP32-S3 QFN56 rev0.2 Dual Core + LP Core 240MHz, Embedded PSRAM 8MB (AP_3v3), Crystal 40MHz, USB-Serial/JTAG
- **MAC:** <YOUR_DEVICE_MAC> — cocok dengan ekspektasi instruksi
- **Flash:** 16MB (detect via `esptool --flash_size detect`)
- **Koneksi:** `python -m esptool --chip esp32s3 --port COM4 chip-id` → SUCCESS (Connected, Stub running, MAC verified, Hard resetting via RTS)
- **SSID target:** `FLAMBOYAN'S` / `<YOUR_WIFI_PASSWORD>` — dicatat untuk `menuconfig` nanti (pakai kutip ganda PowerShell `"FLAMBOYAN'S"`)

> Catatan COM port: setelah hard reset, ESP32-S3 native USB bisa pindah ke COM3. Jika `COM4` hilang, cek ulang:
> ```powershell
> [System.IO.Ports.SerialPort]::getPortNames()
> Get-CimInstance Win32_SerialPort | Format-List DeviceID, Description, PNPDeviceID
> python -m esptool --chip esp32s3 --port COM3 chip-id
> ```

## Isi firmware/ Saat Ini

```
D:\AI\WiFiSense\firmware\
  README.md            — instruksi flash & opsi A/B/C
  esp-csi-master.zip   25,026,658 B  SHA256 D3EBAB4ED32D9A28AB04B7A719B2EAB303BCE311471D518583667BF6E5C9B903 (source cache)
  esp-csi-tmp/         extracted source espressif/esp-csi master
  merged.bin           4,096 B  SHA256 B158A2CB71ECC0B64D3AC806012F5C6D304D4CC02A4B3267291B72C25B564686  ← PLACEHOLDER, NOT FLASHABLE
  DOWNLOAD_LOG.md      log lengkap upaya download Opsi B
  READY.md             (file ini)
```

`Get-ChildItem firmware\ | Format-Table Name, Length, LastWriteTime` menunjukkan placeholder 4KB — bukan ~2MB yang dijanjikan Opsi B prebuilt.

## Apa yang Belum Siap

- [ ] `bootloader.bin` (0x0) — belum ada
- [ ] `partition-table.bin` (0x8000) — belum ada
- [ ] `firmware.bin` / `esp32-csi-node.bin` (0x10000) — belum ada
- [x] `merged.bin` — ada tapi placeholder saja (harus diganti)
- [x] CSI config SSID `FLAMBOYAN'S` — belum baked (butuh `idf.py menuconfig`)

## Cara Menjadi READY ✅ (pilih satu)

### Opsi A — Build RuView / esp-csi via ESP-IDF (recommended, 30–60 menit)

Ikuti `docs/PLAN-OPSI-A.md`:

```powershell
# Install ESP-IDF 5.4 ke C:\Espressif (tanpa spasi), lalu:
cd D:\AI\WiFiSense
git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview   # jika belum
cd _ruview/firmware/esp32-csi-node
C:\Espressif\esp-idf\v5.4\export.ps1
idf.py set-target esp32s3
idf.py menuconfig   # enable CONFIG_ESP_WIFI_CSI_ENABLED + SSID FLAMBOYAN'S / <YOUR_WIFI_PASSWORD>
idf.py build
Copy-Item build\bootloader\bootloader.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\partition_table\partition-table.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\esp32-csi-node.bin D:\AI\WiFiSense\firmware\firmware.bin -Force
# atau jika ada merged:
Copy-Item build\*.merged.bin D:\AI\WiFiSense\firmware\merged.bin -Force
Get-ChildItem D:\AI\WiFiSense\firmware\*.bin | Format-Table Name, Length
python -m esptool --chip esp32s3 image-info D:\AI\WiFiSense\firmware\merged.bin
```

Alternatif pakai source yang sudah ter-cache:

```powershell
cd D:\AI\WiFiSense\firmware\esp-csi-tmp\esp-csi-master\examples\get-started\csi_recv_router
idf.py set-target esp32s3; idf.py build
```

### Opsi B manual — Drag-Drop Binary

Jika teman / CI sudah punya `merged.bin` jadi (~1.5–3 MB, header 0xE9 valid):

1. Hapus placeholder: `Remove-Item D:\AI\WiFiSense\firmware\merged.bin -Force`
2. Copy binary asli ke `D:\AI\WiFiSense\firmware\merged.bin` (drag-drop via Explorer atau `Copy-Item C:\Downloads\merged.bin D:\AI\WiFiSense\firmware\`)
3. Verifikasi:
   ```powershell
   Get-ChildItem D:\AI\WiFiSense\firmware\merged.bin | Format-Table Length
   Get-FileHash D:\AI\WiFiSense\firmware\merged.bin -Algorithm SHA256
   python -m esptool --chip esp32s3 image-info D:\AI\WiFiSense\firmware\merged.bin
   # harus keluar: Image size >1MB, chip esp32s3, segment count >=3, tanpa "Unexpected chip ID"
   ```
4. Flash (baru boleh!):
   ```powershell
   [System.IO.Ports.SerialPort]::getPortNames()  # pastikan COM4 masih ada
   .\scripts\flash.ps1 -Port COM4 -Merged -Baud 460800
   # jika Failed to connect: tahan BOOT, tap RESET, lepas BOOT, ulang flash
   # alternatif baud rendah:
   .\scripts\flash.ps1 -Port COM4 -Merged -Baud 115200
   ```

Lihat detail lengkap di `docs/OPSI-B-DOWNLOAD.md`.

## Validasi Sebelum Flash (checklist)

- [ ] `merged.bin` size > 1 MB (bukan 4096 B)
- [ ] `image-info` tanpa error chip ID
- [ ] Port COM4 terdeteksi (atau COM3 setelah reset)
- [ ] `chip-id` MAC masih <YOUR_DEVICE_MAC>

## Log Image Info Placeholder (expected fail)

```
esptool v5.4.0
Image size: 4096 bytes
WARNING: Unexpected chip ID in image. Expected 9 but value was 30240. Is this image for a different chip model?
Traceback ... (image header invalid — placeholder)
```

Ini bukti file bukan firmware valid.

---
*Jika READY ✅, file ini akan diupdate menjadi `## Status: 🟢 READY — merged.bin valid, siap flash` dengan size + hash baru.*
