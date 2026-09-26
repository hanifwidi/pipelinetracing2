# Vector Factory V3

Pipeline Python untuk mengubah PNG/JPEG/WEBP menjadi SVG dan EPS, memeriksa
hasil render, menyiapkan metadata, dan mencatat performa aset Adobe Stock.
Hasil pemeriksaan otomatis tetap perlu ditinjau secara visual sebelum upload.

## Instalasi

Gunakan Python 3.10+ dan Inkscape. Ghostscript menambahkan pemeriksaan EPS oleh
interpreter; ExifTool diperlukan hanya jika ingin menanam metadata ke EPS.
Tanpa ExifTool, judul/keyword EPS tetap tersedia melalui CSV.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows: aktivasi dengan `.venv\Scripts\activate`.
Untuk Inkscape macOS, path `/Applications/Inkscape.app/Contents/MacOS/inkscape`
dideteksi otomatis. Alternatif: atur `INKSCAPE_PATH` di `config.py`.

Dependency OCR (`easyocr`) dan geometri lama (`shapely`) bersifat opsional.
Modul lama tersebut tidak dijalankan otomatis oleh pipeline utama.

## Menjalankan

Simpan gambar di `input/`, lalu jalankan dari folder proyek:

```bash
python main.py --workers 2 --metadata-workers 1 --eps
```

Untuk aset berupa lembar ikon flat dengan latar putih polos, gunakan profil ikon
secara eksplisit:

```bash
python main.py --asset-type icon-sheet --workers 2 --metadata-workers 1 --eps --no-archive
```

Profil ini membuat background dan ruang kosong putih menjadi transparan, lalu
menelusuri tiap warna foreground sebagai compound path agar lubang roda, handle,
dan detail serupa tetap kosong. Artboard default adalah 16 MP dan dibatasi
4000 px per sisi. `icon` menerima aset tunggal dengan sisi minimal 50 px;
`icon-sheet` memakai minimal 1000 px per sisi. Input bergradasi, bertekstur,
berlatar selain putih, atau memiliki detail putih yang ambigu ditahan sebagai
`needs_review`, sehingga pipeline tidak menebak bagian yang harus transparan.
Gunakan profil `illustration` (default) untuk gambar yang memang membutuhkan
bidang putih sebagai bagian objek.

Tanpa API key, SVG/EPS dan preview tetap dibuat dengan status `needs_metadata`.
Input yang belum siap tetap tersedia untuk diproses ulang.

Metadata AI memakai Gemini lalu OpenRouter jika key masing-masing tersedia:

```bash
export GEMINI_API_KEY="isi-key-di-terminal-lokal"
# Opsional:
export OPENROUTER_API_KEY="isi-key-di-terminal-lokal"
export GEMINI_MODEL="gemini-3.5-flash"
# Urutan cadangan dapat diganti; isi kosong untuk menonaktifkan fallback model:
export GEMINI_FALLBACK_MODELS="gemini-flash-latest,gemini-3.7-flash"
# Pilih model vision yang tersedia pada akunmu bila dibutuhkan:
# export OPENROUTER_MODEL="provider/model"
python main.py --workers 2 --metadata-workers 1 --ai-rpm 10 --eps
```

Key dibaca dari environment, bukan otomatis dari file `.env`. Jangan memasukkan
key ke source atau Git. Preview gambar dikirim ke provider yang dikonfigurasi.
Model dan kuota mengikuti akun provider; ketersediaan API tidak diasumsikan.

Default model di atas mengikuti model yang berhasil diuji pengguna pada akun ini;
bukan jaminan akses untuk semua akun. Tidak ada pencarian model Gemini otomatis.
HTTP 404 melewati model tersebut selama proses berjalan. HTTP 401/403 menghentikan
provider tersebut untuk run ini. Retry 429/5xx membaca `Retry-After` (detik/tanggal),
`google.rpc.RetryInfo.retryDelay`, dan pesan `retry in Xs`; jeda server tidak
dipotong menjadi 30 detik. Tanpa petunjuk server, retry memakai exponential backoff.
Default dua retry setelah percobaan awal, dengan anggaran jeda retry 180 detik
per model/request (`AI_RETRIES`, `AI_MAX_RETRY_WAIT` di `config.py`). Jika petunjuk
jeda melebihi anggaran, request tidak diulang lebih awal; coba fallback yang tersedia.

Metadata worker default satu; request ke setiap provider diserialkan dan semua
model provider tersebut berbagi pacing `--ai-rpm`. Menambah worker tidak menaikkan
batas RPM. Pacing hanya mencakup proses ini, bukan aplikasi lain di project API sama.
Kuota harian atau kuota nol yang teridentifikasi dari `quotaId`/`quotaValue`
dihentikan untuk run ini. Angka `limit: 20` saja tidak membuktikan kuota per menit.
Cooldown kuota project dibagi antar model; kuota dengan dimensi model berlaku ke
model itu. OpenRouter dicoba setelah Gemini tidak berhasil jika key dikonfigurasi.
Tanpa `OPENROUTER_MODEL`, discovery hanya memilih maksimal dua model `:free`
yang menyatakan menerima gambar. Hasil tetap bisa pending jika tidak ada kapasitas.

Untuk melanjutkan hanya aset yang metadata-nya belum lengkap:

```bash
python main.py --resume-metadata --metadata-workers 1 --ai-rpm 5 --no-archive
# Bisa digabungkan dengan CSV manual:
python main.py --resume-metadata --metadata-csv manual_metadata.csv --no-archive
```

Mode ini membaca `tracking/pipeline_manifest.json`, memilih status `needs_metadata`,
dan memakai SVG, preview, serta QA yang tersimpan. Tidak tracing ulang, tidak
memproses `ready`/`needs_review`, dan tidak membutuhkan isi folder input untuk
memilih aset. Preview yang hilang dirender ulang dengan Inkscape. SVG/EPS atau QA
yang hilang menghasilkan error dan mempertahankan status pending; lakukan run
tracing normal untuk memperbaikinya. `--no-archive` mempertahankan input; tanpa
flag itu, hanya input asli yang hash-nya masih cocok boleh diarsipkan saat ready.
Opsi tracing (grid/caption/ukuran/EPS) tidak mengubah artefak dalam mode resume.
Status ready tetap bergantung pada QA, bukan hanya metadata sukses.

Alternatif tanpa API: siapkan CSV judul/keyword yang sudah diperiksa:

```csv
Filename,Title,Keywords,Category
contoh.png,Black geometry icon set,"geometry,shape,square,circle,icon,black",8
```

```bash
python main.py --metadata-csv manual_metadata.csv --workers 2 --eps
```

`Filename` dapat memakai nama SVG output atau nama input yang unik dalam batch.
Untuk input bernama sama di beberapa subfolder, gunakan nama SVG output lengkap.

Opsi tambahan:

```bash
# Hapus caption hanya untuk gambar yang memang berupa grid 4 baris x 4 kolom:
python main.py --strip-captions --grid 4x4
# Artboard mengikuti rasio asli, dengan luas total 25 MP:
python main.py --target-mp 25 --max-size 2048
# Pertahankan input walaupun hasil sudah siap:
python main.py --no-archive
# Bangun ulang tracing atau metadata jika diperlukan:
python main.py --force --force-metadata
```

Penghapusan caption OFF secara default. Optimasi SVG konservatif ON secara
default. `--skip-opt` atau `SKIP_OPT=1` menonaktifkannya untuk diagnosis.
`SKIP_ARCHIVE=1` masih didukung. Konfigurasi worker dikirim secara eksplisit
sehingga opsi juga berlaku pada multiprocessing `spawn` di macOS/Windows.

## Alur aktif dan keluaran

1. Baca/resize gambar, komposit transparansi di atas putih; hapus caption bila diminta.
2. Analisis kompleksitas pada sampel kecil; profil ikon memakai trace mask biner
   per warna, sedangkan profil ilustrasi memakai VTracer warna biasa.
3. Optimasi path konservatif, simpan `viewBox`, pertahankan rasio, dan atur artboard.
4. Render SVG ke PNG dengan Inkscape, bandingkan warna/posisi dengan input tracing.
5. Ekspor EPS opsional melalui Inkscape. Ukuran EPS dinormalisasi ke satuan point
   agar angka luas artboard tidak menyusut saat konversi dari SVG pixel.
6. Ambil metadata relevan dari preview, validasi, tanam ke SVG/EPS jika tersedia.
7. Tulis CSV dan checkpoint dari satu proses induk. Arsipkan hanya status `ready`.

| Lokasi | Isi |
|---|---|
| `output_svg/`, `output_eps/` | File vektor; nama ditambah hash isi untuk menghindari benturan |
| `metadata.csv` di setiap folder output | Metadata aset yang lolos pemeriksaan dan memiliki metadata AI/manual |
| `review.csv` di setiap folder output | Draft yang masih perlu metadata atau pemeriksaan visual |
| `previews/` | Preview PNG dan `.qa.json` berisi hasil pemeriksaan |
| `tracking/pipeline_manifest.json` | ID, sumber, output, status, dan hasil setiap tahap |
| `tracking/production_log.csv` | Identitas, status produksi/submission, download dan royalti yang diketahui |
| `tracking/download_history.csv` | Observasi download kumulatif bertanggal |
| `input_processed/` | Input yang berhasil diselesaikan dan diarsipkan |
| `quarantine/` | Salinan input gagal dan alasan kegagalan; sumber dipertahankan |

Status: `ready`, `needs_metadata`, `needs_review`, atau `failed`.
`ready` berarti lolos pemeriksaan pipeline, bukan persetujuan Adobe.
Exit code 1 menunjukkan kegagalan teknis; draft yang perlu pemeriksaan tetap
tercatat jelas pada ringkasan dan manifest walaupun proses selesai dengan code 0.

Tracing dan metadata memiliki cache terpisah. Menjalankan ulang input yang sama
memakai cache tracing, sehingga kegagalan API tidak mengharuskan tracing ulang.
Cache metadata menyertakan versi prompt. CSV diperbarui berdasarkan filename,
bukan ditambah berulang. Satu workspace hanya menerima satu pipeline/repair
sekaligus; CSV tracking juga memakai lock dan penggantian file secara atomik.

Batas teknis default ilustrasi: artboard 15–65 MP, file maksimal 45 MB, tanpa
gambar raster tertanam. Profil ikon memakai batas sisi dan maksimal 16 MP seperti
yang dijelaskan di atas. Preview juga memeriksa perbedaan warna, pergeseran area
artwork, serta transparansi tiap foreground dan negative-space component.
Halusnya detail kecil, ketepatan objek, dan kelayakan komersial tetap perlu
pemeriksaan manusia. Penggabungan path warna sama default OFF; jika diaktifkan,
hanya path bersebelahan dengan atribut identik dan area yang terbukti terpisah
akan digabung. Transform dan urutan lapisan dipertahankan.

## Tracking niche

```bash
python init_tracking.py
python import_downloads.py adobe_scrape_20260926.csv
python track.py report
python track.py report --json
```

`init_tracking.py` aman dijalankan ulang: hanya menambah aset baru, mempertahankan
status accepted/rejected, catatan, royalti, serta kolom tambahan. File yang baru
dibuat tidak otomatis dianggap sudah disubmit.

Importer menerima kolom minimum `title,downloads,last_seen`. Format tanggal:
`YYYY-MM-DD` atau timestamp ISO yang diawali tanggal tersebut. Kolom opsional:
`filename`, `adobe_asset_id` (alias `asset_id`/`id`), `status`, `accepted_date`,
`royalty_usd`. Pencocokan memakai ID Adobe yang sudah dikenal, lalu filename,
lalu judul yang unik. Judul ambigu dilewati dan dilaporkan. Pemetaan ID dapat
dilengkapi pada production log untuk mengatasi judul yang sama.

`in_review=0` sendiri tidak cukup untuk menyimpulkan accepted. Tanggal accepted
hanya diisi dari data yang eksplisit. Tanggal pertama terlihat accepted disimpan
terpisah. Observasi lama tetap masuk histori tanpa menimpa hitungan terbaru.
Penurunan hitungan pada tanggal observasi yang sama ditandai invalid untuk
ditinjau, agar scrape lama tidak mengganti hitungan yang lebih tinggi.
Royalti hanya dibaca jika kolom `royalty_usd` diberikan secara eksplisit;
pendapatan tidak diperkirakan dari jumlah download.

Laporan memakai `dl_latest` untuk total download. Angka per aset per 30 hari
memerlukan dua observasi terpisah sekitar 30 hari dan data terbaru; angka itu
tidak dihitung dari tebakan tanggal terbit. Rekomendasi menunggu sedikitnya 10
aset dengan data memadai. `EXPAND TEST` adalah heuristik untuk percobaan berikutnya,
bukan prediksi pendapatan. Kolom lama `dl_30d/60d/90d` dipertahankan untuk kompatibilitas.

## Pemeliharaan

```bash
python repair_metadata.py                  # Hanya perbaiki metadata output yang ada
python repair_metadata.py --force          # Perbarui metadata AI/cache
python convert_eps_batch.py                # Konversi SVG yang sudah ada
python inject_eps_xmp.py                   # Perlu ExifTool
python archive_old_inputs.py               # Hanya arsipkan aset berstatus ready
```

`archive_old_inputs.py --all` secara eksplisit mengarsipkan semua gambar input,
termasuk yang belum diproses. Repair output legacy tanpa catatan QA menempatkan
metadata pada `review.csv`; tidak menganggap file lama otomatis lolos QA.

## Pengujian

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tes mencakup rendering VTracer/Inkscape, validitas EPS dengan Ghostscript,
transform path, rasio portrait/landscape, retry API tiruan, cache, CSV idempotent,
tracking historis, input rusak, dan batch multiprocessing `spawn`. Tes API tidak
menggunakan key asli. Tes renderer dilewati jika aplikasi terkait belum terpasang.

Panduan Adobe yang mendasari batas default:
- [Persyaratan teknis vektor](https://helpx.adobe.com/stock/contributor/submit-your-content/submit-vectors/technical-requirements-for-vector-submissions.html)
- [Judul dan keyword](https://helpx.adobe.com/stock/contributor/content-policies-guidelines/metadata/tips-effective-titles-keywords.html)

Lihat `MIGRATION.md` untuk menerapkan pembaruan ke instalasi lama.
