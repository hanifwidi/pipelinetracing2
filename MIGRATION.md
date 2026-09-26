# Memasang pembaruan dari versi cf4c9b4

Paket pembaruan hanya berisi source, konfigurasi, dokumentasi, dan tes.
Folder gambar, output, cache, log, dan catatan produksi tidak disertakan.

1. Hentikan batch yang sedang berjalan.
2. Salin isi folder `updated-files/` dari paket ke folder proyek dengan struktur
   folder yang sama. Jika memakai Git, alternatifnya jalankan
   `git apply --check changes.patch` lalu `git apply changes.patch` pada checkout
   commit `cf4c9b4` yang bersih. Pilih salah satu cara penerapan.
3. Cocokkan pengaturan lokal pada `config.py` dengan versi baru bila sebelumnya
   file itu sudah dikustomisasi. Instal ulang dependency:

```bash
pip install -r requirements.txt
```

4. Pastikan Inkscape terpasang. Ghostscript memvalidasi EPS dengan interpreter;
   ExifTool bersifat opsional untuk metadata tertanam EPS.
5. Coba beberapa gambar dahulu menggunakan `--no-archive`:

```bash
python main.py --workers 2 --metadata-workers 1 --eps --no-archive
```

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

Ketersediaan model AI dan pembacaan metadata oleh Adobe Contributor Portal perlu
diverifikasi pada akun pengguna. Implementasi dan tes tidak melakukan upload
ke Adobe Stock atau memanggil API AI berbayar.
