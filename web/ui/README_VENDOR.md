# WiFiSense UI Vendor — RuView upstream

**Sumber**: https://github.com/ruvnet/RuView/tree/main/ui  
**Upstream commit**: `33a9e90896a691a3f98de042b463e5945178b87c` (2026-09-11 13:32:02Z — Merge PR #1902 feat/firmware-usb-onboarding-c6)  
**Tanggal vendoring**: 2026-09-13  
**Cache mentah**: `_ruview/` (tetap ignored via `.gitignore:45`, berisi full sparse clone + `.git` untuk re-sync)  
**FE yang di-commit**: `web/ui/` (dipilih konsisten; alternatif `server_py/static/ui/` tidak dipakai — pilih satu agar mount konsisten)

## Apa yang di-vendor
- Full `ui/` dari RuView: `index.html`, `observatory.html`, `pose-fusion.html`, `viz.html`, `app.js`, `style.css`, `config/`, `services/`, `components/`, `utils/`, `tests/` + subfolder `observatory/`, `pose-fusion/`, `icons/`, `mobile/` (mobile ikut tercopy tapi tidak wajib untuk Python BE, boleh ignore saat serve).
- Binary besar **tidak** di-commit: `*.zip`, `*.bin`, `models/*.pt` etc sudah di-ignore global. File `.wasm` (154KB + 51KB) di `pose-fusion/pkg/` tetap di-commit karena kecil & dibutuhkan pose-fusion; `mobile/assets/icon.png` 393KB ikut tapi optional — bukan bundle firmware.
- Satu-satunya edit upstream: `web/ui/config/api.config.js` — `BASE_URL` sudah upstream `= window.location.origin` (auto-detect) sehingga ngobrol ke Python BE di origin yang sama, plus `buildWsUrl()` pakai `window.location.host` + `protocol` adaptif (http→ws, https→wss). Tidak ada hard-code `localhost:3000` lagi; jika ada, ganti ke `_origin`.

## Cara re-sync upstream
### Opsi A — sparse-checkout (tanpa 60+ crates, recommended)
```powershell
cd D:\AI\WiFiSense
Remove-Item -Recurse -Force _ruview -ErrorAction SilentlyContinue
git clone --depth 1 --filter=blob:none --sparse https://github.com/ruvnet/RuView.git _ruview
git -C _ruview sparse-checkout set ui
# update FE
Remove-Item -Recurse -Force web\ui
Copy-Item -Path _ruview\ui -Destination web\ui -Recurse -Force
# verifikasi
dir web\ui
git -C _ruview log --oneline -1   # catat hash baru untuk update README ini
```

### Opsi B — fallback ZIP (jika git block)
```powershell
cd D:\AI\WiFiSense
Invoke-WebRequest -Uri https://github.com/ruvnet/RuView/archive/refs/heads/main.zip -OutFile _ruview.zip
Expand-Archive _ruview.zip -DestinationPath _tmp_ruview -Force
# hasil extract: _tmp_ruview/RuView-main/ui -> copy
Remove-Item -Recurse -Force web\ui
Copy-Item -Path _tmp_ruview\RuView-main\ui -Destination web\ui -Recurse -Force
# simpan cache mentah di _ruview/ui (tetap ignored)
New-Item -ItemType Directory -Path _ruview\ui -Force | Out-Null
Copy-Item -Path _tmp_ruview\RuView-main\ui\* -Destination _ruview\ui -Recurse -Force
Remove-Item -Recurse -Force _tmp_ruview, _ruview.zip
dir web\ui
```

### Setelah copy, jangan ubah file upstream kecuali:
- `web/ui/config/api.config.js` → pastikan `BASE_URL = window.location.origin` (atau `_origin` seperti di atas).

## Verifikasi
```powershell
ls web\ui
# harus ada 5 file kunci:
Test-Path web\ui\index.html                # True
Test-Path web\ui\observatory.html          # True
Test-Path web\ui\pose-fusion.html          # True
Test-Path web\ui\services\sensing.service.js  # True
Test-Path web\ui\tests\test-runner.html    # True

# hash upstream yang ter-vendor:
git -C _ruview rev-parse HEAD              # 33a9e90896a691a3f98de042b463e5945178b87c

# .gitignore jangan ignore web/ui:
git check-ignore -v web\ui\index.html      # (no output = tidak di-ignore)
git status --short                         # web/ui/ harus untracked → siap add
```

## Mount Python BE (lane BE, tidak diubah di task ini)
FE ini diserve Python via `server_py` / runner Rust expectation `GET /api/v1/* + WS /ws/sensing`. Pastikan server mount `web/ui` sebagai static di `/` (atau `/ui/`) konsisten dengan `BASE_URL = window.location.origin`. Jangan edit `server/index.js` atau `server_py/` di lane FE ini.

## Tidak commit binary besar
Hanya text + wasm kecil. `*.zip`, `firmware/*.bin`, `models/*.bin/pt` tetap ignored.
