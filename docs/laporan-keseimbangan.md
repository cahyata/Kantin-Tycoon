# Laporan simulasi keseimbangan ekonomi

Dibuat dengan menyalin logika `step`, harga, upgrade, cabang, event, dan Naik Kelas dari `kantin-tycoon.html` ke harness Node, lalu dijalankan dengan bot pemain (restock otomatis, beli upgrade termurah, event pilihan bawaan, 3-5 seed acak). Angka di bawah adalah rata-rata, bukan hasil satu permainan. Simulasi tidak menyertakan klik manual.

## Temuan

1. **Karyawan dan level dapur jebakan di awal-menengah.** Bot "beli termurah" yang rajin beli karyawan/level mencapai omzet kumulatif Rp 168 jt di hari 90. Bot yang tidak membelinya sama sekali mencapai Rp 912 jt (5,4× lebih besar), walau 15% pelanggan kabur. Kapasitas melayani jarang jadi hambatan, permintaan yang jadi hambatan. (Tidak diubah di PR ini; kandidat berikutnya: turunkan basis biaya karyawan 1,6 atau naikkan kapasitas dasar per karyawan.)
2. **Harga acuan hampir optimal tapi sedikit rendah.** Omzet hari 45 menurut pengali harga: ×0,8 = 1,06e8, ×1,0 = 1,78e8, ×1,2 dan ×1,3 = 2,34e8 (puncak), ×1,5 = 1,82e8, ×1,8 = 6,5e7. Pemain yang menaikkan harga 20-30% untung ~30% lebih banyak, kepuasan turun dari 86 ke 81-85. Ini bentuk kurva yang sehat, tidak diubah.
3. **Cabang macet di sekitar cabang ke-8.** Biaya ×3,5 per cabang tapi manfaat +0,6 tetap, jadi tanpa Naik Kelas pendapatan datar di ~Rp 8 jt/hari setelah hari ~900 sementara uang menumpuk Rp 3e10 tanpa tempat pakai. **Diubah:** ×3,5 menjadi ×2,6.
4. **Naik Kelas lebih merugikan daripada menguntungkan.** Dengan rumus lama (akar pangkat tiga, +5% per Reputasi), Naik Kelas langsung saat dapat +1 Reputasi (sekitar hari 46) menghasilkan omzet seumur hidup Rp 2,1e9 di hari 400, sepuluh kali lebih kecil dari yang tidak pernah Naik Kelas (Rp 2,07e10). Menunggu pun kalah (1,45e10). Tiap putaran butuh ~45 hari untuk membangun ulang, sedangkan bonusnya tak sebanding.

## Perubahan di PR ini

| Parameter | Lama | Baru |
|---|---|---|
| Biaya cabang | 3e6 × 3,5^n | 3e6 × 2,6^n |
| Reputasi per putaran | ∛(omzet / 2e8) | √(omzet / 2e8) |
| Bonus pengunjung per Reputasi | +5% | +15% |

Hasil simulasi 400 hari (rata-rata 3 seed), strategi "Naik Kelas bila Reputasi baru ≥ total Reputasi + 2":

| | Omzet seumur hidup | Omzet/hari (40 hari terakhir) |
|---|---|---|
| Lama, tidak pernah Naik Kelas | 2,07e10 | 7,3e7 |
| Lama, Naik Kelas teratur | 1,45e10 | 3,8e7 |
| Baru, tidak pernah Naik Kelas | 2,60e10 | 9,0e7 |
| Baru, Naik Kelas teratur | 2,99e10 | 2,49e8 |
| Baru, Naik Kelas tiap +1 Reputasi | 3,1e9 | 1,3e7 |

Naik Kelas teratur kini mengalahkan tidak pernah, sementara Naik Kelas sesering mungkin tetap tidak menguntungkan (anti-spam).

Catatan: simulasi bergantung pada bot dan event acak (variansi tinggi antar seed). Angka ini arah, bukan nilai pasti. Simpanan lama tetap valid karena hanya rumus yang berubah.
