# Profiling Fitur Kegiatan

## Scope

Endpoint yang dianalisis:

- `GET /api/kegiatan/`
- `GET /api/kegiatan/?status=SEDANG_BERJALAN`
- `GET /api/kegiatan/{pk}/`

Endpoint ini relevan karena response kegiatan menggabungkan banyak entitas:
`Periode`, `KegiatanKaprodiModel`, `KegiatanGuruBesarModel`,
`SuratPernyataanModel`, `LaporanKegiatan`, `KaprodiModel`, dan
`GuruBesarModel`.
 
### Bukti Sentry

<img width="1500" height="873" alt="Screenshot 2026-04-23 021032" src="https://github.com/user-attachments/assets/becf1116-fd9c-4b5e-bb26-e168b148b61d" />
<img width="1491" height="832" alt="image" src="https://github.com/user-attachments/assets/fec63923-4a15-4667-abee-15df6a9499ee" />
<img width="1526" height="868" alt="Screenshot 2026-04-23 011834" src="https://github.com/user-attachments/assets/edd78082-112e-439c-8520-dc1ba903f6c3" />

| Endpoint | Issue | Events | Users | First Seen | Last Seen | Key Finding |
| --- | --- | ---: | ---: | --- | --- | --- |
| `/api/kegiatan/` | `PYTHON-DJANGO-W` N+1 Query | 181 | 5 | 9 hari lalu | 2 hari lalu | Query berulang pada `laporan_laporankegiatan` |
| `/api/kegiatan/{pk}/` | `PYTHON-DJANGO-1E` N+1 Query | 63 | 7 | 1 hari lalu | 3 jam lalu | Request detail juga terdeteksi sebagai N+1 candidate |

Catatan:

- `PYTHON-DJANGO-W` adalah bukti Sentry paling representatif untuk list kegiatan
  karena signature query-nya langsung membaca `laporan_laporankegiatan`.
- Sentry Autofix mengindikasikan view mengiterasi list `KegiatanModel` dan
  mengambil data terkait seperti `LaporanKegiatan` di dalam loop tanpa
  prefetching yang cukup.
- Issue lain yang menampilkan repeated span pada `silk_request` diperlakukan
  sebagai sinyal overhead profiler, bukan akar utama query domain.

### Bukti django-silk

<img width="1339" height="841" alt="Screenshot 2026-04-23 013230" src="https://github.com/user-attachments/assets/f4c3dac1-7742-4ab3-9eb5-f93bfe2a3627" />
<img width="1246" height="820" alt="Screenshot 2026-04-23 013253" src="https://github.com/user-attachments/assets/d8f636db-d630-48ef-ad6c-807244f6186f" />

| Endpoint | Status | Overall Time | Query Time | Query Count | Query Berat yang Terlihat |
| --- | ---: | ---: | ---: | ---: | --- |
| `/api/kegiatan/` | 200 | 7257 ms | 2658 ms | 44 | `documents_suratpernyataanmodel`, `kegiatan_kegiatankaprodimodel`, `authentication_gurubesarmodel`, `authentication_kaprodimodel`, `laporan_laporankegiatan`, `kegiatan_kegiatangurubesarmodel` |
| `/api/kegiatan/{pk}/` | 200 | 888 ms | 363 ms | 8 | `authentication_gurubesarmodel`, `laporan_laporankegiatan`, `kegiatan_kegiatankaprodimodel`, `kegiatan_kegiatanmodel`, `kegiatan_kegiatangurubesarmodel`, `documents_suratpernyataanmodel` |

### Bukti Local Profiling Script

<img width="1400" height="773" alt="Screenshot 2026-04-23 021553" src="https://github.com/user-attachments/assets/66b2e999-9ecd-407e-a5d3-a071dd682417" />

Baseline lokal dijalankan dengan isolated SQLite database:
`sqlite3:media/kegiatan_profiling_point1.sqlite3`.

Dataset:

| Parameter | Value |
| --- | ---: |
| Records | 25 kegiatan |
| Kaprodi per kegiatan | 2 |
| Guru besar per kegiatan | 3 |
| Repeat | 3 |
| Authenticated role | Admin |

Result:

| Endpoint | Avg Time | Avg Query Count | Max Duplicate SQL |
| --- | ---: | ---: | ---: |
| `/api/kegiatan/` | 1047.9 ms | 368.0 | 284 |
| `/api/kegiatan/?status=SEDANG_BERJALAN` | 887.0 ms | 368.0 | 284 |
| `/api/kegiatan/{pk}/` | 105.6 ms | 26.0 | 6 |

## Interpretasi

Evidence dari tiga sumber menunjukkan endpoint kegiatan sudah dapat diprofiling
dan memiliki indikasi query yang mahal:

- Sentry menemukan N+1 pada `/api/kegiatan/`, terutama akses berulang ke
  `laporan_laporankegiatan`.
- django-silk menunjukkan request list kegiatan menghabiskan 2658 ms hanya untuk
  query database dengan total 44 query.
- Script lokal menghasilkan baseline yang repeatable: list kegiatan menjalankan
  rata-rata 368 query untuk 25 kegiatan dengan 284 duplicate SQL.

Dengan demikian, point 1 sudah terpenuhi dan data ini dapat dipakai sebagai
baseline untuk point 2 dan point 3.

## Analisis Hasil Profiling

Point 2 berfokus pada analisis hasil profiling untuk menemukan akar masalah.
Temuan utama: endpoint list kegiatan masih melakukan akses relasi di dalam
proses serialisasi, terutama pada `laporan_kegiatan`.

### Query-to-Code Mapping

| Profiling Finding | Evidence | Lokasi Kode | Analisis |
| --- | --- | --- | --- |
| N+1 pada `laporan_laporankegiatan` | Sentry `PYTHON-DJANGO-W`; local script list endpoint `368` avg queries dan `284` duplicate SQL | `KegiatanView._get_base_queryset()` di `kegiatan/views_kegiatan.py`; `BaseKegiatanSerializer._get_laporan_kegiatan_relasi()` di `kegiatan/serializers.py` | Queryset list sudah prefetch `kaprodi_relasi`, `guru_besar_relasi`, dan `surat_pernyataan`, tetapi belum prefetch `laporan_kegiatan`. Saat serializer memproses setiap `KegiatanModel`, method `_get_laporan_kegiatan_relasi()` jatuh ke fallback `obj.laporan_kegiatan.all().order_by("-created_at")`, sehingga muncul query per kegiatan. |
| Query berulang ke `authentication_gurubesarmodel` saat serialisasi laporan | django-silk list/detail menampilkan query ke `authentication_gurubesarmodel`; local script detail masih `26` avg queries | `KegiatanLaporanSerializer.guru_besar_id` di `kegiatan/serializers.py` | Field `guru_besar_id` memakai `source="guru_besar.id"`. Akses ini berpotensi membaca objek relasi `guru_besar`, bukan hanya kolom FK `guru_besar_id`, jika `LaporanKegiatan` tidak diambil dengan `select_related("guru_besar")`. |
| Query relasi Kaprodi/Guru Besar relatif sudah lebih aman, tetapi implementasinya belum seragam | django-silk masih menampilkan tabel `kegiatan_kegiatankaprodimodel`, `kegiatan_kegiatangurubesarmodel`, `authentication_kaprodimodel`, dan `authentication_gurubesarmodel` | `KegiatanView._get_base_queryset()` dan `KegiatanService.get_kegiatan_detail()` | List endpoint memakai string prefetch `kaprodi_relasi__kaprodi` dan `guru_besar_relasi__guru_besar`; detail endpoint memakai `Prefetch(... select_related(...))`. Keduanya bekerja, tetapi pola detail lebih eksplisit dan lebih mudah dikontrol untuk ordering serta query budget. |
| Query `documents_suratpernyataanmodel` tetap muncul sebagai bagian payload | django-silk list/detail menampilkan `documents_suratpernyataanmodel` | `get_surat_pernyataan()` di `kegiatan/serializers.py`; prefetch di `KegiatanView._get_base_queryset()` dan `KegiatanService.get_kegiatan_detail()` | Surat pernyataan sudah diprefetch bersama `guru_besar`, sehingga query ini wajar ada. Fokus optimasi bukan menghapus query relasi yang memang dibutuhkan, tetapi mencegah query tersebut berulang per objek. |
| Repeated span `silk_request` muncul di Sentry lain | Sentry `PYTHON-DJANGO-15` dan sebagian `PYTHON-DJANGO-1E` | Middleware/profiler Silk, bukan kode bisnis kegiatan | Ini diperlakukan sebagai overhead instrumentation. Untuk optimasi point 3, fokus tetap pada query domain kegiatan, bukan mengoptimalkan tabel internal Silk. |

### Akar Masalah

Root cause paling kuat adalah ketidaksinkronan antara queryset list kegiatan dan
serializer response:

1. Response kegiatan selalu menyertakan `laporan_kegiatan`.
2. Serializer sudah punya mekanisme membaca cache prefetch lewat
   `_prefetched_objects_cache`.
3. Queryset list kegiatan belum mengisi cache `laporan_kegiatan`.
4. Akibatnya, untuk setiap kegiatan dalam list, serializer menjalankan query
   fallback ke `obj.laporan_kegiatan.all().order_by("-created_at")`.
5. Jika setiap laporan juga membutuhkan data guru besar, serializer dapat
   memicu query tambahan ke `authentication_gurubesarmodel`.

Dengan dataset lokal 25 kegiatan, pola ini menghasilkan:

| Endpoint | Avg Query Count | Max Duplicate SQL | Interpretasi |
| --- | ---: | ---: | --- |
| `/api/kegiatan/` | 368.0 | 284 | N+1 sangat jelas pada list endpoint |
| `/api/kegiatan/?status=SEDANG_BERJALAN` | 368.0 | 284 | Filter status tidak mengubah pola query; masalah ada di serialisasi relasi |
| `/api/kegiatan/{pk}/` | 26.0 | 6 | Detail lebih kecil, tetapi masih punya query relasi yang bisa distabilkan |

### Hipotesis Optimasi Untuk Point 3

Perbaikan yang paling relevan untuk point 3:

1. Tambahkan `Prefetch("laporan_kegiatan", queryset=LaporanKegiatan.objects.select_related("guru_besar").order_by("-created_at"))` pada list endpoint.
2. Tambahkan prefetch `laporan_kegiatan` yang sama pada detail endpoint.
3. Ubah serializer agar `guru_besar_id` pada laporan membaca kolom FK langsung
   jika memungkinkan, bukan memaksa akses `guru_besar.id`.
4. Samakan pola prefetch list dan detail dengan `Prefetch` eksplisit supaya
   ordering, select-related, dan query budget lebih mudah dikontrol.
5. Jalankan ulang profiling lokal dengan dataset yang sama untuk membandingkan
   query count, duplicate SQL, dan waktu response sebelum dan sesudah optimasi.

### Target Point 3

Target optimasi yang akan dibuktikan setelah perbaikan:

| Endpoint | Baseline Query Count | Target Query Count | Target Improvement |
| --- | ---: | ---: | ---: |
| `/api/kegiatan/` | 368 avg | kurang dari 40 | lebih dari 80% |
| `/api/kegiatan/?status=SEDANG_BERJALAN` | 368 avg | kurang dari 40 | lebih dari 80% |
| `/api/kegiatan/{pk}/` | 26 avg | kurang dari 12 | lebih dari 50% |

Point 2 terpenuhi karena hasil profiling sudah dianalisis sampai ke lokasi kode,
akar masalah, dan hipotesis perbaikan yang dapat diuji pada point 3.

## Implementasi Optimasi

Point 3 berfokus pada perbaikan kualitas non-fungsional berdasarkan hasil
profiling. Berdasarkan analisis point 2, bottleneck utama ada pada akses relasi
`laporan_kegiatan` dan `guru_besar` saat serializer membentuk response
kegiatan.

### Perubahan Kode

| File | Perubahan | Dampak |
| --- | --- | --- |
| `kegiatan/services.py` | Menambahkan `get_kegiatan_response_prefetches()` sebagai konfigurasi prefetch bersama | List dan detail memakai strategi query yang konsisten |
| `kegiatan/services.py` | Menambahkan `Prefetch("laporan_kegiatan", queryset=LaporanKegiatan.objects.select_related("guru_besar").order_by("-created_at"))` | Menghilangkan N+1 pada `laporan_laporankegiatan` |
| `kegiatan/views_kegiatan.py` | `KegiatanView._get_base_queryset()` memakai `get_kegiatan_response_prefetches()` | Endpoint list mengisi cache relasi yang dibutuhkan serializer |
| `kegiatan/serializers.py` | `KegiatanLaporanSerializer.guru_besar_id` membaca kolom FK langsung | Menghindari akses objek relasi `guru_besar` hanya untuk mengambil ID |

Inti implementasi:

- Queryset list dan detail sekarang sama-sama mengambil relasi yang memang
  dibutuhkan response.
- `laporan_kegiatan` diprefetch sekali untuk semua kegiatan, bukan diambil ulang
  per kegiatan saat serialisasi.
- Data `guru_besar` untuk laporan ikut diambil dengan `select_related`, sehingga
  serializer tidak membuat query tambahan untuk setiap laporan.
- Field `guru_besar_id` pada laporan memakai kolom FK langsung, sehingga tidak
  perlu membuka objek relasi hanya untuk membaca ID.
- Filter akses berdasarkan role tetap dipertahankan. Admin tetap melihat semua
  kegiatan, sedangkan guru besar dan kaprodi tetap hanya melihat kegiatan yang
  terkait dengan akun mereka.

### Hasil Profiling Setelah Optimasi

Profiling setelah optimasi dijalankan dengan dataset yang sama seperti baseline:

| Parameter | Value |
| --- | ---: |
| Database | `sqlite3:media/kegiatan_profiling_point1.sqlite3` |
| Records | 25 kegiatan |
| Kaprodi per kegiatan | 2 |
| Guru besar per kegiatan | 3 |
| Repeat | 3 |
| Authenticated role | Admin |

Result after:

<img width="1431" height="806" alt="image" src="https://github.com/user-attachments/assets/b78a723e-8a96-4769-bc99-fea170940088" />

| Endpoint | Avg Time | Avg Query Count | Max Duplicate SQL |
| --- | ---: | ---: | ---: |
| `/api/kegiatan/` | 105.8 ms | 14.0 | 0 |
| `/api/kegiatan/?status=SEDANG_BERJALAN` | 50.3 ms | 14.0 | 0 |
| `/api/kegiatan/{pk}/` | 6.0 ms | 14.0 | 0 |

### Before and After

| Endpoint | Before Query Count | After Query Count | Query Reduction | Before Duplicate SQL | After Duplicate SQL |
| --- | ---: | ---: | ---: | ---: | ---: |
| `/api/kegiatan/` | 368.0 | 14.0 | 98.6% | 284 | 0 |
| `/api/kegiatan/?status=SEDANG_BERJALAN` | 368.0 | 14.0 | 98.6% | 284 | 0 |
| `/api/kegiatan/{pk}/` | 26.0 | 14.0 | 80.8% | 6 | 0 |

Time comparison:

| Endpoint | Before Avg Time | After Avg Time | Time Reduction |
| --- | ---: | ---: | ---: |
| `/api/kegiatan/` | 1047.9 ms | 105.8 ms | 89.9% |
| `/api/kegiatan/?status=SEDANG_BERJALAN` | 887.0 ms | 50.3 ms | 94.3% |
| `/api/kegiatan/{pk}/` | 105.6 ms | 6.0 ms | 94.3% |

### Kesimpulan Point 3

Target point 3 terpenuhi:

| Endpoint | Target | Actual |
| --- | --- | --- |
| `/api/kegiatan/` | Query count turun lebih dari 80% | Turun 98.6% |
| `/api/kegiatan/?status=SEDANG_BERJALAN` | Query count turun lebih dari 80% | Turun 98.6% |
| `/api/kegiatan/{pk}/` | Query count turun lebih dari 50% | Turun 80.8% |

Perbaikan ini berdasarkan hasil profiling, menghilangkan duplicate SQL pada
endpoint yang dianalisis, dan tetap mempertahankan pembatasan akses berdasarkan
role pengguna.
