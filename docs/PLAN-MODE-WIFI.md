# PLAN MODE WiFi — STA vs Sniffer untuk FLAMBOYAN'S (Opsi A & B)

> **Tujuan:** Coba 2 mode WiFi capture CSI untuk SSID `FLAMBOYAN'S` (2.4GHz) — berlaku untuk **Opsi A (RuView esp32-csi-node)** maupun **Opsi B (ESP32-CSI-Tool)**. Rekomendasi urutan coba & cara ganti mode.

## 1. Konteks SSID FLAMBOYAN'S

- **SSID:** `FLAMBOYAN'S` (ada apostrophe `'`)
- **Password:** `<YOUR_WIFI_PASSWORD>`
- **Band:** 2.4GHz only (ESP32-S3 tidak support 5GHz)
- **Channel:** ideal **6 (2437MHz)**, cek di router admin page. Jika auto, catat channel saat test.
- **Security:** WPA2-PSK (WPA3 kadang tidak kompatibel dengan firmware lama)

> **PowerShell Escape WAJIB:** SSID ada `'`, jadi selalu pakai **kutip ganda** `"FLAMBOYAN'S"`. Kutip tunggal `'FLAMBOYAN'S'` akan error parsing di PowerShell.

```powershell
# BENAR — kutip ganda:
$ssid = "FLAMBOYAN'S"
$pass = "<YOUR_WIFI_PASSWORD>"
python -m esptool --port COM4 --ssid "FLAMBOYAN'S" --password <YOUR_WIFI_PASSWORD>
idf.py menuconfig  # isi SSID dengan FLAMBOYAN'S langsung

# SALAH — kutip tunggal pecah:
# $ssid = 'FLAMBOYAN'S'  -> PowerShell parse error!

# Jika butuh escape dalam string single-quote (jarang):
$ssid2 = 'FLAMBOYAN''S'  # double '' untuk escape, tapi lebih ribet — pakai " saja

# Cek SSID via netsh (Windows):
netsh wlan show networks | Select-String -Pattern "FLAMBOYAN"
# atau
netsh wlan show interfaces
```

Link firmware:
- **Opsi B (binary jadi, tanpa build):** https://github.com/Steven063/ESP32-CSI-Tool/releases
- **Opsi A (source build):** https://github.com/ruvnet/RuView/tree/main/firmware/esp32-csi-node

---

## 2. Mode 1 — STA (Station Connect) ⭐ Recommended Pertama

### Konsep
ESP32 mode **station** connect ke AP `FLAMBOYAN'S` seperti HP/laptop. Setelah connect, firmware enable `wifi_csi` API Espressif dan capture CSI dari paket AP (beacon, data, ack). Channel **auto follow** AP (mis AP channel 6 -> ESP32 ikut 6).

### Diagram

```
[Router FLAMBOYAN'S]  --(WiFi 2.4GHz, ch 6, WPA2)-->  [ESP32-S3 STA]
      |                                                    |
      |  beacon/data setiap ~100ms                         | CSI callback
      |                                                    v
      +------------------------------------------>  Serial/USB -> Laptop (COM4)
```

### Kelebihan
- ✅ **Stabil** — channel auto, tidak perlu set manual
- ✅ Tidak miss paket — sudah associate, dapat data frame + beacon
- ✅ Bisa ping / iperf untuk generate trafik CSI terus-menerus
- ✅ RSSI & CSI lebih konsisten untuk ML

### Kekurangan
- ❌ **Butuh password** (`<YOUR_WIFI_PASSWORD>`) — jika salah, tidak connect
- ❌ Jika AP ganti channel (auto channel hopping), harus **reconnect** (tapi modern firmware auto reconnect)
- ❌ Jika AP hidden / MAC filter, perlu konfigurasi tambahan
- ❌ Satu ESP32 hanya bisa connect ke 1 AP

### Langkah Mode STA (Windows, COM4)

#### A. Jika pakai Opsi A (RuView build)

```powershell
# 1. Set SSID/PASS via menuconfig (sekali saja)
cd D:\AI\WiFiSense\_ruview\firmware\esp32-csi-node
C:\Espressif\esp-idf\v5.4\export.ps1
idf.py menuconfig
# -> isi: SSID="FLAMBOYAN'S", PASS=<YOUR_WIFI_PASSWORD>, Channel=0 (auto)

# 2. Build & flash
idf.py build
idf.py -p COM4 flash monitor
# atau
Copy-Item build\bootloader\bootloader.bin ..\..\..\firmware\ -Force
Copy-Item build\partition_table\partition-table.bin ..\..\..\firmware\ -Force
Copy-Item build\esp32-csi-node.bin ..\..\..\firmware\firmware.bin -Force
.\scripts\flash.ps1 -Port COM4 -Baud 460800
```

#### B. Jika pakai Opsi B (ESP32-CSI-Tool binary)

```powershell
# Download dari https://github.com/Steven063/ESP32-CSI-Tool/releases
# Mis file: ESP32_CSI_Tool_STA.bin atau merged.bin

# Flash (sesuaikan nama file)
.\scripts\flash.ps1 -Port COM4 -Baud 460800
# atau manual:
python -m esptool --chip esp32s3 --port COM4 --baud 460800 --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect 0x0 firmware\bootloader.bin 0x8000 firmware\partition-table.bin 0x10000 firmware\firmware.bin

# Provision SSID (jika firmware support serial command)
python -m serial.tools.miniterm COM4 115200 --raw
# Di console ketik (jika ada CLI):
# > sta_config "FLAMBOYAN'S" <YOUR_WIFI_PASSWORD>
# > sta_connect
# > csi_start
```

#### C. Verifikasi STA Connect

```powershell
# Monitor log
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
# atau
idf.py -p COM4 monitor
# atau
python -m serial.tools.miniterm COM4 115200 --raw
```

Log yang diharapkan:

```
I (1234) wifi: connected to ap SSID:FLAMBOYAN'S
I (1234) wifi: channel 6, bssid=aa:bb:cc:dd:ee:ff, rssi=-42
I (1235) wifi: CSI enabled
CSI_DATA, len=128, rssi=-42, channel=6, [12, -3, 45, ...]
```

Test tambahan:

```powershell
# Ping test (dari laptop ke ESP32 jika dapat IP)
# Cek IP ESP32 di log: "got ip:192.168.1.xxx"
ping 192.168.1.xxx -t

# Atau ping dari ESP32 ke router (jika firmware ada command):
# > ping 192.168.1.1

# Generate trafik: biarkan ping jalan, CSI akan keluar terus
# Gerakkan tangan antara router dan ESP32, amplitude CSI harus berubah
```

Jika **tidak connect**:

- Cek password `<YOUR_WIFI_PASSWORD>` benar (case-sensitive)
- Cek router 2.4GHz aktif, bukan 5GHz only, WPA2 (bukan WPA3 only)
- Cek channel router (kunci ke 6, bandwidth 20MHz)
- Cek jarak 1–5m, jangan terlalu jauh
- Coba `idf.py menuconfig` cek SSID tidak typo (ingat `"FLAMBOYAN'S"`)

---

## 3. Mode 2 — Sniffer / Promiscuous (Tanpa Password)

### Konsep
ESP32 **tidak connect** ke AP. Mode promiscuous / sniffer menangkap semua paket WiFi di udara, filter berdasarkan **MAC BSSID** router `FLAMBOYAN'S`. Tidak butuh password, tapi **harus set channel manual** (mis 6) via serial.

### Diagram

```
[Router FLAMBOYAN'S ch6] --beacon/probe-->  (( udara ))
                                                |
[ESP32-S3 Sniffer ch6, promiscuous]  <----------+  filter MAC aa:bb:cc:dd:ee:ff
      | CSI dari beacon yang sniff
      v
Serial -> Laptop
```

### Kelebihan
- ✅ **Tidak butuh password** — bisa sniff AP mana saja
- ✅ Bisa sniff banyak AP / tetangga sekaligus (untuk eksperimen)
- ✅ Tidak membebani AP (tidak associate)
- ✅ Cocok untuk riset pasif

### Kekurangan
- ❌ **Harus set channel manual** via serial — jika AP ganti channel (auto), akan miss
- ❌ Hanya dapat **beacon/probe** (~10 paket/detik), bukan data frame — CSI lebih jarang
- ❌ Perlu tahu **MAC BSSID** AP (bisa berubah jika router ganti)
- ❌ Kurang stabil untuk ML yang butuh sample rate tinggi
- ❌ Filter MAC harus di-set via code atau serial command

### Langkah Mode Sniffer (Windows, COM4)

#### A. Flash Firmware Sniffer

```powershell
# Opsi A: build RuView dengan config sniffer
cd D:\AI\WiFiSense\_ruview\firmware\esp32-csi-node
idf.py menuconfig
# -> RuView Config -> Mode = Sniffer / Promiscuous
# -> Enable promiscuous, disable STA
idf.py build; idf.py -p COM4 flash

# Opsi B: download binary sniffer dari ESP32-CSI-Tool
# https://github.com/Steven063/ESP32-CSI-Tool/releases
# Cari file: *_sniffer.bin atau *_promiscuous.bin
.\scripts\flash.ps1 -Port COM4 -Baud 460800
```

#### B. Cari MAC BSSID FLAMBOYAN'S

```powershell
# Dari Windows (laptop connect ke FLAMBOYAN'S dulu):
netsh wlan show networks mode=bssid | Select-String -Pattern "FLAMBOYAN|BSSID|Channel" -Context 0,3

# Contoh output:
# SSID 1 : FLAMBOYAN'S
#     BSSID 1 : aa:bb:cc:dd:ee:ff
#     Channel : 6

# Alternatif: dari router admin page (192.168.1.1) lihat Wireless Status -> BSSID
# Catat MAC: mis aa:bb:cc:dd:ee:ff dan channel 6
```

#### C. Set Filter MAC & Channel via Serial

```powershell
python -m serial.tools.miniterm COM4 115200 --raw
# Di console ESP32 ketik (perintah tergantung firmware, contoh):

# ESP32-CSI-Tool style:
# > filter_set aa:bb:cc:dd:ee:ff
# > channel_set 6
# > csi_start

# RuView style (jika ada CLI):
# > csi_config --mode sniffer --bssid aa:bb:cc:dd:ee:ff --channel 6
# > csi_start

# Jika tidak ada CLI, edit source sebelum build:
# main/app_main.c:
# #define FILTER_BSSID "aa:bb:cc:dd:ee:ff"
# #define WIFI_CHANNEL 6
# lalu rebuild
```

Verifikasi:

```powershell
# Monitor
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
# Harus keluar:
# I (xxx) sniffer: channel 6, filter aa:bb:cc:dd:ee:ff
# CSI_DATA, len=128, rssi=-50, channel=6, [ ... ]  # dari beacon
```

#### D. Jika AP Auto Channel Hopping

- Kunci channel router ke **6** di admin page (Wireless -> Channel -> Fixed 6, bukan Auto)
- Atau buat script auto hop (advanced):

```powershell
# Loop channel 1,6,11 via serial (jika firmware support)
for ($ch=1; $ch -le 11; $ch++) {
  Write-Host "Set channel $ch"
  # kirim via serial: channel_set $ch
  Start-Sleep -Seconds 5
}
```

---

## 4. Tabel Perbandingan

| Aspek | Mode 1 STA (Connect) | Mode 2 Sniffer (Promiscuous) |
|-------|----------------------|------------------------------|
| **Butuh password** | Ya (`<YOUR_WIFI_PASSWORD>`) | Tidak |
| **Channel** | Auto follow AP | Manual set (6) |
| **Stabilitas** | Tinggi (associate) | Sedang (beacon only) |
| **Sample rate CSI** | Tinggi (data + beacon, 50–100Hz jika ping) | Rendah (beacon ~10Hz) |
| **Kalau AP ganti channel** | Auto reconnect (jika firmware bagus) | Miss, harus set manual lagi |
| **Filter** | Otomatis (sudah connect) | Manual MAC BSSID |
| **Cocok untuk** | Training ML, sensing stabil, demo | Eksperimen pasif, sniff tetangga, tanpa password |
| **Kelebihan utama** | Stabil, tidak miss, channel auto | Tanpa password, multi-AP |
| **Kekurangan utama** | Butuh password, 1 AP saja | Channel manual, sample jarang |
| **Firmware Opsi A** | `menuconfig` STA SSID/PASS | `menuconfig` Sniffer + BSSID |
| **Firmware Opsi B** | `*_sta.bin` | `*_sniffer.bin` |

---

## 5. Rekomendasi Urutan Coba

### Urutan Recommended (karena password sudah ada)

```
1. Coba STA dulu (15 menit)
   |
   +-- Sukses? -> lanjut capture CSI, kumpulkan dataset, training
   |
   +-- Gagal connect? -> cek password, channel, WPA2, jarak
         |
         2. Coba Sniffer (10 menit)
            |
            +-- Sukses? -> capture beacon CSI, bandingkan kualitas vs STA
            |
            +-- Gagal juga? -> cek MAC, channel, firmware CSI enabled
                  |
                  3. Fallback: ganti router / cek hardware (kabel, COM4, download mode)
```

**Kenapa STA dulu?**
- Password `<YOUR_WIFI_PASSWORD>` sudah diketahui — tidak ada alasan pakai sniffer dulu
- STA lebih stabil untuk dataset awal
- Sniffer bagus untuk **eksperimen kedua** (bandingkan, atau kalau mau sniff tanpa ganggu AP)

**Kapan pakai Sniffer?**
- Mau coba tanpa ganggu koneksi AP (pasif)
- Mau bandingkan CSI STA vs beacon
- Mau sniff AP tetangga / riset multi-AP
- Password STA ternyata salah / AP pakai WPA3 yang tidak support

---

## 6. Cara Ganti Mode (Re-flash atau Serial Command)

### Metode 1 — Re-flash (paling bersih)

```powershell
# Ganti mode = flash firmware berbeda

# STA -> Sniffer:
.\scripts\flash.ps1 -Port COM4 -Baud 460800  # dengan file sniffer.bin
# atau
idf.py -p COM4 flash  # setelah menuconfig ganti ke Sniffer + rebuild

# Sniffer -> STA:
idf.py menuconfig  # ganti ke STA, isi "FLAMBOYAN'S"/<YOUR_WIFI_PASSWORD>
idf.py build; idf.py -p COM4 flash

# Cek mode saat ini di log boot:
# "Mode: STA" atau "Mode: Sniffer promiscuous"
```

### Metode 2 — Serial Command (tanpa re-flash, jika firmware support dual-mode)

```powershell
python -m serial.tools.miniterm COM4 115200 --raw

# Contoh CLI dual-mode (cek docs firmware):
# > mode sta "FLAMBOYAN'S" <YOUR_WIFI_PASSWORD>
# > mode sniffer aa:bb:cc:dd:ee:ff 6
# > save
# > reset

# ESP32-CSI-Tool sering punya command:
# > csi_mode 0  # 0=STA, 1=Sniffer
# > channel 6
# > bssid aa:bb:cc:dd:ee:ff
# > restart
```

> **Catatan:** Tidak semua firmware support ganti mode via serial. RuView `esp32-csi-node` umumnya **harus rebuild** untuk ganti mode. ESP32-CSI-Tool ada yang support CLI. Jika ragu, **re-flash saja** (2 menit).

### Cek Mode Aktif

```powershell
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
# Lihat baris awal boot:
# I (xxx) wifi: mode STA, ssid FLAMBOYAN'S, channel 6
# atau
# I (xxx) wifi: mode SNIFFER, channel 6, filter aa:bb:cc:dd:ee:ff
```

---

## 7. Checklist Coba Kedua Mode

### Persiapan Umum
- [ ] Catat BSSID `FLAMBOYAN'S`: `aa:bb:cc:dd:ee:ff` (via `netsh wlan show networks mode=bssid`)
- [ ] Catat channel: `6` (cek router admin page, kunci ke 6, 20MHz)
- [ ] Pastikan ESP32-S3 di COM4 (`[System.IO.Ports.SerialPort]::getPortNames()`)
- [ ] Siapkan 2 firmware: STA dan Sniffer (atau 1 firmware dual-mode)

### Test STA
- [ ] Flash STA dengan `"FLAMBOYAN'S"` / `<YOUR_WIFI_PASSWORD>` (pakai kutip ganda!)
- [ ] Monitor log -> `connected, channel 6, CSI enabled`
- [ ] Ping test -> `ping <IP_ESP32> -t` atau `ping 192.168.1.1` dari ESP32
- [ ] Capture CSI 1 menit, gerakkan tangan, cek amplitude berubah
- [ ] Simpan log ke file: `python -m serial.tools.miniterm COM4 115200 --raw --logfile sta_csi.log`

### Test Sniffer
- [ ] Flash Sniffer
- [ ] Set `filter aa:bb:cc:dd:ee:ff` + `channel 6` via serial
- [ ] Monitor -> CSI dari beacon muncul (~10Hz)
- [ ] Jika tidak muncul: cek channel benar? BSSID benar? AP beacon aktif?
- [ ] Bandingkan kualitas CSI STA vs Sniffer (STA biasanya lebih rapat)

### Ganti Mode
- [ ] Coba re-flash STA -> Sniffer -> STA lagi (latihan ganti cepat)
- [ ] Coba serial command jika firmware support (tanpa re-flash)
- [ ] Dokumentasikan mode mana yang paling stabil untuk dataset

---

## 8. Troubleshooting Mode WiFi

| Masalah | Mode | Solusi |
|---------|------|--------|
| `auth failed` / `wrong password` | STA | Cek `<YOUR_WIFI_PASSWORD>` lower-case, tanpa spasi. Coba connect HP dulu ke `FLAMBOYAN'S` untuk verifikasi. |
| `connected but no CSI` | STA | Cek `CONFIG_ESP_WIFI_CSI_ENABLED=y` di build. Cek baud 115200/921600. Generate trafik pakai `ping`. |
| `no AP found` | STA | Cek router 2.4GHz aktif, SSID broadcast on, bukan hidden. Dekatkan ESP32 <3m. |
| `CSI empty / len 0` | Keduanya | Cek firmware CSI enabled, cek channel, coba reset board. |
| `sniffer no packet` | Sniffer | Cek channel manual benar (6). Cek BSSID benar (`netsh` lagi). Cek router beacon interval 100ms (default). |
| `channel miss after router reboot` | Sniffer | Kunci channel router ke 6 (bukan Auto). Atau set auto-hop script. |
| `PowerShell parse error near FLAMBOYAN` | Keduanya | Selalu pakai `"FLAMBOYAN'S"` kutip ganda, jangan `'FLAMBOYAN'S'`. |
| `COM4 not found` | Keduanya | Masuk download mode (BOOT+RESET), cek Device Manager, ganti kabel data. |

---
*SSID: "FLAMBOYAN'S" / <YOUR_WIFI_PASSWORD> — STA recommended dulu — Sniffer untuk eksperimen — Firmware B: https://github.com/Steven063/ESP32-CSI-Tool/releases — Source A: https://github.com/ruvnet/RuView/tree/main/firmware/esp32-csi-node*
