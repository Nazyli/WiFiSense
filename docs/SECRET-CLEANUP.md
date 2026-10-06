# Pembersihan credential WiFi dan Git history

Password dan MAC perangkat pada dokumentasi menggunakan placeholder.
Panduan ini menjelaskan cara membersihkan nilai lama dari history Git.
Verifikasi hasil cleanup pada clone baru dari remote sebelum menyatakan selesai.
Panduan ini ditujukan untuk `https://github.com/Nazyli/WiFiSense.git`.

## 1. Sebelum rewrite

Ganti password WiFi di router terlebih dahulu jika masih aktif, lalu provision
ulang perangkat yang menggunakannya. Jangan masukkan password baru ke repository.
Pembersihan history tidak mencabut akses yang diberikan password lama.

Review, commit, dan push perubahan sanitasi dokumentasi ini terlebih dahulu.
Clone pada langkah berikut mengambil kondisi remote, bukan perubahan lokal yang
belum dipush. Koordinasikan jeda push dengan kolaborator sampai cleanup selesai.
Simpan pekerjaan lokal yang belum dipush dan cadangan privat sebelum rewrite;
cadangan itu masih berisi credential lama, jadi batasi aksesnya.

Gunakan `git-filter-repo` versi 2.47 atau lebih baru yang mendukung
`--sensitive-data-removal`. Cek bantuan terlebih dahulu:

```powershell
rtk proxy git filter-repo -h
```

## 2. Clone terpisah dan aturan penggantian lokal

Jalankan blok PowerShell berikut dari `D:\WiFiSense`. Direktori tujuan harus
belum ada; jangan memakai checkout kerja untuk rewrite.

```powershell
Set-Location D:\WiFiSense
New-Item -ItemType Directory -Path .history-cleanup -ErrorAction Stop | Out-Null
rtk git clone --mirror https://github.com/Nazyli/WiFiSense.git .history-cleanup\WiFiSense.git
if ($LASTEXITCODE -ne 0) { throw 'Clone gagal; hentikan cleanup.' }

# Input disembunyikan; file aturan tetap plaintext dan harus dijaga privat.
$secretInput = Read-Host 'Password lama yang terpapar' -AsSecureString
$oldSecret = [System.Net.NetworkCredential]::new('', $secretInput).Password
if ([string]::IsNullOrWhiteSpace($oldSecret)) { throw 'Password lama wajib diisi.' }
if ($oldSecret.Contains('==>') -or $oldSecret.Contains("`n") -or $oldSecret.Contains("`r")) {
    throw 'Nilai ini perlu aturan filter-repo khusus.'
}
$rules = @('literal:' + $oldSecret + '==><YOUR_WIFI_PASSWORD>')
# Tambahkan variasi penulisan dengan spasi yang ditemukan di dokumentasi lama.
$variantInput = Read-Host 'Variasi password lama dengan spasi' -AsSecureString
$oldVariant = [System.Net.NetworkCredential]::new('', $variantInput).Password
if ([string]::IsNullOrWhiteSpace($oldVariant)) { throw 'Variasi wajib diisi.' }
if ($oldVariant.Contains('==>') -or $oldVariant.Contains("`n") -or $oldVariant.Contains("`r")) {
    throw 'Variasi ini perlu aturan filter-repo khusus.'
}
$rules += 'literal:' + $oldVariant + '==><YOUR_WIFI_PASSWORD>'
$oldMac = Read-Host 'MAC perangkat lama yang ingin dihapus dari history'
if ($oldMac -notmatch '^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$') {
    throw 'MAC wajib menggunakan format enam pasangan hex dengan titik dua.'
}
$rules += 'regex:(?i)' + [regex]::Escape($oldMac) + '==><YOUR_DEVICE_MAC>'
$rulesPath = Join-Path (Get-Location) '.history-cleanup\history-replacements.txt'
[System.IO.File]::WriteAllLines($rulesPath, $rules, [System.Text.UTF8Encoding]::new($false))
Set-Location .history-cleanup\WiFiSense.git
```

## 3. Rewrite lokal pada clone tersebut

Blok ini mengubah commit pada clone cleanup. Hash commit dan tanda tangan berubah.
`--replace-message` juga membersihkan pesan commit/tag. Jangan batasi `--refs`
ke satu branch karena credential mungkin ada di branch/tag lain.

```powershell
rtk proxy git filter-repo --sensitive-data-removal --replace-text $rulesPath --replace-message $rulesPath
if ($LASTEXITCODE -ne 0) { throw 'Rewrite gagal; jangan push.' }
```

Periksa semua commit tanpa mencetak baris yang berisi password:

```powershell
$commits = @(rtk proxy git rev-list --all)
if ($LASTEXITCODE -ne 0 -or $commits.Count -eq 0) { throw 'Daftar commit tidak valid.' }
foreach ($commit in $commits) {
    rtk proxy git grep -q -i -F -e $oldSecret -e $oldVariant -e $oldMac $commit
    if ($LASTEXITCODE -eq 0) { throw "Credential masih ada pada commit $commit" }
    if ($LASTEXITCODE -ne 1) { throw "Pemeriksaan gagal pada commit $commit" }
}
$messages = @(rtk proxy git log --all --format=%B)
if ($LASTEXITCODE -ne 0) { throw 'Pemeriksaan pesan commit gagal.' }
foreach ($line in $messages) {
    if ($line.IndexOf($oldSecret, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $line.IndexOf($oldVariant, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $line.IndexOf($oldMac, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        throw 'Credential atau MAC lama masih ada di pesan commit.'
    }
}
rtk proxy git fsck --full
if ($LASTEXITCODE -ne 0) { throw 'Integritas Git gagal; jangan push.' }
rtk git show-ref
rtk git remote -v
```

Pemeriksaan ini mencakup konten file dan pesan commit yang terjangkau refs;
review pesan annotated tag, nama file/ref, artefak binary/NVS, dan LFS secara
terpisah jika pernah menyimpan credential di sana. Jangan sekadar mengganti teks
di binary NVS: hapus artefak credential dari history melalui `--invert-paths`
dan `--path` yang sudah ditinjau. Catat laporan `filter-repo/changed-refs` dan
First Changed Commit(s) untuk menilai PR yang terkena dampak.

## 4. Publikasi history: langkah terpisah setelah review

Pastikan repo remote tidak menerima commit baru selama cleanup. Review refs,
branch/tag yang akan berubah, PR terdampak, dan izin force-push terlebih dahulu.
Jika remote berubah, ulangi dari clone baru agar pekerjaan orang lain terjaga.
`--mirror` juga dapat menghapus refs remote yang tidak ada pada clone lokal.

`git-filter-repo` dapat menghapus remote `origin`; jika hilang, tambahkan kembali:

```powershell
rtk git remote add origin https://github.com/Nazyli/WiFiSense.git
```

Hanya setelah review dan keputusan publikasi, jalankan dari clone cleanup:

```powershell
rtk git push --force --mirror origin
```

GitHub menolak perubahan `refs/pull/*` karena read-only. Kegagalan refs lain
harus diselesaikan; pulihkan aturan branch protection bila sempat diubah.
Verifikasi ulang dengan clone baru dari remote setelah push. Kolaborator sebaiknya
clone ulang dan jangan merge history lama kembali. Bersihkan fork, clone lama,
cadangan, dan file aturan plaintext sesuai kebutuhan setelah verifikasi.

Force-push tidak menghapus salinan pada fork, clone lain, atau cache/refs PR
GitHub. Tinjau insiden GitGuardian setelah rotasi dan verifikasi remote;
penghapusan cache oleh GitHub Support bergantung pada kelayakan kasus.

Referensi: [GitHub: Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
