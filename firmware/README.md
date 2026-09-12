# Firmware — ESP32-S3 CSI Node

Folder ini untuk binary & source firmware CSI.

## File yang diharapkan

```
firmware/
├─ bootloader.bin          (0x0000)
├─ partition-table.bin     (0x8000)
├─ firmware.bin            (0x10000)  atau esp32-csi-node.bin
└─ merged.bin              (alternatif single-file 0x0)
```

## Sumber firmware

### Opsi 1 — RuView (recommended)

Repo: https://github.com/ruvnet/RuView

Jika clone `_ruview` sukses, firmware ada di:

```
_ruview/firmware/esp32-csi-node/
_ruview/esp32-csi-node/
_ruview/src/esp32/
```

Build via ESP-IDF:

```powershell
cd _ruview/firmware/esp32-csi-node
idf.py set-target esp32s3
idf.py menuconfig  # set WiFi SSID/PASS, enable CSI
idf.py build
# hasil di build/bootloader/bootloader.bin, build/partition_table/..., build/esp32-csi-node.bin
xcopy build\bootloader\bootloader.bin ..\..\firmware\ /Y
xcopy build\partition_table\partition-table.bin ..\..\firmware\ /Y
xcopy build\esp32-csi-node.bin ..\..\firmware\firmware.bin /Y
```

### Opsi 2 — ESP32-CSI-Tool (alternatif)

https://github.com/Steven063/ESP32-CSI-Tool

Sudah ada binary rilis untuk S3.

### Opsi 3 — Download manual (jika git gagal)

Clone manual via browser:

1. Buka https://github.com/ruvnet/RuView
2. Code -> Download ZIP
3. Extract, copy `firmware/*.bin` ke sini

Atau via git di PowerShell:

```powershell
git clone --depth 1 https://github.com/ruvnet/RuView.git _ruview
```

## Flash

Lihat `scripts/flash.ps1`:

```powershell
.\scripts\flash.ps1 -Port COM3          # 3-file
.\scripts\flash.ps1 -Port COM3 -Merged  # merged.bin
```

## Cat clone gagal

Jika `_ruview` tidak ada (internet blocked / timeout), folder ini tetap placeholder. Ikuti Opsi 3 download manual.
