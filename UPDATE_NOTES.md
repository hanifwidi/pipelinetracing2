# Pembaruan pipeline 3.0

Basis: `cf4c9b43593cbeaa4c056be92398680a9dcceade`.

## Perbaikan utama

- SVG mempertahankan viewBox/rasio, dengan artboard 15–65 MP yang dapat dipilih.
- EPS memakai Inkscape dan pemeriksaan Ghostscript bila terpasang. Konversi
  pixel ke point menjaga ukuran artboard; metadata EPS menggunakan ExifTool.
- Optimasi XML dapat diserialisasikan, path tidak kehilangan transform/urutan,
  dan penggabungan hanya dilakukan bila aman secara konservatif.
- Preview dan QA membandingkan hasil vektor dengan input tracing. Penghapusan
  caption grid menjadi pilihan eksplisit.
- Worker tracing dan metadata terpisah, limit API/retry dibatasi, cache tracing
  dapat digunakan ulang, output memakai hash agar nama tidak bertabrakan.
- CSV ditulis satu proses, diperbarui per filename, memakai lock dan replace
  atomik. Aset belum lengkap tidak dianggap siap atau otomatis diarsipkan.
- Tracking mempertahankan histori, menghitung download terbaru dengan benar,
  menyimpan observasi bertanggal, menghindari judul ambigu, dan menunggu data
  memadai sebelum menyarankan perluasan produksi.
- Skrip repair, archive, konversi EPS, importer, serta dokumentasi diselaraskan.

## Verifikasi

Perintah: `python -m pytest -q`
Hasil akhir: **27 passed**, tanpa tes dilewati pada lingkungan pengujian.

Pengujian mencakup VTracer sungguhan, render Inkscape, pembacaan EPS melalui
Ghostscript, portrait/landscape, transfer konfigurasi multiprocessing spawn,
metadata manual, cache, input rusak, nama file ganda, pemrosesan ulang, retry
HTTP tiruan, integritas CSV, dan histori tracking.

API AI langsung dan upload Adobe belum diuji. ExifTool tidak tersedia di
lingkungan uji: jalur tanpa ExifTool diverifikasi tidak merusak EPS dan tetap
menyediakan metadata CSV. Pembacaan metadata tertanam EPS melalui Contributor
Portal perlu diperiksa pada instalasi/akun pengguna.

Panduan penerapan: `MIGRATION.md`. Pilihan CLI: `README.md`.
