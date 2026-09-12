# BUNDLE-16MB-LOG — RuView 0.8.8 S3 16MB Investigation

> Tanggal: 2026-09-13 Asia/Jakarta
> Chip target: ESP32-S3 QFN56 rev0.2 **16MB flash / 8MB PSRAM — MAC <YOUR_DEVICE_MAC> — COM4**
> Operator: @fixer

## 1. Kesimpulan — TIDAK ADA bundle 16MB (per 2026-09-13)

**Bundle `esp32-csi-node-v0.8.8-s3-16mb-flash-bundle.zip` TIDAK PERNAH dirilis upstream.**

- Tag yang benar: **`v0.8.8-esp32`** (bukan `v0.8.8`). `v0.8.8` sebagai tag tidak ada → 404.
- `v0.8.8-esp32` hanya merilis **3 bundle**:
  | file | target | size | sha256 | download_count |
  |------|--------|------|--------|---|
  | `esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip` | ESP32-S3 8MB flash | 778550 B | `132d3d4fe3f23625eccbf6b4c2f404b31cb94f754bb2638d98cf2d0f65f8de46` | 299 |
  | `esp32-csi-node-v0.8.8-s3-4mb-flash-bundle.zip` | ESP32-S3 4MB flash | 627559 B | `3862ece2fa83c0ec4bb62b718c85d4f613e0221667577b3daf164e46a39d1c8b` | 74 |
  | `esp32-csi-node-v0.8.8-c6-4mb-flash-bundle.zip` | ESP32-C6 4MB | 675373 B | `cbcaa1564d9fe71f0eda1d6a1fad0e63fe5cb54a8cc5cf97b24f82af786d55d5` | 65 |
- Pencarian `*16mb*` di **331 releases** (via `gh api --paginate`) → **0 hasil**.
- History bundle ESP32-S3: hanya `8mb` dan `4mb` (v0.8.4 → hanya 8mb, v0.8.0-v0.8.3 → 8mb+4mb sebagai file terpisah, bukan bundle). Tidak ada varian `16mb` di versi mana pun.

**Implikasi untuk chip 16MB:** bundle **S3 8MB flash tetap kompatibel** dengan chip fisik 16MB. Partition table di bundle hanya memakai 8MB pertama; sisa 8MB tidak terpakai (aman). Flash dengan `--flash_size 8MB` atau `detect` (esptool akan detect 16MB tapi tulis sesuai offset bundle). Jangan gunakan `flash_size 16MB` secara manual — biarkan `detect` atau pakai `8MB`.

> File yang sudah ada `D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip` (778550 B, SHA256 terverifikasi) adalah file yang benar dan siap flash ke chip 16MB.

## 2. Verifikasi Bundle 8MB yang Ada (valid untuk 16MB chip)

- **Path lokal:** `D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip`
- **Size:** 778550 bytes (>500KB ✅)
- **SHA256:** `132D3D4FE3F23625ECCBF6B4C2F404B31CB94F754BB2638D98CF2D0F65F8DE46` — **cocok** dengan digest GitHub API & `SHA256SUMS.txt` canonical
- **SHA256SUMS.txt upstream (https://github.com/ruvnet/RuView/releases/download/v0.8.8-esp32/SHA256SUMS.txt):**
  ```
  7bbb97d26f53b9d9beb420cd4ebf5b3913f51da31e09d4161c0a3245b69ac529  esp32-csi-node-v0.8.8-c6-4mb.bin
  26fce74fada920be9e8c46c4d0d3046be4a90254200372563873f85b96843ea4  esp32-csi-node-v0.8.8-s3-4mb.bin
  baf6f86dc593156a19f837c56a1a1b235123d2edacf5f582363302097e3ae8f2  esp32-csi-node-v0.8.8-s3-8mb.bin
  cbcaa1564d9fe71f0eda1d6a1fad0e63fe5cb54a8cc5cf97b24f82af786d55d5  esp32-csi-node-v0.8.8-c6-4mb-flash-bundle.zip
  3862ece2fa83c0ec4bb62b718c85d4f613e0221667577b3daf164e46a39d1c8b  esp32-csi-node-v0.8.8-s3-4mb-flash-bundle.zip
  132d3d4fe3f23625eccbf6b4c2f404b31cb94f754bb2638d98cf2d0f65f8de46  esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip
  ```
- **Extract target:** `D:\AI\WiFiSense\firmware\bundle-extract\` (sudah ada ✅) dan duplikat ke `firmware\bundle-16mb-extract\` untuk memenuhi permintaan task
- **Isi bundle (8 file, SHA256 terverifikasi per `bundle-extract/SHA256SUMS.txt`):**
  ```
  7b8e80af12bcc36e74509faa58f691cc9e40892db7de7bff808bcbe3ad06acf4  bootloader.bin          18880 B ✅
  67222c257c0477501fd4002275638dc4262b34eb68235b8289fb1337054d322b  partition-table.bin     3072 B ✅
  7d2c7ac4888bfd75cd5f56e8d61f69595121183afc81556c876732fd3782c62f  ota_data_initial.bin    8192 B ✅
  baf6f86dc593156a19f837c56a1a1b235123d2edacf5f582363302097e3ae8f2  esp32-csi-node.bin     1127104 B ✅
  25d3fe425891d4e6cb3a233f6b40013ae633373eecbb4dfcbeece3ce0287b14c  version.txt                6 B (0.8.8)
  ca774d873c265d4fabe9b87adbd6afef9468f3df4d4c8a520186f536377409d3  FLASHING.md             1164 B
  e8bd29e766dbd62d0aa16b77db83eca2c75efb501c25a8883b4f2f6b5471479c  README.md              40313 B
  aeb0ea721c081b49d7c675bbd9c2975b386907af4a23c0119ffb4b1ad98fee95  RELEASE_NOTES.md        4999 B
  ```
- **Copy ke firmware root (overwrite yang 8MB — sama, jadi no-op tapi diverifikasi):**
  - `firmware\bootloader.bin` 18880 B SHA256 `7B8E80AF...` ✅
  - `firmware\partition-table.bin` 3072 B SHA256 `67222C25...` ✅
  - `firmware\ota_data_initial.bin` 8192 B ✅
  - `firmware\esp32-csi-node.bin` 1127104 B SHA256 `BAF6F86D...` ✅
  - `firmware\firmware.bin` (copy dari esp32-csi-node.bin, untuk kompatibilitas script lama) ✅
- **Hasil:** `firmware/bundle-16mb-extract/` identik dengan `bundle-extract/` — siap flash, tidak perlu download ulang.

## 3. Log Upaya Download 16MB (semua gagal 404 — expected)

Semua URL predictable diuji dengan `Invoke-WebRequest -Method Head` + `User-Agent Mozilla/5.0`, dan via `gh api` dengan auth:

```
[1] HEAD https://github.com/ruvnet/RuView/releases/download/v0.8.8/esp32-csi-node-v0.8.8-s3-16mb-flash-bundle.zip
    → 404 Not Found (tag v0.8.8 tidak ada)

[2] HEAD https://github.com/ruvnet/RuView/releases/download/v0.8.8/esp32-csi-node-v0.8.8-s3-16mb-flash-bundle.tar.gz
    → 404 Not Found

[3] HEAD https://github.com/ruvnet/RuView/releases/download/v0.8.8-esp32/esp32-csi-node-v0.8.8-s3-16mb-flash-bundle.zip
    → 404 Not Found (asset tidak ada di rilis v0.8.8-esp32)

[4] HEAD https://github.com/ruvnet/RuView/releases/download/v0.8.8-esp32/esp32-csi-node-v0.8.8-s3-16mb.bin
    → 404 Not Found

[5] HEAD https://github.com/ruvnet/RuView/releases/download/v0.8.8/esp32-csi-node-v0.8.8-s3-16mb.bin
    → 404 Not Found

[6] GET https://github.com/ruvnet/RuView/releases/tag/v0.8.8
    → 404 Not Found

[7] GET https://github.com/ruvnet/RuView/releases/tag/v0.8.8-esp32
    → 200 OK (220283 bytes) — tidak ada link *.zip 16mb di halaman

[8] gh api repos/ruvnet/RuView/releases/tags/v0.8.8
    → 404 Not Found (documentation_url https://docs.github.com/rest/releases/releases#get-a-release-by-tag-name)

[9] gh api repos/ruvnet/RuView/releases/tags/v0.8.8-esp32 --paginate
    → 200 OK — tag_name v0.8.8-esp32, 7 assets, tidak ada yang mengandung "16mb"

[10] gh api repos/ruvnet/RuView/releases --paginate --jq '.[].tag_name' (331 releases)
     → grep "16mb" → 0 hasil
     → bundle assets total 5: v0.8.4-8mb, v0.8.8 s3-8mb/4mb/c6-4mb, v0.9.0 witness-bundle

[11] Invoke-WebRequest SHA256SUMS.txt valid
     → https://github.com/ruvnet/RuView/releases/download/v0.8.8-esp32/SHA256SUMS.txt → 633 bytes, berisi 6 hash (tanpa 16mb)
```

**Kesimpulan log:** bukan error jaringan / auth — memang tidak ada asset 16MB yang dipublish.

## 4. Instruksi Manual (jika user tetap ingin bundle 16MB)

> **Tidak diperlukan** — bundle 8MB sudah valid untuk chip 16MB. Jika tetap ingin mencoba download manual:

1. Buka browser ke **https://github.com/ruvnet/RuView/releases/tag/v0.8.8-esp32** (bukan `/v0.8.8`)
2. Cari tabel "Choose the correct download" — hanya ada 3 bundle zip (s3-8mb, s3-4mb, c6-4mb)
3. Klik **`esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip`** → browser akan download dari
   `https://github.com/ruvnet/RuView/releases/download/v0.8.8-esp32/esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip`
4. Drag file hasil download ke **`D:\AI\WiFiSense\`** (overwrite yang 778550 B) — atau biarkan, karena sudah benar
5. Jika ingin file bernama 16mb, copy:
   ```powershell
   Copy-Item "D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip" "D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-16mb-flash-bundle.zip" -Force
   ```
   (hash tetap `132d3d4f...`, hanya alias nama)
6. Verifikasi:
   ```powershell
   Get-FileHash D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip -Algorithm SHA256
   # harus 132D3D4FE3F23625ECCBF6B4C2F404B31CB94F754BB2638D98CF2D0F65F8DE46
   Expand-Archive -LiteralPath D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip -DestinationPath D:\AI\WiFiSense\firmware\bundle-16mb-extract -Force
   Get-ChildItem D:\AI\WiFiSense\firmware\bundle-16mb-extract
   ```
7. Flash (tidak diwajibkan oleh task ini, tapi untuk referensi):
   ```powershell
   # Mode 4-file (recommended, preserve NVS)
   python -m esptool --chip esp32s3 --port COM4 --baud 460800 write_flash `
     0x0000 firmware\bootloader.bin `
     0x8000 firmware\partition-table.bin `
     0xf000 firmware\ota_data_initial.bin `
     0x20000 firmware\esp32-csi-node.bin

   # atau jika esptool auto-detect 16MB, eksplisit 8MB:
   python -m esptool --chip esp32s3 --port COM4 --baud 460800 --flash_size 8MB write_flash --flash_mode dio --flash_freq 80m `
     0x0000 firmware\bootloader.bin 0x8000 firmware\partition-table.bin 0xf000 firmware\ota_data_initial.bin 0x20000 firmware\esp32-csi-node.bin
   ```

Jika di masa depan RuView merilis varian 16MB, URL akan menjadi:
`https://github.com/ruvnet/RuView/releases/download/<tag-baru>/esp32-csi-node-<ver>-s3-16mb-flash-bundle.zip`
— tinggal `Invoke-WebRequest` ke URL baru dan simpan sebagai `esp32-csi-node-v0.8.8-s3-16mb-flash-bundle.zip`.

## 5. File yang Disiapkan Hari Ini (tanpa flash)

- `D:\AI\WiFiSense\esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip` — **tetap** 778550 B, SHA256 valid (tidak dihapus)
- `D:\AI\WiFiSense\firmware\bundle-extract\` — 8 file original (sudah ada)
- `D:\AI\WiFiSense\firmware\bundle-16mb-extract\` — **baru dibuat**, duplikat identik dari bundle-extract (8 file, hash ✅)
- `D:\AI\WiFiSense\firmware\bootloader.bin`, `partition-table.bin`, `ota_data_initial.bin`, `esp32-csi-node.bin`, `firmware.bin` — overwrite & terverifikasi SHA256 (lihat §2)
- `D:\AI\WiFiSense\firmware\BUNDLE-16MB-LOG.md` — file ini
- `D:\AI\WiFiSense\firmware\READY.md` — update jadi 🟡 READY 8MB-on-16MB (lihat file tersebut)
- **Tidak dibuat:** `esp32-csi-node-v0.8.8-s3-16mb-flash-bundle.zip` — sengaja tidak dibuat sebagai file palsu; jika butuh alias, lihat instruksi copy di §4 step 5.

## 6. Validasi Akhir

```powershell
Get-ChildItem D:\AI\WiFiSense\ -Filter *.zip | Format-Table Name, Length
# esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip   778550
# esp-csi-master.zip                            25026658 (cache source, opsional)

Get-ChildItem D:\AI\WiFiSense\firmware\bundle-16mb-extract\
# 8 file: bootloader.bin, partition-table.bin, ota_data_initial.bin, esp32-csi-node.bin, version.txt, FLASHING.md, README.md, RELEASE_NOTES.md, SHA256SUMS.txt

Get-Content firmware\bundle-16mb-extract\version.txt
# 0.8.8

python -m esptool --chip esp32s3 image_info firmware\esp32-csi-node.bin
# (opsional, akan shows valid image)
```

## 7. Referensi

- Rilis v0.8.8-esp32: https://github.com/ruvnet/RuView/releases/tag/v0.8.8-esp32 (body berisi Measured hardware validation 2026-08-31)
- API: `gh api repos/ruvnet/RuView/releases/tags/v0.8.8-esp32` (assets 7, verified)
- Issue flash size 16MB: esptool `Detected flash size: 16MB` (log user), tapi partition table bundle hanya 8MB — sisa flash tidak terpakai, aman. Untuk memanfaatkan penuh 16MB butuh custom partition CSV & rebuild via ESP-IDF 5.4 (tidak ada prebuilt).

---
*Generated by @fixer 2026-09-13 — 16MB bundle not found, 8MB bundle verified compatible with 16MB flash.*
