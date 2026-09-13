# FLAMBOYAN DHCP Reservation + Re-target Guide

> **Tujuan:** Laptop selalu `192.168.1.75` di WiFi `FLAMBOYAN'S` agar ESP32 bisa kirim CSI ke `192.168.1.75:5005` tanpa re-flash. Jika pindah hotspot/kantor, pakai **1-klik Re-target** di Settings.

---

## Ringkas

| Situasi | Solusi |
|---------|--------|
| Di rumah, router `FLAMBOYAN'S` milik sendiri, laptop selalu dapat IP sama | **DHCP Reservation** sekali, permanen |
| Pindah WiFi (hotspot HP, kantor, IP laptop berubah) | **Re-target** 1-klik di panel Settings → WiFi |
| Target IP | **Read-only** `192.168.1.75:5005` — otomatis diisi dari IP laptop saat Re-target |

---

## A. DHCP Reservation di Router FLAMBOYAN'S (Sekali di Rumah)

> Mengunci agar laptop **selalu dapat `192.168.1.75`** tiap connect ke `FLAMBOYAN'S`. ESP32 yang sudah di-provision ke `192.168.1.75` tidak perlu di-flash ulang.

### 1. Siapkan MAC Laptop

```powershell
ipconfig /all
# Cari adapter Wi-Fi yang connect ke FLAMBOYAN'S:
#    Wireless LAN adapter Wi-Fi:
#      Physical Address. . . . . . . . : AA-BB-CC-DD-EE-FF   <- catat ini
#      IPv4 Address. . . . . . . . . . : 192.168.1.x
```

Atau:

```powershell
Get-NetAdapter -Name "Wi-Fi" | Select-Object Name, MacAddress, Status
```

### 2. Login Router

1. Browser → `http://192.168.1.1` (kebanyakan FLAMBOYAN'S / IndiHome / TP-Link / ZTE pakai ini).
2. Login admin (cek stiker belakang router atau tanya pemilik: biasanya `admin` / `user`).
3. Masuk menu **DHCP → Address Reservation**  
   Alias di beberapa firmware: `LAN → DHCP Server → Static Lease` / `DHCP Reservation` / `Address Reservation`.

### 3. Tambah Reservation

1. Klik **Add New / Add / Create**.
2. Isi:
   - **MAC Address:** `AA:BB:CC:DD:EE:FF` (MAC laptop dari langkah 1, pakai format `:` atau `-` sesuai router)
   - **Reserved / Assigned IP:** `192.168.1.75`
   - **Status:** Enabled
3. **Save / Apply**.

> Tip: Jika router sudah ada IP `.75` dipakai device lain, hapus dulu atau pilih `.75` tetap bisa overwrite — pastikan tidak bentrok.

### 4. Reboot & Verifikasi

1. **Reboot router** (System Tools → Reboot) atau cabut/colok power 10 detik.
2. Di laptop: disconnect lalu reconnect WiFi `FLAMBOYAN'S`, atau:
   ```powershell
   ipconfig /release; ipconfig /renew
   ipconfig /all
   # Harus sekarang: IPv4 Address . . . : 192.168.1.75
   ```
3. Jika masih bukan `.75`: cek MAC salah ketik, pastikan reservation **Enabled**, dan `DHCP Server` aktif.

Selesai. Selama di `FLAMBOYAN'S` dengan IP `.75`, ESP32 tinggal di-provision sekali:

```powershell
python firmware\provision.py --port COMx --ssid "FLAMBOYAN'S" --password <YOUR_WIFI_PASSWORD> --target-ip 192.168.1.75 --target-port 5005
```

---

## B. Re-target 1-Klik di Panel Settings → WiFi (Kalau Pindah Jaringan)

> Saat laptop ganti WiFi, IP berubah (mis. `192.168.43.20` / `10.1.10.x`). ESP32 masih kirim ke IP lama → data hilang. **Re-target** otomatis tulis ulang `target_ip` di NVS tanpa re-build firmware.

### Posisi Panel

Web UI → **Settings → WiFi / Provision** (label bisa `WiFiSense Settings` atau `Hardware` tergantung versi UI).

### 3 Langkah

#### 1. Colok ESP32 & Pilih COM

- Colok USB-C ESP32-S3 ke laptop.
- Di panel Settings → WiFi, buka dropdown **Port**:
  - Isi otomatis dari `[System.IO.Ports.SerialPort]::getPortNames()` — contoh `COM3`, `COM4`, `COM7`.

> **COM Dinamis — ngga wajib COM4!**
> Port muncul sebagai `USB JTAG/serial debug unit (COMx)` — angka `x` tergantung slot USB, driver, & urutan colok. Lihat `firmware/READY.md:42` (`.\scripts\flash.ps1 -Port COM4` hanya contoh, jika hilang pakai `COM3`) dan `docs/HARDWARE.md:51` (Device Manager → Ports (COM & LPT) → `USB JTAG/serial debug unit (COMx)`). **Pilih yang muncul**, jangan memaksa COM4.

Cek manual jika dropdown kosong:

```powershell
[System.IO.Ports.SerialPort]::getPortNames()
Get-PnpDevice -Class Ports -PresentOnly | Format-Table FriendlyName, InstanceId
```

#### 2. Target IP Otomatis

- Field **Target IP** di panel bersifat **read-only** — terisi otomatis `192.168.1.75` (atau IP laptop saat ini jika laptop sudah pindah).
- Logika: frontend baca IP WiFi laptop (`ipconfig` / `window.location` / API backend) → isi `target_ip` + `target_port 5005`.
- Kamu tidak perlu ketik manual. Jika IP laptop sekarang `192.168.43.20`, Target IP akan jadi `192.168.43.20:5005` otomatis.

#### 3. Test → Apply

1. Klik **Test** (dry-run):
   - App menjalankan `provision.py --dry-run` di belakang layar.
   - Cek indikator **pps > 0** (packet per second) di Dashboard / LiveDemo — artinya CSI sudah mengalir.
   - Jika `pps=0`, cek COM benar, baud 115200, dan ESP32 sudah connect WiFi (lihat monitor log).
2. Klik **Apply** (flash NVS):
   - Menulis `target_ip`, `target_port`, `ssid`, `password` baru ke partisi NVS `0x9000` (tidak menghapus firmware).
   - ESP32 auto-reset, reconnect WiFi, dan kirim CSI ke IP baru dalam ±5 detik.
   - Verifikasi: `pps` naik, log `wifi: connected, target 192.168.x.x:5005`.

**Kapan tekan Apply?** Hanya jika Test `pps>0` sudah OK. Jika Test gagal, jangan Apply — perbaiki COM/WiFi dulu.

---

## Kapan Pakai Mana?

| Kondisi | Pakai |
|---------|-------|
| **Di rumah, WiFi tetap `FLAMBOYAN'S`**, ingin sekali-set permanen | **DHCP Reservation** (`192.168.1.75`). ESP32 provision sekali, lupakan. |
| **Pindah hotspot/kantor/kos**, laptop dapat IP baru (mis. `192.168.0.10`, `10.x.x.x`) | **Re-target** 1-klik. Tidak perlu ubah router orang lain, cukup tulis ulang NVS ESP32. |
| **Ganti SSID** (mis. dari `FLAMBOYAN'S` ke `Kantor_2.4G`) | Re-target juga ganti SSID/PASS. Atau manual: `python firmware\provision.py --port COMx --ssid "Kantor_2.4G" --password ... --target-ip <IP-baru>` |
| **Balik ke rumah** | Re-target balik ke `192.168.1.75` atau biarkan reservation yang handle (IP kembali `.75` otomatis). |

### Kenapa Target IP Read-Only?

- Menghindari typo (`192.168.1.57` vs `75`) yang bikin ESP32 kirim ke alamat salah.
- `192.168.1.75:5005` adalah **konvensi proyek** — server Python (`server_py/app.py` / `csi_ingest.py`) listen di `5005/UDP` untuk CSI. Semua node WiFiSense default ke sana. Provision manual juga pakai `--target-port 5005` kalau mau eksplisit.
- Saat Re-target, nilai read-only di-update otomatis dari IP laptop. Jika ganti WiFi dan IP laptop berubah (cek `ipconfig`), **wajib** Re-target ulang — kalau tidak, ESP32 tetap kirim ke `192.168.1.75` yang sekarang tidak ada yang listen.

### Alur Lengkap Pindah WiFi

```
1. Laptop connect WiFi baru → IP berubah (ipconfig /all)
2. Buka Settings → WiFi → pilih COMx (dinamis)
3. Target IP auto-update → Test (dry-run, cek pps>0)
4. Apply → ESP32 reset → CSI ngalir ke IP baru
5. (Opsional) Jika WiFi baru milik sendiri, buat reservation lagi untuk IP itu biar permanen
```

---

## Troubleshooting Cepat

| Gejala | Sebab | Fix |
|--------|-------|-----|
| `ipconfig` tetap bukan `.75` setelah reservation | MAC salah, reservation Disabled, atau DHCP Server mati | Cek MAC pakai `:` , Enable, Save, reboot router, `ipconfig /release & /renew` |
| `192.168.1.1` tidak bisa login | Router pakai `192.168.0.1` / `192.168.18.1` | Cek stiker router atau `ipconfig` → `Default Gateway` = alamat login |
| COM tidak muncul di dropdown | Kabel charge-only, driver belum install | Ganti kabel **data**, cek `HARDWARE.md` § Cara Masuk Download Mode, install CH340/CP210x jika perlu |
| COM muncul tapi Test pps=0 | Salah COM, salah baud, ESP32 belum connect WiFi | Pilih COM lain, cek `[System.IO.Ports.SerialPort]::getPortNames()`, monitor `.\scripts\monitor.ps1 -Port COMx -Baud 115200` |
| Apply sukses tapi tetap tidak ada data | Firewall blok UDP 5005 | `Windows Firewall → Allow app → python` atau `New-NetFirewallRule -DisplayName "WiFiSense 5005" -Direction Inbound -LocalPort 5005 -Protocol UDP -Action Allow` |
| Balik ke rumah tapi IP bukan `.75` lagi | Reservation terhapus setelah reset router | Ulangi langkah A, atau pakai Re-target untuk tulis `.75` lagi |

---

## Referensi

- COM dinamis: `firmware/READY.md:42`, `docs/HARDWARE.md:51` — port `USB JTAG/serial debug unit (COMx)`, pilih yang terdeteksi.
- Provision manual: `firmware/provision.py --help` (additive-by-default, `--dry-run`, `--state` untuk debug).
- Mode WiFi FLAMBOYAN'S: `docs/PLAN-MODE-WIFI.md`.
- Hardware & download mode: `docs/HARDWARE.md`.

*Ditulis untuk WiFiSense — FLAMBOYAN'S `192.168.1.75:5005` — jangan ubah kode, cukup rezervasi atau Re-target.*
