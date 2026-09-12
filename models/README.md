# Models — WiFiSense / RuView Pretrained Weights

Folder ini untuk menyimpan **pretrained weights** RuView (CSI sensing model).

## Cara download (manual)

RuView biasanya publish model di Hugging Face. Contoh:

```powershell
pip install huggingface_hub

# via python
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='ruvnet/RuView', local_dir='models/ruview', local_dir_use_symlinks=False)"

# atau hf CLI
huggingface-cli download ruvnet/RuView --local-dir models/ruview
```

Jika repo belum ada, cek https://github.com/ruvnet/RuView -> rilis / docs model.

## Struktur yang diharapkan

```
models/
├─ README.md          # file ini
├─ ruview/
│  ├─ config.json
│  ├─ model.safetensors / model.bin
│  └─ tokenizer/ (jika ada)
└─ csi_classifier.pt  # model custom kecil (opsional)
```

## Placeholder

Saat ini belum ada weights yang di-commit (karena besar). `.gitignore` mengabaikan `*.bin`, `*.pt`, `*.safetensors`, `*.onnx`.

Untuk eksperimen awal tanpa model berat:
- Gunakan `numpy` + `scikit-learn` untuk classifier sederhana dari CSI amplitude.
- Contoh script nanti di `server/` atau `scripts/collect_csi.py`.

## Lisensi

Ikuti lisensi model asli RuView. Jangan re-distribusi weights tanpa izin.
