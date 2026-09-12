# HARDWARE — ESP32-S3 untuk WiFiSense / RuView CSI

## Ringkasan Requirement

- **1x ESP32-S3 DevKitC-1** (ESP32-S3-WROOM-1 / N16R8 / N8R2, minimal 8MB flash)
- Router 2.4GHz rumah
- Kabel USB data + laptop Windows

> ESP32-S3 **wajib**. ESP32 lama, S2, C3 tidak support CSI yang sama atau tidak ada di RuView.

## Pinout ESP32-S3 DevKitC-1

```
            ┌─────────────────────┐
     3V3 ───┤ 3V3          GND ├─── GND
     5V  ───┤ 5V           3V3 ├─── 3V3
     GND ───┤ GND           48 ├─── GPIO48 (RGB LED)
     ...    │ ...            ... 
   BOOT ───┤ GPIO0  USB-C  EN  ├─── RESET / EN
            └─────────────────────┘
```

Pin penting:

| Pin | Fungsi | Catatan |
|-----|--------|---------|
| **GPIO0** | **BOOT** | Tahan LOW saat reset untuk download mode |
| **EN** | RESET / CHIP_PU | Tekan LOW untuk reset |
| **GPIO3** | JTAG / UART | Jangan pakai |
| **GPIO19/20** | USB D-/D+ | Native USB CDC JTAG |
| **GPIO48** | RGB LED | Indikator status (opsional) |
| **5V / 3V3 / GND** | Power | Jangan short |

Tidak perlu wiring tambahan untuk CSI — cukup USB.

## DevKit Varian

- **ESP32-S3-DevKitC-1**: 2 tombol (BOOT + RESET), USB-C native. Paling umum.
- **LilyGo / Waveshare S3**: pin sama, cek label BOOT/RESET.
- **Yang pakai CH340/CP2102**: muncul sebagai COM via UART bridge, bukan native. Tetap bisa, tapi baud/monitor beda.

## Cara Masuk Download Mode (WAJIB HAFAL)

ESP32-S3 pakai **USB native CDC**. Jika firmware crash / belum ada, port COM bisa hilang.

### Metode 1 — Tombol (paling aman)

1. **Tahan BOOT** (GPIO0) terus jangan lepas
2. **Tekan & lepas RESET** (EN) sekali (tap <0.5 detik)
3. **Lepas BOOT** setelah 1 detik
4. Cek Device Manager -> **Ports (COM & LPT)** -> muncul `USB JTAG/serial debug unit (COMx)` atau `USB Serial Device`

### Metode 2 — Cabut-Colok

1. Cabut USB
2. Tahan BOOT
3. Colok USB sambil tahan BOOT
4. Lepas BOOT setelah terdeteksi

### Verifikasi

```powershell
[System.IO.Ports.SerialPort]::getPortNames()
# atau
Get-PnpDevice -Class Ports -PresentOnly | Format-Table FriendlyName, InstanceId
```

Harus ada COM baru. Jika tidak:
- Ganti kabel (wajib kabel **data**, 4 pin, bukan charge-only 2 pin)
- Coba port USB 2.0 langsung (jangan hub)
- Install driver CH340/CP210x jika board pakai bridge
- Coba di laptop lain

## Flash & Monitor

Lihat `scripts/flash.ps1` dan `scripts/monitor.ps1`.

Ringkasan command manual:

```powershell
# flash 3-file
python -m esptool --chip esp32s3 --port COM3 --baud 460800 --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 firmware.bin

# monitor
python -m serial.tools.miniterm COM3 115200 --raw
```

## Tips Router 2.4GHz

- Kunci channel: **1 (2412MHz) / 6 (2437MHz) / 11 (2462MHz)**
- Bandwidth **20MHz** (bukan 40MHz) -> CSI lebih stabil
- WPA2-PSK, SSID tanpa spasi aneh
- Jarak ESP32 - router 1–5 meter, line-of-sight untuk tes awal
- Matikan band steering / smart connect yang memaksa 5GHz

## Foto & Referensi

- Espressif DevKitC-1 schematic: https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/index.html
- Pinout lengkap: https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/hw-reference/esp32s3/user-guide-devkitc-1.html

## Troubleshooting Hardware

| Gejala | Penyebab | Solusi |
|--------|----------|--------|
| LED tidak nyala | Power / kabel | Ganti kabel, coba 5V 1A |
| COM hilang setelah flash | CDC reset | Tekan RESET sekali, atau masuk download mode |
| `Failed to connect to ESP32-S3` | Belum download mode | Tahan BOOT + RESET, turunkan baud 115200 |
| Panas berlebih | Short / beban | Cabut, cek wiring, jangan hubung 5V ke 3V3 |
