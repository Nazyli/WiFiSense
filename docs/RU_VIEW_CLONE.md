# RuView Clone — Status & Instruksi Manual

## Status clone otomatis

Percobaan `git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview` pada 2026-09-13 **gagal / timeout** (network blocked / shallow.lock tersisa, hanya .git kosong).

Maka `_ruview/` tidak tersedia secara otomatis. Ini placeholder.

## Instruksi manual (wajib jika ingin firmware asli)

### Opsi A — Git (jika internet sudah allow)

```powershell
cd D:\AI\WiFiSense
Remove-Item -Recurse -Force _ruview -ErrorAction SilentlyContinue
git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview
dir _ruview
# cari firmware
dir _ruview -Recurse -Filter "*.bin" | Select-Object FullName -First 10
```

### Opsi B — Download ZIP (tanpa git)

1. Buka https://github.com/ruvnet/RuView di browser
2. Tombol hijau **Code -> Download ZIP**
3. Extract ke `D:\AI\WiFiSense\_ruview`
4. Copy binary ke `firmware/`:
   ```
   _ruview/firmware/esp32-csi-node/build/*.bin -> firmware/
   ```

### Opsi C — ESP-IDF build

```powershell
cd _ruview
idf.py set-target esp32s3
idf.py menuconfig  # enable CSI, set SSID
idf.py build flash monitor
```

## Yang dicari di RuView

- `firmware/esp32-csi-node/` atau `esp32/` — source ESP-IDF
- `models/` — pretrained weights link
- `docs/` — paper / arsitektur CSI

Jika repo RuView di masa depan pindah / private, fallback ke:
- https://github.com/Steven063/ESP32-CSI-Tool
- https://github.com/espressif/esp-csi

## Catatan

File ini dibuat otomatis oleh scaffolding fixer karena clone gagal. Hapus file ini setelah `_ruview` berhasil ter-clone manual.
