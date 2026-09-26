# Update metadata untuk Pipeline v3.0

Basis upstream: `aa6b29d` (diperiksa ulang setelah repo kembali public).

## Perubahan

- `config.py`: default Gemini `gemini-3.5-flash` sesuai hasil uji akun pengguna,
  cadangan `gemini-flash-latest,gemini-3.7-flash`, metadata worker default 1,
  anggaran jeda retry 180 detik per model/request.
- `utils/metadata_ai.py`: fallback model dan provider, retry mengikuti header/body,
  pacing bersama dan cooldown antar worker, hentikan kuota harian/nol dan model
  404 selama run, log kode HTTP tanpa key atau isi respons mentah.
- `main.py`: `--resume-metadata` hanya memilih `needs_metadata` dari manifest;
  memakai QA lama dan tidak melakukan tracing. Aset `ready`/`needs_review` tidak
  disentuh. Metadata manual tetap didukung.
- README dan tes regresi diperbarui. Tidak ada perubahan requirements.

Perilaku aman tetap dipertahankan: metadata dummy tidak ditanam ke SVG/EPS,
aset pending tidak masuk CSV ready dan tidak diarsipkan, hash tracing dan nama
output tetap, serta caption stripping tetap opt-in.

## Cara menerapkan di iMac

Unduh `metadata_quota_fix.zip` ke folder Downloads dan ekstrak. Folder
`metadata_quota_fix` berisi patch, panduan ini, dan `updated_files/` untuk review.
Dari folder repo, setelah memastikan berada di versi v3.0 yang sesuai, jalankan:

```bash
git apply --check ~/Downloads/metadata_quota_fix/metadata_quota_fix.patch
```

Hanya jika pemeriksaan tersebut sukses, jalankan:

```bash
git apply ~/Downloads/metadata_quota_fix/metadata_quota_fix.patch
python main.py --help
```

Jika check gagal, jangan paksa. Periksa perubahan lokal dengan `git diff` lalu
cocokkan bagian yang bentrok. Patch hanya mengubah file yang tercantum di atas
beserta tes; file requirements Catalina, input, output, cache, dan tracking tidak
diubah oleh pemasangan patch. ZIP memuat salinan file yang diperbarui untuk review
atau penggantian manual jika diperlukan; utamakan patch untuk menjaga edit lokal.

Environment `GEMINI_API_KEY` yang sudah dipasang tetap digunakan. Jalankan:

```bash
export GEMINI_MODEL="gemini-3.5-flash"
export GEMINI_FALLBACK_MODELS="gemini-flash-latest,gemini-3.7-flash"
python main.py --resume-metadata --metadata-workers 1 --ai-rpm 5 --no-archive
```

Perintah ini memilih lima aset `needs_metadata` jika manifest masih sesuai log
terakhir. Tujuh ready dan tiga needs_review dilewati. Angka hasil resume menghitung
aset yang diproses pada run tersebut, bukan total seluruh portofolio.

OpenRouter opsional: isi `OPENROUTER_API_KEY` di terminal lokal. Pilih
`OPENROUTER_MODEL` dengan ID model vision yang tersedia pada akun tersebut, atau
biarkan tidak disetel untuk discovery model gratis yang menerima gambar. Jangan
mengisi ID contoh literal. Tanpa key OpenRouter, fallback hanya antar model Gemini.

## Batasan

- `limit: 20` dapat berupa batas harian. Periksa quotaId lengkap atau AI Studio.
  Retry 50 detik tidak akan menyelesaikan kuota harian yang sudah habis.
- Retry terbatas; cooldown/permanent skip berlaku selama proses berjalan.
  Jika seluruh provider tidak tersedia, status tetap needs_metadata untuk dilanjutkan.
- Tidak menjamin semua batch selesai dalam satu run saat quota/capacity habis.
- 404 menyatakan model tidak tersedia untuk request/akun itu; tidak membuktikan
  model pensiun global.
- Mengganti model/daftar cadangan mengubah kunci cache metadata. Cache tracing
  tidak berubah. Mode resume tidak meregenerasi metadata aset ready.
- Sudah diuji lokal dengan respons API simulasi. Tidak diuji live memakai API key
  pengguna atau dijalankan langsung di macOS Catalina. Tidak menambah dependency.
- Hasil suite: 45 tes lulus, termasuk retry/fallback, pacing antar worker, resume,
  serta regresi tracing/export/arsip. Patch diperiksa terhadap basis `aa6b29d`.

Rujukan:
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/troubleshooting
- https://openrouter.ai/docs/api/reference/errors-and-debugging
