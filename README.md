# 🍢 Kantin Tycoon

Game idle/manajemen kantin sekolah yang berjalan di browser. Dibuat untuk mengisi waktu luang: kelola menu, harga, stok, dan karyawan, lalu lihat antrean siswa bergerak di kantinmu.

Satu file HTML (JavaScript murni, tanpa framework), dengan server Python opsional untuk akun dan simpanan di file SQLite.

## Menjalankan

### Cara cepat (tanpa akun)
Buka `kantin-tycoon.html` dengan klik dua kali. Simpanan tersimpan di browser (IndexedDB).

### Dengan akun dan file simpanan SQLite
Butuh Python 3 (tanpa pustaka tambahan).

```bash
python server.py
```

Atau klik dua kali `jalankan.bat` di Windows. Browser terbuka di `http://127.0.0.1:8765`.

- Simpanan masuk ke `kantin-tycoon.sqlite` di folder yang sama.
- Daftar akun pertama kali, atau pilih "Main tanpa akun".
- Opsi: `python server.py --port 9000 --no-browser`

### Online (gratis)
Lihat [docs/pasang-pythonanywhere.md](docs/pasang-pythonanywhere.md) untuk memasangnya di PythonAnywhere.

## Cara bermain

| Tombol | Fungsi |
|---|---|
| `Spasi` | Layani pelanggan |
| `P` | Jeda / lanjut |
| `1` `2` `3` `4` | Kecepatan ×1 / ×2 / ×5 / ×10 |
| `+` / `-` | Naikkan / turunkan kecepatan |
| `Esc` | Layar darurat (menampilkan dokumen palsu) |

Inti permainan:

- **Hari sekolah 07:00-15:00.** Jam pelajaran sepi, jam istirahat ramai.
- **6 menu** dengan harga yang kamu atur sendiri. Harga naik berarti untung per porsi naik, tapi minat pembeli turun.
- **Stok, karyawan, dan level dapur** menentukan seberapa banyak pelanggan yang terlayani.
- **Kepuasan** memengaruhi jumlah pengunjung. Antrean panjang dan stok habis membuat pelanggan kabur.
- **Event acak:** hujan, sidak guru, pesanan katering, video viral, harga bahan naik, dan lainnya.
- **Cabang** dan **Naik Kelas** (prestise dengan toko Reputasi) untuk progres jangka panjang.
- **Laporan** per menu, per hari, dan per jam.

## Penyimpanan

| Mode | Lokasi data | Akun |
|---|---|---|
| `jalankan.bat` / `server.py` | `kantin-tycoon.sqlite` | ya |
| Online (PythonAnywhere) | file SQLite di server (`KT_DB`) | ya |
| Klik dua kali file HTML | IndexedDB browser | tidak |

- Slot simpanan ganda, cadangan otomatis tiap 5 menit (maks. 10 per slot).
- Ekspor/impor kode simpanan di tab **Pengaturan**.
- Kantin tetap jalan sampai 8 jam saat tab ditutup.
- Server menyalin database ke `kantin-tycoon.sqlite.bak` setiap kali dimulai.

## Keamanan

- Secara bawaan server hanya menerima koneksi dari `127.0.0.1`. Di hosting publik, host diizinkan lewat `KT_HOSTS`, cookie diberi flag `Secure`, dan login/pendaftaran dibatasi per IP.
- Kata sandi di-hash dengan PBKDF2-SHA256 (salt acak); sesi lewat cookie `HttpOnly` + `SameSite=Strict`.
- Akun lain tidak bisa melihat atau mengubah slotmu.
- File `*.sqlite` ada di `.gitignore`. Jangan di-commit, karena berisi akun dan simpanan.

## Struktur

```
kantin-tycoon.html   # game lengkap (UI, simulasi, penyimpanan)
server.py            # server lokal + aplikasi WSGI: akun + simpanan SQLite
wsgi.py              # titik masuk untuk hosting publik
jalankan.bat         # peluncur Windows
docs/                # panduan pasang online dan laporan keseimbangan ekonomi
```

## Catatan

- Tampilan memakai font Inter dari Google Fonts (mirip Helvetica); tanpa internet jatuh ke Helvetica/Arial.
- Keseimbangan ekonomi jangka panjang sudah disimulasikan; hasil dan angka yang diubah ada di [docs/laporan-keseimbangan.md](docs/laporan-keseimbangan.md). Simulasi tidak mencakup klik manual.
