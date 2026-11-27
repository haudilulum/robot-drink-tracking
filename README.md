# Robot Drink Tracking

Robot beroda diferensial: tekan **PB1 → cari & dekati kopi**, tekan **PB2 → cari &
dekati teh**. Robot memutar badannya untuk menyapu pandangan, mengunci gelas
target, maju sampai jarak berhenti, lalu berhenti + beep.

Target perangkat: **Raspberry Pi 3B+ (1 GB)**, Raspberry Pi OS 32-bit, webcam UVC,
2× modul driver MX1508, 2 motor DC gearbox.

```
IDLE ──PB1/PB2──▶ CARI (putar 30°, periksa, ulangi) ──target stabil──▶ DEKATI
DEKATI ──gelas cukup besar──▶ SAMPAI (stop + beep 1×) ──▶ IDLE
DEKATI ──target hilang > GRACE_HILANG_S──▶ CARI
CARI   ──20 s tanpa target──▶ GAGAL (beep 2×) ──▶ IDLE
DEKATI ──30 s tidak sampai──▶ GAGAL (beep 2×) ──▶ IDLE
tombol sama ditekan saat bergerak ──▶ berhenti seketika
tombol lain ditekan saat bergerak ──▶ ganti target, mulai cari lagi
```

## Satu jalur: model YOLO dari Roboflow

Isi kopi dan teh sama-sama cairan gelap, jadi **dari warna saja keduanya tidak bisa
dibedakan** — informasinya memang tidak ada di piksel cairan. Yang membuat mereka
beda adalah gelas/penandanya. Karena itu satu-satunya jalur identifikasi di proyek
ini adalah **model YOLO 2 kelas** yang dilatih di Roboflow (atau Colab) dan
diekspor ke ONNX; robot hanya menjalankan model itu lewat `cv2.dnn`.

Tidak ada ambang HSV, tidak ada `kalibrasi.py`, tidak ada deteksi bentuk. Berkas
itu sudah dihapus, bukan dipindah.

### Kenapa model, bukan ambang warna

Ambang warna (HSV blob) bekerja kalau gelasnya diberi penanda warna tunggal, tapi
rentangnya harus disetel ulang setiap kali lampu/meja berubah, dan satu rentang
untuk `kopi` gampang tumpang tindih dengan `teh`. Model belajar bentuk, tekstur,
dan konteks gelas sekaligus, sehingga lebih tahan perubahan cahaya. Harganya:
perlu ±300 foto berlabel dan satu kali training — cukup ±60 foto **bervariasi** per kelas, bukan 300 foto yang
mirip semua.

### Biaya inference dan cara menutupinya

YOLOv8n ONNX 640×640 di `cv2.dnn` pada CPU kelas Cortex-A53 terukur
**1171 ms/frame (0,85 FPS)**; di `human-tracking-robot-v2` angka Pi 3B+ tercatat
**640 → 4,1 s, 416 → 1,75 s, 320 → 1,03 s** per deteksi (TFLite int8 1,8× lebih
cepat dari ONNX fp32). Karena itu:

- `YOLO_IMGSZ = 320` — satu deteksi ±1 s, cukup untuk target yang tidak bergerak.
- `vision.AsyncDetector` — model berjalan di thread sendiri, loop kendali tidak
  pernah menunggu (terukur: loop tetap ~16 Hz saat model butuh 1,17 s/frame).
  Hasil lebih tua dari `ASYNC_BASI_S` dibuang.
- `vision.AlurDetector` — kotak digeser dengan optical flow Lucas-Kanade
  (~5 ms/frame) di setiap frame kamera, jadi kotak tetap menempel di gelas di
  antara dua deteksi. Bila titik fitur habis (gelas tertutup/buram), kotak
  dilepas dan state machine memperlakukannya sebagai target hilang.

Gelas **tidak bergerak**, jadi gerakan kotak di gambar berasal dari gerakan robot
sendiri — itu justru yang diukur optical flow. Konsekuensi lain: deteksi yang
putus sesaat bukan alasan berhenti; `main.py` menyimpan perintah terakhir dan
melanjutkannya sampai `GRACE_HILANG_S` lewat.

## Membuat model (Roboflow)

1. Ambil foto dari **kamera, sudut, dan ketinggian pemasangan yang sama** dengan
   saat dipakai. Jumlah bukan target: 120 foto yang bervariasi mengalahkan 300
   foto hasil burst yang nyaris identik. Yang dihitung adalah variasi —
   terang/gelap, jarak 20/40/60/100 cm, gelas di kiri/tengah/kanan frame, dua
   jenis meja, ada/tidak ada gelas lain di latar. Ambil dengan webcam USB yang
   dicolok ke laptop — kamera yang sama dengan yang nanti dipasang di robot.
2. Upload ke Roboflow, beri label `kopi` / `teh` (satu kotak per gelas; gelas lain
   yang bukan target jangan dilabeli).
3. Augmentasi cahaya + blur secukupnya, lalu train (Roboflow hosted atau Colab).
4. Export **ONNX** dengan input **320**, simpan sebagai
   `models/kopi_teh_yolov8n.onnx`.
5. `YOLO_KELAS` di `config.py` harus sama urutannya dengan saat training
   (`["kopi", "teh"]`).
6. Uji: `python3 main.py --vision yolo --debug foto/debug`, periksa kotak di
   `foto/debug/`.

Model tetap hanya bisa membedakan apa yang **terlihat beda**. Kalau dua gelasnya
identik, akurasi training tidak menolong — beri ciri visual (stiker, warna gelas,
bentuk berbeda) supaya kelasnya punya pembeda.

## Pin (BCM, bukan nomor fisik header)

| Fungsi | GPIO | Catatan |
|---|---|---|
| MX1508 kiri IN1 / IN2 | 23 / 24 | PWM masuk ke pin IN, arah dari pin pasangannya |
| MX1508 kanan IN1 / IN2 | 5 / 6 |  |
| PB1 (kopi) | 17 | tombol ke GND, pull-up internal, tanpa resistor |
| PB2 (teh) | 27 | idem |
| LED status | 22 | + resistor 330 Ω ke GND |
| Buzzer | 18 | buzzer aktif 3–5 V, atau lewat transistor |
| GPIO 12 | — | sengaja kosong; tidak ada servo pan, kamera dipasang tetap |

Daya: 2S 7.4 V ke VM MX1508 (maksimum 10 V), GND baterai–Pi–driver **disatukan**.
Jangan mengambil daya motor dari 5 V Pi, dan jangan memparalel dua motor pada satu
kanal MX1508 (batas kontinu ±1,2–1,5 A per kanal).

## Pasang di Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy python3-gpiozero python3-lgpio
cd ~/robot-drink-tracking
python3 -c "import cv2;c=cv2.VideoCapture(0);c.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'));ok,f=c.read();print('kamera',int(c.get(3)),'x',int(c.get(4)),'@',round(c.get(5)),'fps','frame=ada' if ok else 'frame=GAGAL')"
python3 main.py                 # butuh models/kopi_teh_yolov8n.onnx
```

Autostart saat boot:

```bash
bash scripts/install_pi.sh
sudo systemctl status robot-drink-tracking
journalctl -u robot-drink-tracking -f
```

Model ONNX dijalankan lewat `cv2.dnn`, **tanpa** `ultralytics`/torch, supaya RAM
1 GB tidak habis. Kalau `models/` belum berisi model, `main.py` berhenti dengan
pesan `model YOLO belum ada: ...` sebelum menyentuh kamera.

## Jarak dari lebar kotak (tanpa sensor tambahan)

Tidak ada VL53L0X/ultrasonik: jarak ditebak dari lebar kotak deteksi. Alasannya
geometri kamera biasa —

```
lebar_piksel = f * LEBAR_GELAS / Z        (f = fokus dalam piksel, Z = jarak)
```

jadi `Z = f * LEBAR_GELAS / lebar_piksel`. Karena itu lebar kotak ternormalisasi
(`w` 0..1) berbanding terbalik dengan jarak: dua kali lebih dekat = kotak dua kali
lebih lebar. `W_BERHENTI` **adalah** jarak berhenti, hanya dinyatakan dalam
satuan `w`; Anda tidak perlu tahu `f` — cukup ukur sekali di lantai (langkah 1 di
bawah) dan ambang itu otomatis berarti jarak yang Anda inginkan.

Batas ketelitiannya jujur saja: galat relatif jarak ≈ galat relatif lebar. Kotak
yang bergetar 10% berarti jarak meleset 10% — pada jarak berhenti 40 cm itu ±4 cm,
masih wajar. Karena itu ada dua penjaga di `main.py`:

- lebar diratakan **median 3 deteksi terakhir** (`W_FILTER_N`), supaya satu frame
  yang kebetulan besar tidak membuat robot berhenti terlalu awal;
- kotak yang **menyentuh tepi frame** dianggap terpotong: lebarnya justru terukur
  lebih kecil dari aslinya, jadi kalau `w` sudah ≥ 80% `W_BERHENTI` robot langsung
  berhenti — kalau tidak, ia akan terus maju dan menabrak gelas yang sudah
  memenuhi pandangan.

Yang tidak bisa dilakukan cara ini: mengukur jarak ke benda yang ukurannya berbeda
(gelas tinggi vs mug lebar). Kalau di demo dipakai dua gelas berukuran beda,
setel `W_BERHENTI` untuk yang paling kecil, atau tambahkan ToF sebagai
pembanding.

## Yang perlu disetel di lantai

Angka di `config.py` adalah nilai awal, bukan hasil ukur. Yang wajib diukur hanya
empat, dan tidak ada satu pun yang soal warna:

1. **`W_BERHENTI` / `W_MULAI_PELAN`** — letakkan gelas pada jarak berhenti yang
   diinginkan, jalankan `python3 main.py --debug foto/debug`, baca `w=` pada log,
   set `W_BERHENTI` ke nilai itu (`W_MULAI_PELAN` ±0,18 lebih kecil).
2. **`SPEED_MIN`** — naikkan sampai robot benar-benar bergerak dari diam (motor
   TT + 2S biasanya 0,30–0,40). Duty di bawah ini hanya membuat motor bergetar.
3. **`DERAJAT_PER_DETIK`** — target ~45°/s: satu deteksi butuh ±1 s, jadi menyapu
   lebih cepat dari itu membuat gelas terlewat di antara dua deteksi. Ukur dengan
   busur: 12 langkah mode CARI harus ≈ 360°.
4. **`KP_BELOK`** — terlalu besar = robot mengayun kiri-kanan; terlalu kecil =
   gelas keluar frame sebelum sempat dikoreksi.

`CONF_MIN` (0,35 awal) dinaikkan kalau potongan latar ikut terdeteksi, diturunkan
kalau gelas jauh tidak terbaca.

## Uji tanpa hardware

```bash
python3 main.py --dry-run --seconds 10                 # PB1 otomatis, model fake
python3 main.py --dry-run --seconds 10 --tombol-uji teh
python3 -m unittest discover -s tests                  # 54 tes
python3 tests/uji_integrasi_dunia.py                   # dunia sintetis closed-loop
```

`uji_integrasi_dunia.py` menutup loop kendali: gelas bergeser ke tengah saat robot
berbelok dan membesar saat robot maju, jadi terlihat apakah robot benar-benar
berhenti dengan gelas di tengah — bukan cuma apakah detektor menyala. Detektornya
menggantikan model (membaca keadaan dunia langsung), jadi model tidak dibutuhkan
untuk tes ini.

## Berkas

| Berkas | Isi |
|---|---|
| `config.py` | pin, ambang, gain, setelan model & gerak |
| `hardware.py` | motor/tombol/LED/buzzer + versi palsu untuk tes |
| `vision.py` | kamera, `YoloDetector`, `AsyncDetector`, `AlurDetector`, `FakeDetector` |
| `main.py` | state machine + CLI |
| `tests/` | 54 unit test + uji integrasi dunia |

## Troubleshooting

- **`model YOLO belum ada`.** ONNX hasil export Roboflow belum ditaruh di
  `models/kopi_teh_yolov8n.onnx`.
- **Kelas tertukar (kopi dianggap teh).** `YOLO_KELAS` tidak sama urutannya dengan
  training; urutan mengikuti `data.yaml` di Roboflow.
- **`w=` tidak pernah mencapai `W_BERHENTI`.** Kotak terpotong tepi frame; robot
  terlalu dekat atau kamera menunduk terlalu tajam.
- **Kamera gelap / 5 FPS.** Pastikan `KAMERA_MJPG=True`; tanpa MJPG webcam jatuh ke
  YUYV dan frame drop. Cek dengan perintah `python3 -c` di bagian pemasangan.
- **Robot tidak bergerak walau duty 0,4.** Deadband motor terlalu tinggi atau
  baterai drop. Ukur tegangan VM saat motor jalan.
- **Robot berputar terus di IDLE.** Pin motor tertukar dengan pin tombol, atau
  `SPEED_MIN` terlalu tinggi sehingga motor tidak pernah benar-benar 0.
- **Robot berhenti-maju berulang saat mendekat.** Deteksi sering putus; naikkan
  `GRACE_HILANG_S` atau turunkan `CONF_MIN`.
- **Deteksi hanya jalan di laptop, bukan di robot.** Dataset diambil dengan
  kamera yang berbeda. Ambil ulang dari webcam yang dipasang di robot.

## Yang belum ada

- Model terlatih di repo ini — `models/` kosong; dataset dan training dilakukan
  terpisah (`~/coffee-tea-dataset` baru berisi skrip).
- Pengukur jarak sesungguhnya (VL53L0X/ultrasonik) — sekarang jarak ditebak dari
  lebar kotak, jadi akurasinya bergantung pada ukuran gelas dan sudut kamera.
- Deteksi halangan saat maju (minimal bumper switch).
- Log CSV per sesi (target, waktu tempuh, `w` akhir) untuk evaluasi.
