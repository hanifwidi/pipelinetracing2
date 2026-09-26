# Memasang pembaruan dari Pipeline 3.0 / 3.1

Paket pembaruan hanya berisi source, konfigurasi, dokumentasi, dan tes.
Folder gambar, output, cache, log, dan catatan produksi tidak disertakan.

1. Hentikan batch yang sedang berjalan.
2. Ekstrak ZIP dan salin berkas dengan struktur folder yang sama ke folder proyek.
   Jika memakai Git dan checkout berawal dari commit `a1328c0`, alternatifnya
   jalankan `git apply --check pipelinetracing2_icon_tracing_update.patch` lalu
   `git apply pipelinetracing2_icon_tracing_update.patch`. Pilih satu cara.
3. Cocokkan pengaturan lokal pada `config.py` dengan versi baru bila sebelumnya
   file itu sudah dikustomisasi. Pembaruan ini tidak menambah dependency; pada
   instalasi Catalina gunakan pin `requirements.txt` yang sudah ada. Instal ulang
   hanya bila environment belum mengikuti file tersebut:

```bash
pip install -r requirements.txt
```

4. Pastikan Inkscape terpasang. Ghostscript memvalidasi EPS dengan interpreter;
   ExifTool bersifat opsional untuk metadata tertanam EPS.
5. Coba beberapa gambar dahulu menggunakan `--no-archive`:

```bash
python main.py --workers 2 --metadata-workers 1 --eps --no-archive
```

Untuk lembar ikon flat seperti sampel geometris, jalankan pengujian terpisah:

```bash
python main.py --asset-type icon-sheet --workers 1 --metadata-workers 1 \
  --metadata-csv manual_metadata.csv --eps --no-archive
```

`--asset-type` masuk ke signature cache. Aset yang pernah ditrace pada profil
ilustrasi akan dibangun ulang ketika dijalankan dengan profil ikon. Salin input
yang sudah dipindahkan ke `input_processed/` kembali ke `input/` bila ingin
meregenerasi SVG lama; output lama tidak diubah otomatis.

Periksa `previews/`, `.qa.json`, serta ringkasan ready/needs_metadata/needs_review.
Tanpa API key, status needs_metadata memang diharapkan. Untuk menyelesaikannya,
isi environment API atau gunakan `--metadata-csv` berisi metadata yang ditinjau.

## Perubahan perilaku

- `harden_for_adobe` mempertahankan rasio dan koordinat dengan `viewBox`.
- Nama output baru menggunakan `nama__hash.svg/eps`. Dua gambar dengan nama sama
  tidak saling menimpa. Isi identik dalam batch diproses sekali.
- Output lama dengan nama tanpa hash tetap ada. Jangan mengupload kedua versi
  sebagai aset berbeda hanya karena nama filenya berubah; cocokkan dengan aset
  yang sudah pernah disubmit melalui production log/ID Adobe.
- Optimasi SVG aktif secara konservatif; penghapusan caption menjadi opt-in.
- Default worker maksimal empat; permintaan AI dibatasi terpisah.
- Aset yang perlu metadata/review tidak otomatis diarsipkan dan tidak masuk CSV
  upload-ready. Input asli tetap ada; tracing berikutnya memakai cache.
- Cache metadata lama tidak dipakai sebagai hasil prompt baru. Pembentukan ulang
  metadata hanya dilakukan saat ada key aktif dan aset diproses/diperbaiki.
- `init_tracking.py` mempertahankan histori. Importer menyimpan observasi kumulatif
  bertanggal, tidak mengarang tanggal accepted dari waktu proses lokal.
- Script XMP lama diganti writer ExifTool. File EPS tidak lagi disisipi XML mentah.
- `repair_metadata.py` tidak men-truncate seluruh metadata.csv atau menambahkan
  baris untuk SVG yang tidak ada. Output legacy tanpa QA tetap perlu ditinjau.
- Profil `icon`/`icon-sheet` memverifikasi alpha melalui `expected_alpha.png` di
  cache dan menahan hasil yang masih memiliki bidang putih pada background atau
  lubang. Profil ini bersifat opt-in karena penghapusan warna putih tidak aman
  untuk ilustrasi umum.

Ketersediaan model AI dan pembacaan metadata oleh Adobe Contributor Portal perlu
diverifikasi pada akun pengguna. Implementasi dan tes tidak melakukan upload
ke Adobe Stock atau memanggil API AI berbayar.
