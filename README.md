# WiFiSense — Replikasi RuView (1x ESP32-S3 + Router Rumah)

Replikasi minimal sistem **RuView** untuk sensing berbasis **WiFi CSI (Channel State Information)** hanya dengan **1x ESP32-S3** dan **router WiFi 2.4GHz rumah**. Tanpa Docker, tanpa multi-node.

## Konsep RuView CSI

RuView memanfaatkan **CSI** — data layer fisik WiFi yang menggambarkan bagaimana sinyal terdistorsi oleh lingkungan (gerakan manusia, pernapasan, kehadiran). Berbeda dengan RSSI yang hanya 1 nilai kekuatan sinyal, CSI berisi amplitudo & fasa per subcarrier OFDM (mis. 52–256 subcarrier di 20MHz).

Alur RuView:

```
Router (AP 2.4GHz)  --~ ~ ~ WiFi ~ ~ ~-->  ESP32-S3 (STA / sniffer CSI)
                                            |
                                            | USB Serial / WiFi UDP
                                            v
                                    Laptop / Server (Python/Node)
                                            |
                                            v
                                    Preprocessing -> Model / Visualisasi
```

- **ESP32-S3** di-flash firmware CSI (contoh: `esp32-csi-node` dari RuView / esp-csi). Firmware mengaktifkan `wifi_csi` API Espressif, menangkap CSI dari paket yang diterima dari router, lalu mengirim via Serial atau UDP.
- **Router rumah** cukup sebagai AP biasa 2.4GHz (channel 1/6/11, bandwidth 20MHz lebih stabil). Tidak perlu OpenWrt.
- **Server Python/Node** di laptop menerima stream CSI, parsing, filtering, visualisasi / inference model.

> Varian RuView asli pakai 2 node (TX + RX) atau 1 node + AP. Setup 1x ESP32-S3 + router ini adalah mode paling murah untuk eksperimen awal.

## Requirement Hardware & Software

| Item | Detail |
|------|--------|
| **ESP32-S3 DevKitC-1 / N16R8 / WROOM** | 1x, USB Native (CDC). Pastikan chip **ESP32-S3**, bukan S2/C3 |
| **Router 2.4GHz** | AP rumah, SSID terlihat, WPA2, channel tetap (1/6/11), bandwidth 20MHz |
| **Kabel USB data** | USB-A/C ke ESP32-S3, support data (bukan charge-only) |
| **Laptop Windows** | PowerShell 5.1, Python 3.9+, Node.js 18+ opsional |
| **Driver** | CH340/CP210x jika board pakai UART bridge; native USB CDC tidak perlu driver di Win11 |

Software:

- Python `esptool`, `pyserial`, `numpy`, `huggingface_hub`
- `git` (untuk clone RuView)

> **Catatan:** Tidak butuh Docker. Semua jalan native di Windows.

## Struktur Project

```
WiFiSense/
├─ firmware/          # binary & source firmware ESP32-S3 CSI
├─ server/            # Node.js bridge (serial -> websocket/UDP)
├─ scripts/           # flash.ps1, monitor.ps1
├─ models/            # pretrained weights (placeholder)
├─ docs/
│  └─ HARDWARE.md     # pinout & download mode ESP32-S3
├─ _ruview/           # clone shallow RuView (jika internet ok)
├─ requirements.txt
├─ .gitignore
└─ README.md
```

## Langkah Flash (Windows)

### 1. Siapkan binary firmware

Opsi A — dari RuView (jika clone berhasil):

```
_ruview/firmware/esp32-csi-node/  -> build via ESP-IDF
atau ambil rilis: bootloader.bin, partition-table.bin, firmware.bin
```

Opsi B — placeholder `firmware/` sudah berisi instruksi. Download manual dari:
- https://github.com/ruvnet/RuView
- https://github.com/Steven063/ESP32-CSI-Tool

Letakkan 3 file di `firmware/`:
- `bootloader.bin` (offset 0x0000)
- `partition-table.bin` (offset 0x8000)
- `firmware.bin` / `esp32-csi-node.bin` (offset 0x10000)

> Jika hanya ada `merged.bin` / `firmware_merged.bin`, flash di 0x0 saja (lihat `scripts/flash.ps1`).

### 2. Masuk Download Mode (penting untuk ESP32-S3 Native USB)

ESP32-S3 pakai **USB CDC native**, bukan UART. Kadang port COM tidak muncul jika firmware crash.

Cara masuk download mode:

1. **Tahan tombol BOOT** (GPIO0) jangan dilepas
2. Tekan & lepas **RESET**
3. Lepas **BOOT**
4. Cek Device Manager -> Ports (COM & LPT) muncul `USB JTAG/serial debug unit (COMx)`

Lihat detail di `docs/HARDWARE.md`.

### 3. Flash via PowerShell

```powershell
# Edit port jika bukan COM3
.\scripts\flash.ps1 -Port COM3 -Baud 460800

# Jika hanya punya merged.bin
.\scripts\flash.ps1 -Port COM3 -Merged
```

Script menjalankan:

```
python -m esptool --chip esp32s3 --port COM3 --baud 460800 --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 firmware.bin
```

Jika gagal `Failed to connect`, ulangi langkah download mode + tahan BOOT.

### 4. Monitor CSI

```powershell
.\scripts\monitor.ps1 -Port COM3 -Baud 115200
# atau
python -m serial.tools.miniterm COM3 115200 --raw
```

Harus keluar log CSI seperti:

```
CSI_DATA, len=128, rssi=-42, channel=6, [12, -3, 45, ...]
```

Jika tidak keluar, cek baud (921600 / 115200) atau reset board.

## Cara Koneksi ke Router

1. Flash firmware yang support mode **STA** (station).
2. Edit SSID/PASS di firmware (via `menuconfig` atau `csi_config.h` / `wifi_config`):
   ```
   WIFI_SSID="NamaWiFiRumah"
   WIFI_PASS="password"
   ```
3. Atur router: 2.4GHz saja, channel **6** (2437MHz), bandwidth **20MHz**, WPA2.
4. Nyalakan ESP32-S3, cek log: harus `connected to AP, channel 6`.
5. Untuk trafik CSI, biarkan ESP32 ping router atau router kirim beacon. Gerakkan tangan di antara router dan ESP32, CSI amplitude harus berubah.
6. Server Python baca serial, parse CSI, simpan ke `.npy` / kirim via websocket.

Mode alternatif (sniffer, tanpa connect):
- Firmware set ke promiscuous, filter MAC router. Tidak perlu password, tapi butuh set channel manual via serial command.

## Troubleshooting

| Masalah | Solusi |
|---------|--------|
| `COM3` tidak ada | Ganti kabel data, coba USB lain, masuk download mode, install driver CH340/CP210x |
| `A fatal error occurred: Failed to connect` | Tahan BOOT saat flash, turunkan baud ke 115200, cabut-colok USB |
| CSI tidak keluar | Cek SSID/PASS, cek channel, coba baud 921600, cek firmware build `CONFIG_ESP_WIFI_CSI_ENABLED=y` |
| Port hilang setelah flash | Normal di S3 CDC, tekan RESET sekali, atau masuk download mode lagi |
| Router 5GHz tidak terdeteksi | ESP32-S3 hanya 2.4GHz |

## Next Step

- `server/` : bridge Serial -> WebSocket untuk visualisasi realtime
- `models/` : download pretrained RuView weights via `huggingface_hub`
- Eksperimen: kumpulkan CSI saat orang berjalan/duduk, latih classifier sederhana (RandomForest / CNN 1D)

## Referensi

- RuView: https://github.com/ruvnet/RuView
- ESP32 CSI Tool: https://github.com/Steven063/ESP32-CSI-Tool
- Espressif CSI docs: https://docs.espressif.com/projects/esp-idf/en/latest/api-guides/wifi.html#wi-fi-channel-state-information

## Lisensi

Mengikuti lisensi RuView (MIT/Apache-2.0). Project ini hanya scaffolding.
