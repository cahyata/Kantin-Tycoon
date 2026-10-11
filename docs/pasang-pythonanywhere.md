# Memasang Kantin Tycoon di PythonAnywhere (gratis)

Hasilnya: `https://NAMAANDA.pythonanywhere.com`, dengan akun dan simpanan SQLite yang permanen.
Ganti `NAMAANDA` dengan nama pengguna PythonAnywhere Anda di semua langkah.

## 1. Daftar dan ambil kode
1. Buat akun gratis ("Beginner") di https://www.pythonanywhere.com. Nama pengguna menjadi subdomain.
2. Buka tab **Consoles**, mulai **Bash**, lalu:
   ```bash
   git clone https://github.com/cahyata/kantin-tycoon
   ```

## 2. Buat web app
1. Tab **Web** > **Add a new web app** > domain gratis bawaan > **Manual configuration** > pilih Python 3.10 atau lebih baru.
2. Di bagian **Code**, "Source code": `/home/NAMAANDA/kantin-tycoon`
3. Klik file WSGI configuration, **hapus isinya**, ganti dengan:
   ```python
   import os, sys
   os.environ['KT_HOSTS'] = 'NAMAANDA.pythonanywhere.com'
   os.environ['KT_SECURE'] = '1'
   os.environ['KT_TRUST_PROXY'] = '1'
   os.environ['KT_DB'] = '/home/NAMAANDA/kantin-data/kantin-tycoon.sqlite'
   os.makedirs('/home/NAMAANDA/kantin-data', exist_ok=True)
   sys.path.insert(0, '/home/NAMAANDA/kantin-tycoon')
   from wsgi import application
   ```
4. Bagian **Security**: nyalakan **Force HTTPS**.
5. Klik **Reload**, lalu buka `https://NAMAANDA.pythonanywhere.com`.

Database sengaja disimpan di luar folder git (`kantin-data`) supaya `git pull` tidak menyentuhnya.

## 3. Pembaruan
```bash
cd ~/kantin-tycoon && git pull
```
lalu **Reload** di tab Web.

## 4. Perawatan
- Akun gratis harus diperpanjang dengan menekan tombol **Run until 3 months from today** di tab Web kira-kira tiap 3 bulan (cek aturan terbaru di situs PythonAnywhere).
- Cadangan: unduh `kantin-data/kantin-tycoon.sqlite` lewat tab **Files** sesekali.

## Pengaturan (variabel lingkungan)
| Nama | Fungsi |
|---|---|
| `KT_HOSTS` | Daftar host yang diizinkan, pisah koma. Wajib di hosting publik. |
| `KT_SECURE` | `1` = cookie sesi diberi flag `Secure` (wajib dengan HTTPS). |
| `KT_TRUST_PROXY` | `1` = ambil IP klien dari `X-Real-IP` proxy hosting, untuk batas percobaan. |
| `KT_DB` | Lokasi file SQLite. |

Tanpa variabel ini, `python server.py` berjalan lokal seperti biasa.

## Batas yang berlaku di mode publik
- Login: 5 kegagalan per nama pengguna mengunci 30 detik; maksimal 30 percobaan per IP per 10 menit.
- Pendaftaran: maksimal 5 akun per IP per jam.
- Penghitung ini ada di memori proses dan ikut reset saat Reload.
