param(
    [string]$Port = "COM3",
    [int]$Baud = 115200,
    [switch]$Raw
)

<#
.SYNOPSIS
  Serial monitor untuk ESP32-S3 CSI.
.DESCRIPTION
  Alternatif ringan tanpa Arduino IDE. Pakai pyserial miniterm jika ada, fallback ke .NET SerialPort.
.EXAMPLE
  .\scripts\monitor.ps1 -Port COM3 -Baud 115200
  .\scripts\monitor.ps1 -Port COM3 -Baud 921600
#>

$ErrorActionPreference = "Stop"

Write-Host "=== WiFiSense Serial Monitor ===" -ForegroundColor Cyan
Write-Host "Port: $Port  Baud: $Baud  (Ctrl+C untuk keluar)" -ForegroundColor Gray

$ports = [System.IO.Ports.SerialPort]::getPortNames()
Write-Host "Port tersedia: $($ports -join ', ')" -ForegroundColor Gray
if ($ports -notcontains $Port) {
    Write-Host "WARN: $Port tidak ditemukan. Cek Device Manager." -ForegroundColor Yellow
    Write-Host "ESP32-S3 native USB kadang pindah COM setelah reset. Coba COM lain." -ForegroundColor Yellow
}

# Coba pakai python miniterm (lebih stabil)
$hasMiniterm = $false
try {
    python -m serial.tools.miniterm --help 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $hasMiniterm = $true }
} catch {}

if ($hasMiniterm -and -not $Raw) {
    Write-Host "Menggunakan: python -m serial.tools.miniterm $Port $Baud --raw --exit-char 0x03" -ForegroundColor Green
    Write-Host "Tekan Ctrl+] lalu Ctrl+C untuk exit (atau tutup window)" -ForegroundColor Yellow
    python -m serial.tools.miniterm $Port $Baud --raw
    exit $LASTEXITCODE
}

# Fallback .NET SerialPort
Write-Host "Fallback ke .NET SerialPort..." -ForegroundColor Yellow
try {
    $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
    $sp.ReadTimeout = 500
    $sp.WriteTimeout = 500
    $sp.DtrEnable = $true
    $sp.RtsEnable = $true
    $sp.Open()
    Write-Host "Terhubung ke $Port. Tekan Ctrl+C untuk keluar." -ForegroundColor Green
    $sp.DiscardInBuffer()

    # Handle Ctrl+C
    [Console]::TreatControlCAsInput = $false
    $exit = $false
    $handler = {
        $script:exit = $true
        Write-Host "`nMenutup..." -ForegroundColor Yellow
    }
    # Gunakan try/finally untuk cleanup

    while (-not $exit) {
        try {
            $line = $sp.ReadLine()
            # Highlight CSI
            if ($line -match "CSI_DATA|CSI|csidata") {
                Write-Host $line -ForegroundColor Cyan
            } elseif ($line -match "error|fail|panic", [System.StringComparison]::InvariantCultureIgnoreCase) {
                Write-Host $line -ForegroundColor Red
            } else {
                Write-Host $line
            }
        } catch [TimeoutException] {
            # no data, check key
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Modifiers -band [ConsoleModifiers]::Control -and $key.Key -eq "C") { break }
                # forward key ke serial (opsional)
                $sp.Write($key.KeyChar)
            }
        } catch {
            if ($exit) { break }
            Write-Host "Read error: $_" -ForegroundColor Red
            Start-Sleep -Milliseconds 500
        }
        if ([Console]::KeyAvailable) {
            $k = [Console]::ReadKey($true)
            if (($k.Modifiers -band [ConsoleModifiers]::Control) -and $k.Key -eq "C") { break }
        }
    }
} catch {
    Write-Error "Gagal buka $Port $Baud : $_"
    Write-Host @"
Tips:
- Coba baud lain: 921600, 115200, 74880
- Tekan RESET di board
- Coba: python -m serial.tools.miniterm $Port 115200 --raw
- Cek apakah port dipakai aplikasi lain (Arduino IDE / Putty)
"@ -ForegroundColor Yellow
    exit 1
} finally {
    if ($sp -and $sp.IsOpen) { $sp.Close(); $sp.Dispose(); Write-Host "Port ditutup." -ForegroundColor Gray }
}
