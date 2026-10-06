# PLAN OPSI A — Build RuView esp32-csi-node Besok (Windows)

> **Tujuan:** Build firmware `esp32-csi-node` dari source RuView via ESP-IDF di Windows dan flash ke ESP32-S3 (COM4). Estimasi total **30–60 menit** tergantung kecepatan internet & disk.

## 1. Ringkasan & Tujuan

- Build firmware CSI resmi RuView (`firmware/esp32-csi-node`) agar bisa dikonfigurasi SSID `FLAMBOYAN'S` / `<YOUR_WIFI_PASSWORD>` lewat `menuconfig` dan capture CSI stabil.
- Hasil build dipakai untuk **Opsi A**; fallback tetap **Opsi B** (binary jadi) jika build gagal.
- Target chip: **ESP32-S3** (bukan S2/C3). Source: https://github.com/ruvnet/RuView/tree/main/firmware/esp32-csi-node

## 2. Estimasi Waktu Total 30–60 Menit

| Tahap | Estimasi | Keterangan |
|-------|----------|------------|
| **1. Download ESP-IDF Installer** | 5–10 menit | File `esp-idf-tools-setup-2.3.exe` ~300–500MB, tergantung internet |
| **2. Install ESP-IDF Tools** | 10–15 menit | Ekstrak + install toolchain, Python env, Git |
| **3. Clone RuView** | 1–3 menit | `git clone` shallow, ~50–100MB |
| **4. Set-target esp32s3** | 1 menit | `idf.py set-target esp32s3` |
| **5. menuconfig (enable CSI)** | 2–5 menit | Cek `CONFIG_ESP_WIFI_CSI_ENABLED` + isi SSID/PASS |
| **6. Build** | 8–15 menit | First build lama (compile semua); build ulang 2–3 menit |
| **7. Flash + Monitor** | 3–5 menit | Flash ke COM4, cek log CSI |
| **Total** | **30–60 menit** | Jika internet stabil & antivirus tidak blok |

> Jika install ESP-IDF sudah pernah, total bisa **<20 menit** (tinggal build).

## 3. Prasyarat (Cek Malam Ini)

- [ ] **Disk 10GB free** minimal di `C:` (ESP-IDF + toolchain ~4–6GB, build artifacts ~1–2GB, plus cache). Cek: `Get-PSDrive C | Select-Object Free`
- [ ] **Internet stabil** (jangan tethering lemot; butuh download ~500MB + clone GitHub)
- [ ] **Disable antivirus sementara** (Windows Defender / Avast / Smadav sering blok `python.exe`, `git.exe`, `idf.py` sebagai false positive). Tambahkan exclusion `C:\Espressif` jika tidak mau disable total.
- [ ] **Python 3.11 sudah ada** (cek `python --version` harus `Python 3.11.x`). ESP-IDF v5.4 support Python 3.8–3.12, tapi 3.11 paling aman. Jangan pakai Python dari Microsoft Store yang path-nya ada spasi.
- [ ] **Git sudah ada** (`git --version`). Jika belum, installer ESP-IDF akan install Git juga.
- [ ] **Kabel USB data** siap, ESP32-S3 terdeteksi COM4 (`[System.IO.Ports.SerialPort]::getPortNames()`)
- [ ] **PowerShell 5.1** (bawaan Windows) + hak admin untuk install ke `C:\Espressif`

## 4. Langkah Detail Windows (Step-by-Step)

### 4.1 Download ESP-IDF Installer

```powershell
# Buka browser ke:
# https://dl.espressif.com/dl/esp-idf/
# Download file:
# esp-idf-tools-setup-2.3.exe
# Alternatif direct (jika link masih aktif):
# https://dl.espressif.com/dl/esp-idf/esp-idf-tools-setup-2.3.exe

# Simpan ke Downloads, cek size ~400MB
Get-ChildItem "$env:USERPROFILE\Downloads\esp-idf-tools-setup-2.3.exe" | Select-Object Name, Length
```

> Jangan download `esp-idf.zip` manual — pakai **installer .exe** biar auto set PATH.

### 4.2 Install ke C:\Espressif\esp-idf\v5.4

```powershell
# 1. Jalankan sebagai Administrator:
#    Klik kanan esp-idf-tools-setup-2.3.exe -> Run as administrator

# 2. Pada wizard:
#    - Pilih "Custom" atau "Express" -> Express (recommended)
#    - Framework: ESP-IDF v5.4 (stable)  # atau v5.3 jika v5.4 belum ada di list
#    - Install path: C:\Espressif\esp-idf\v5.4
#      Tools path:   C:\Espressif\.espressif
#      JANGAN pakai path ada spasi! (mis D:\My Documents\Espressif -> GAGAL)
#    - Python: Use existing Python 3.11 (auto-detect) atau allow installer buat venv
#    - Check "Add to PATH" jika ada opsi
#
# 3. Tunggu install selesai (10-15 menit). Jangan close paksa.
# 4. Finish -> centang "Run ESP-IDF PowerShell" untuk test.
```

Verifikasi setelah install:

```powershell
# Buka ESP-IDF PowerShell (Start Menu -> ESP-IDF 5.4 PowerShell) atau jalankan manual:
C:\Espressif\esp-idf\v5.4\export.bat
# atau
C:\Espressif\esp-idf\v5.4\export.ps1

# Cek:
idf.py --version
python --version
git --version
# Harus keluar versi tanpa error
```

> Jika `idf.py` not found, berarti `export.bat` belum dijalankan. **Wajib** run `export.bat` setiap buka terminal baru.

### 4.3 Clone RuView

```powershell
# Buat folder kerja (mis di D:\AI\WiFiSense\_ruview)
cd D:\AI\WiFiSense

# Clone shallow biar cepat
git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview
# atau jika sudah ada folder _ruview:
# cd _ruview; git pull

Get-ChildItem _ruview\firmware\esp32-csi-node | Format-Table Name, Length
# Harus ada: CMakeLists.txt, sdkconfig.defaults, main/, components/
```

### 4.4 Export ESP-IDF Environment (WAJIB tiap terminal baru)

```powershell
# Di PowerShell biasa (bukan ESP-IDF PowerShell), jalankan:
C:\Espressif\esp-idf\v5.4\export.ps1
# atau jika pakai CMD:
# C:\Espressif\esp-idf\v5.4\export.bat

# Alternatif: buka langsung "ESP-IDF 5.4 PowerShell" dari Start Menu (sudah auto export)
```

### 4.5 Set Target esp32s3

```powershell
cd D:\AI\WiFiSense\_ruview\firmware\esp32-csi-node

# Hapus build lama jika pernah build untuk target lain
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force sdkconfig -ErrorAction SilentlyContinue

idf.py set-target esp32s3
# Output harus: "Set Target to: esp32s3, new sdkconfig created"
```

### 4.6 Menuconfig — Enable CSI & Isi SSID

```powershell
idf.py menuconfig
```

Di dalam menu (navigasi panah + Enter):

```
Component config  --->  ESP32S3-Specific  ---> (biarkan default)
Component config  --->  Wi-Fi  --->  [X] Enable WiFi CSI  (CONFIG_ESP_WIFI_CSI_ENABLED=y)
                       Pastikan ter-centang!

Example Connection Configuration  --->  (jika ada)
    WiFi SSID: FLAMBOYAN'S
    WiFi Password: <YOUR_WIFI_PASSWORD>
    # Catatan: apostrophe ' harus dalam kutip ganda di PowerShell nanti

Atau jika RuView pakai Kconfig custom:
RuView CSI Node Configuration  --->
    WiFi SSID = FLAMBOYAN'S
    WiFi Password = <YOUR_WIFI_PASSWORD>
    CSI Send Mode = Serial / UDP (pilih Serial untuk awal)
    Channel = 0 (auto follow AP) atau 6
```

Simpan: `S` -> `Y` -> `Q` keluar.

> Jika tidak ada menu SSID di menuconfig, nanti isi via `provision.py` atau edit `main/wifi_config.h` / `main/app_main.c` manual (lihat §5).

Cek hasil config:

```powershell
Select-String -Path sdkconfig -Pattern "CSI_ENABLED|WIFI_SSID|WIFI_PASS"
# Harus ada: CONFIG_ESP_WIFI_CSI_ENABLED=y
```

### 4.7 Build

```powershell
idf.py build
# Tunggu 8-15 menit first build
# Jika sukses, akhir log: "Project build complete. To flash, run..."
```

Hasil build ada di:

```
build/bootloader/bootloader.bin      -> offset 0x0
build/partition_table/partition-table.bin -> offset 0x8000
build/esp32-csi-node.bin             -> offset 0x10000  (nama bisa firmware.bin / csi-node.bin)
build/flash_args                      # file berisi alamat flash lengkap
build/esp32-csi-node.merged.bin      # jika ada, bisa flash 0x0 saja
```

Copy ke folder project biar `flash.ps1` bisa pakai:

```powershell
Copy-Item build\bootloader\bootloader.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\partition_table\partition-table.bin D:\AI\WiFiSense\firmware\ -Force
Copy-Item build\esp32-csi-node.bin D:\AI\WiFiSense\firmware\firmware.bin -Force -ErrorAction SilentlyContinue
Copy-Item build\*.bin D:\AI\WiFiSense\firmware\ -Force
Get-ChildItem D:\AI\WiFiSense\firmware\*.bin | Format-Table Name, Length
```

### 4.8 Flash ke COM4

```powershell
# Pastikan ESP32-S3 di COM4 (cek dulu)
[System.IO.Ports.SerialPort]::getPortNames()
# Harus ada COM4

# Opsi 1: pakai idf.py langsung (paling simple)
idf.py -p COM4 flash monitor
# Tekan Ctrl+] untuk exit monitor

# Opsi 2: pakai esptool via script project
.\scripts\flash.ps1 -Port COM4 -Baud 460800
# Jika hanya ada merged.bin:
# .\scripts\flash.ps1 -Port COM4 -Merged

# Opsi 3: manual esptool
python -m esptool --chip esp32s3 --port COM4 --baud 460800 --before default_reset --after hard_reset write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect 0x0 firmware\bootloader.bin 0x8000 firmware\partition-table.bin 0x10000 firmware\firmware.bin
```

Jika `Failed to connect`, masuk **Download Mode**: tahan BOOT -> tap RESET -> lepas BOOT, lalu flash lagi.

### 4.9 Monitor & Verifikasi CSI

```powershell
idf.py -p COM4 monitor
# atau
.\scripts\monitor.ps1 -Port COM4 -Baud 115200
# atau
python -m serial.tools.miniterm COM4 115200 --raw
```

Log sukses:

```
I (xxx) wifi: connected to ap SSID:FLAMBOYAN'S password:<YOUR_WIFI_PASSWORD>
I (xxx) wifi: channel 6, rssi -45
CSI_DATA, len=128, rssi=-42, channel=6, [12, -3, 45, ...]
```

Gerakkan tangan antara router dan ESP32, nilai CSI harus berubah.

## 5. Cara Provision SSID FLAMBOYAN'S (password <YOUR_WIFI_PASSWORD>)

Ada **2 cara**, pilih salah satu:

### Opsi A — via menuconfig (recommended untuk build awal)

Seperti di §4.6, isi langsung di `idf.py menuconfig`:

```
WiFi SSID = FLAMBOYAN'S
WiFi Password = <YOUR_WIFI_PASSWORD>
```

Kelebihan: credentials baked ke firmware, auto-connect saat boot. Kekurangan: ganti SSID harus rebuild.

**PowerShell escape note:** Karena SSID ada apostrophe `'`, selalu pakai **kutip ganda** di PowerShell:

```powershell
# BENAR:
$ssid = "FLAMBOYAN'S"
$pass = "<YOUR_WIFI_PASSWORD>"
idf.py menuconfig  # isi dengan FLAMBOYAN'S (tanpa escape tambahan di menuconfig)

# SALAH (akan error parsing):
# $ssid = 'FLAMBOYAN'S'  -> string terpotong!
```

### Opsi B — via provision.py / serial command (tanpa rebuild)

Jika firmware RuView support provisioning (cek `tools/provision.py` atau `scripts/provision.py` di repo):

```powershell
# Contoh jika ada provision.py
cd D:\AI\WiFiSense\_ruview\firmware\esp32-csi-node
python tools\provision.py --port COM4 --ssid "FLAMBOYAN'S" --password "<YOUR_WIFI_PASSWORD>" --channel 6

# Atau via serial console setelah flash:
python -m serial.tools.miniterm COM4 115200 --raw
# ketik di console ESP32:
# > wifi_config set ssid "FLAMBOYAN'S" password <YOUR_WIFI_PASSWORD>
# > wifi_config save
# > reset
```

Jika tidak ada `provision.py`, edit manual source lalu rebuild:

```powershell
# Cari file config
Select-String -Path _ruview\firmware\esp32-csi-node\main\* -Pattern "WIFI_SSID|ssid.*FLAMBOYAN"
# Edit file (mis main/app_main.c atau main/wifi_config.h):
# #define WIFI_SSID "FLAMBOYAN'S"
# #define WIFI_PASS "<YOUR_WIFI_PASSWORD>"
# lalu
idf.py build; idf.py -p COM4 flash
```

> Rekomendasi besok: pakai **Opsi A menuconfig** dulu biar cepat. Provision.py dipakai jika mau ganti AP tanpa rebuild.

## 6. Troubleshooting ESP-IDF Install Gagal

| Gejala | Penyebab | Solusi |
|--------|----------|--------|
| `Destination folder contains spaces` / `path with spaces is not supported` | Install di `C:\Users\Nama Panjang\...` atau `D:\My Documents\Espressif` | **Install ulang ke `C:\Espressif\esp-idf\v5.4`** tanpa spasi. Jangan pakai folder user yang ada spasi. |
| `Antivirus deleted python.exe / idf.py` | Defender/Avast blok file | Disable antivirus sementara, restore from quarantine, add exclusion `C:\Espressif` + `C:\Espressif\.espressif`. Re-run installer. |
| `Python version not supported` / `No Python found` | Python 3.13 terlalu baru atau Python Store bermasalah | Install **Python 3.11** dari https://www.python.org/downloads/ (centang Add to PATH). Uninstall Python Store version. Re-run installer pilih `Use existing Python 3.11`. |
| `git not found` | Git belum install | Installer ESP-IDF sudah include Git. Atau install manual https://git-scm.com/download/win , centang Add to PATH. |
| `idf.py not found` setelah install | Lupa export | Jalankan `C:\Espressif\esp-idf\v5.4\export.ps1` setiap buka terminal, atau buka via Start Menu `ESP-IDF 5.4 PowerShell`. |
| `Permission denied` / `Access is denied` | Tidak run as admin | Tutup installer, klik kanan -> **Run as administrator**. Pastikan `C:\Espressif` writable. |
| Build error `CSI not enabled` | Lupa menuconfig | `idf.py menuconfig` -> enable `CONFIG_ESP_WIFI_CSI_ENABLED=y`, lalu `idf.py build` lagi. |
| Download lambat / timeout | Internet putus / proxy kampus | Pakai tethering HP stabil, atau clone dengan `--depth 1`. Coba lagi `idf.py build` (akan resume). |
| `No space left on device` | Disk penuh | Kosongkan 10GB di `C:`, hapus `build/` lama, kosongkan Recycle Bin. |

**Cek disk & Python sebelum install:**

```powershell
Get-PSDrive C | Select-Object Used, Free, @{N="FreeGB";E={[math]::Round($_.Free/1GB,2)}}
python --version; python -m pip --version; git --version
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath  # cek exclusion Defender
```

## 7. Checklist Besok (Print / Copas ke Notes)

### Malam Ini (Persiapan)
- [ ] Cek `C:` free >=10GB
- [ ] Cek `python --version` == 3.11.x
- [ ] Siapkan installer `esp-idf-tools-setup-2.3.exe` di Downloads
- [ ] Cek COM4 muncul (`[System.IO.Ports.SerialPort]::getPortNames()`)
- [ ] Catat SSID `FLAMBOYAN'S` + password `<YOUR_WIFI_PASSWORD>` (pakai kutip ganda!)

### Besok Pagi — Install (30 menit)
- [ ] Disable antivirus / add exclusion `C:\Espressif`
- [ ] Run installer as Admin -> `C:\Espressif\esp-idf\v5.4` (tanpa spasi)
- [ ] Jalankan `export.ps1` / buka `ESP-IDF PowerShell`, cek `idf.py --version`
- [ ] `git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview`
- [ ] `cd _ruview\firmware\esp32-csi-node` -> `idf.py set-target esp32s3`

### Build & Flash (15 menit)
- [ ] `idf.py menuconfig` -> enable CSI + isi `FLAMBOYAN'S` / `<YOUR_WIFI_PASSWORD>`
- [ ] `idf.py build` -> tunggu sukses
- [ ] Copy `bootloader.bin`, `partition-table.bin`, `firmware.bin` ke `firmware/`
- [ ] Flash: `idf.py -p COM4 flash` atau `.\scripts\flash.ps1 -Port COM4`
- [ ] Monitor: `idf.py -p COM4 monitor` -> cek `connected to FLAMBOYAN'S` + `CSI_DATA`

### Jika Gagal -> Fallback Opsi B
- [ ] Download binary jadi dari https://github.com/Steven063/ESP32-CSI-Tool/releases
- [ ] Flash via `.\scripts\flash.ps1 -Port COM4`
- [ ] Lanjut ke `docs/PLAN-MODE-WIFI.md` coba mode STA dulu

---
*Opsi A source: https://github.com/ruvnet/RuView/tree/main/firmware/esp32-csi-node — Installer: https://dl.espressif.com/dl/esp-idf/ — Board: ESP32-S3 COM4*
