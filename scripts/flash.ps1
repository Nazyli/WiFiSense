param(
    [string]$Port = "COM3",
    [int]$Baud = 460800,
    [switch]$Merged,
    [string]$FirmwareDir = "$PSScriptRoot\..\firmware"
)

<#
.SYNOPSIS
  Flash ESP32-S3 untuk WiFiSense / RuView CSI via esptool.
.DESCRIPTION
  Menangani kasus native USB CDC ESP32-S3 yang butuh manual BOOT.
  Default: flash 3 file (bootloader 0x0, partition 0x8000, firmware 0x10000).
  Dengan -Merged: flash merged.bin di 0x0.
.EXAMPLE
  .\scripts\flash.ps1 -Port COM3 -Baud 460800
  .\scripts\flash.ps1 -Port COM5 -Merged
#>

$ErrorActionPreference = "Stop"

Write-Host "=== WiFiSense ESP32-S3 Flash ===" -ForegroundColor Cyan
Write-Host "Port: $Port  Baud: $Baud  FirmwareDir: $FirmwareDir"

# Cek python & esptool
try {
    $py = Get-Command python -ErrorAction Stop
    Write-Host "Python: $($py.Source) $(python --version)" -ForegroundColor Green
} catch {
    Write-Error "python tidak ditemukan di PATH. Install Python 3.9+ dan centang Add to PATH."
    exit 1
}

$esptoolCheck = python -m esptool version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "esptool belum terinstall. Install via:" -ForegroundColor Yellow
    Write-Host "  pip install esptool pyserial" -ForegroundColor Yellow
    Write-Host "atau" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements.txt" -ForegroundColor Yellow
    $answer = Read-Host "Install sekarang? (y/n)"
    if ($answer -eq "y") {
        python -m pip install esptool pyserial
        if ($LASTEXITCODE -ne 0) { Write-Error "Gagal install esptool"; exit 1 }
    } else {
        exit 1
    }
}

# Cek port
$ports = [System.IO.Ports.SerialPort]::getPortNames()
Write-Host "Port tersedia: $($ports -join ', ')" -ForegroundColor Gray
if ($ports -notcontains $Port) {
    Write-Host "WARN: $Port tidak terdeteksi!" -ForegroundColor Yellow
    Write-Host @"
[Instruksi ESP32-S3 Native USB CDC]
1. Cabut USB, tahan tombol BOOT (GPIO0) jangan dilepas.
2. Colok USB sambil tahan BOOT, atau tekan+lepas RESET sambil tahan BOOT.
3. Lepas BOOT setelah 1 detik.
4. Cek Device Manager -> Ports (COM & LPT) harus muncul 'USB JTAG/serial debug unit (COMx)'.
5. Jika masih tidak muncul, coba kabel USB data lain (bukan charge-only) atau port USB lain.
"@ -ForegroundColor Yellow
    $cont = Read-Host "Lanjut paksa flash ke $Port? (y/n)"
    if ($cont -ne "y") { exit 1 }
}

# Resolve firmware files
$FirmwareDir = Resolve-Path $FirmwareDir -ErrorAction SilentlyContinue
if (-not $FirmwareDir) {
    Write-Error "Folder firmware tidak ditemukan: $PSScriptRoot\..\firmware"
    exit 1
}
$FirmwareDir = $FirmwareDir.Path

if ($Merged) {
    $merged = Get-ChildItem -Path $FirmwareDir -Filter "*merged*.bin" | Select-Object -First 1
    if (-not $merged) { $merged = Get-ChildItem -Path $FirmwareDir -Filter "*.bin" | Select-Object -First 1 }
    if (-not $merged) {
        Write-Error "Tidak ada .bin di $FirmwareDir. Letakkan merged.bin dulu."
        exit 1
    }
    Write-Host "Mode MERGED: $($merged.FullName) -> 0x0" -ForegroundColor Cyan
    $args = @("--chip","esp32s3","--port",$Port,"--baud",$Baud,"--before","default_reset","--after","hard_reset","write_flash","-z","--flash_mode","dio","--flash_freq","80m","--flash_size","detect","0x0",$merged.FullName)
} else {
    $boot = Join-Path $FirmwareDir "bootloader.bin"
    $part = Join-Path $FirmwareDir "partition-table.bin"
    $fw   = Join-Path $FirmwareDir "firmware.bin"
    if (-not (Test-Path $fw)) { $fw = Join-Path $FirmwareDir "esp32-csi-node.bin" }
    if (-not (Test-Path $fw)) {
        # fallback: ambil bin terbesar
        $fwCand = Get-ChildItem -Path $FirmwareDir -Filter "*.bin" | Sort-Object Length -Descending | Select-Object -First 1
        if ($fwCand) { $fw = $fwCand.FullName }
    }

    foreach ($f in @($boot,$part,$fw)) {
        if (-not (Test-Path $f)) {
            Write-Host "File tidak ditemukan: $f" -ForegroundColor Yellow
        } else {
            Write-Host "Found: $f ($( (Get-Item $f).Length / 1KB -as [int]) KB)" -ForegroundColor Green
        }
    }

    if (-not (Test-Path $boot) -or -not (Test-Path $part) -or -not (Test-Path $fw)) {
        Write-Host @"
[File belum lengkap]
Butuh 3 file di firmware/:
  bootloader.bin      -> 0x0000
  partition-table.bin -> 0x8000
  firmware.bin        -> 0x10000
Atau gunakan -Merged jika hanya punya merged.bin
Download dari RuView release atau build via ESP-IDF.
"@ -ForegroundColor Yellow
        $cont2 = Read-Host "Lanjut coba flash dengan file yang ada? (y/n)"
        if ($cont2 -ne "y") { exit 1 }
    }
    $args = @("--chip","esp32s3","--port",$Port,"--baud",$Baud,"--before","default_reset","--after","hard_reset","write_flash","-z","--flash_mode","dio","--flash_freq","80m","--flash_size","detect","0x0",$boot,"0x8000",$part,"0x10000",$fw)
}

Write-Host ""
Write-Host "Menjalankan: python -m esptool $($args -join ' ')" -ForegroundColor Cyan
Write-Host "Jika stuck 'Connecting...', tahan BOOT + tekan RESET, lalu lepas BOOT." -ForegroundColor Yellow
Write-Host ""

# Eksekusi
python -m esptool @args
$code = $LASTEXITCODE
if ($code -eq 0) {
    Write-Host "`nFlash sukses! Tekan RESET sekali, lalu jalankan .\scripts\monitor.ps1 -Port $Port" -ForegroundColor Green
} else {
    Write-Host "`nFlash gagal (exit $code)." -ForegroundColor Red
    Write-Host @"
Troubleshoot:
- Turunkan baud: .\scripts\flash.ps1 -Port $Port -Baud 115200
- Masuk download mode manual: tahan BOOT, tekan RESET, lepas BOOT
- Ganti kabel USB / port USB 2.0 (bukan hub)
- Cek Device Manager apakah COM berubah setelah reset
"@ -ForegroundColor Yellow
}
exit $code
