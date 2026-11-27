# Robot Drink Tracking

Robot beroda dua yang **mengantar pesanan**: tekan tombol, robot memutar badannya
mencari gelas yang diminta, mendekatinya, lalu berhenti di depannya dan berbunyi.

- **PB1 → kopi**, **PB2 → teh**.
- Kopi dan teh dibedakan oleh **model YOLO hasil latih sendiri** (Roboflow → ONNX),
  bukan ambang warna.
- Target perangkat: **Raspberry Pi 3B+ (1 GB)**, Raspberry Pi OS 32-bit, webcam USB,
  2× driver MX1508, 2 motor DC gearbox.

> Status: kode selesai dan teruji (54 tes, uji loop tertutup). Yang belum ada di
> repo hanya **model terlatih** — dibuat sendiri di tahap 4.

```
IDLE ──PB1/PB2──▶ CARI (putar 30°, diam, periksa, ulangi) ──target stabil──▶ DEKATI
DEKATI ──gelas sudah cukup besar──▶ SAMPAI (stop + beep 1×) ──▶ IDLE
DEKATI ──target hilang > 1 s──▶ CARI
CARI   ──20 s tanpa target──▶ GAGAL (beep 2×) ──▶ IDLE
DEKATI ──30 s tak pernah sampai──▶ GAGAL (beep 2×) ──▶ IDLE
tombol yang sama ditekan saat bergerak ──▶ berhenti seketika
tombol lain ditekan saat bergerak ──▶ ganti target, mulai cari lagi
```

Urutan pengerjaan dari nol sampai robot jalan ada di bawah. Jangan lompat:
tiap tahap punya pemeriksaan sendiri, dan tahap 4 (model) baru bisa dikerjakan
setelah robotnya bisa melihat (tahap 3).

| Tahap | Yang dikerjakan | Perkiraan waktu |
|---|---|---|
| 1 | Siapkan barang | belanja |
| 2 | Rakit + kabel | 1–2 jam |
| 3 | Pasang Raspberry Pi & cek kamera | 30 menit |
| 4 | Ambil dataset + latih model di Roboflow | 1,5–2 jam |
| 5 | Pasang model, uji deteksi | 20 menit |
| 6 | Kalibrasi 4 angka di lantai | 30 menit |
| 7 | Jalankan sebagai service | 10 menit |

---

## 1. Siapkan barang

| Bagian | Jumlah | Catatan |
|---|---|---|
| Raspberry Pi 3B+ | 1 | 1 GB RAM; 4/5 boleh, tapi angka di repo ini diukur untuk 3B+ |
| microSD 16 GB+ | 1 | Raspberry Pi OS **32-bit** (Bullseye/Bookworm) |
| Webcam USB (UVC) | 1 | yang mendukung **MJPG** 640×480 @30 FPS |
| Modul driver MX1508 | 2 | satu motor satu kanal; jangan diparalel (batas ±1,2–1,5 A/kanal) |
| Motor DC gearbox + roda | 2 set | motor "TT" kuning sudah cukup |
| Roda bebas (castor) | 1 | di depan atau belakang |
| Baterai 2S (7,4 V) | 1 | 2× 18650 + holder, atau LiPo 2S; **maksimal 10 V** ke MX1508 |
| Saklar + sekring | 1 | sekring 3 A sudah cukup |
| Push button | 2 | tombol tekan biasa, tidak perlu modul |
| LED + resistor 330 Ω | 1 | indikator status |
| Buzzer aktif 3–5 V | 1 | yang berbunyi sendiri saat diberi tegangan |
| Bodi | 1 | akrilik/3D print; kamera dipasang tetap, **tidak** pakai servo |

Yang **tidak** dibutuhkan: servo pan, sensor jarak, layar, keyboard. Robot
sepenuhnya dikendalikan dua tombol, dan jarak ditebak dari ukuran kotak deteksi.

## 2. Rakit dan kabel

### Peta pin (BCM, bukan nomor fisik header)

| Fungsi | GPIO | Keterangan |
|---|---|---|
| MX1508 **kiri** IN1 / IN2 | 23 / 24 | modul 1, kanal A |
| MX1508 **kanan** IN1 / IN2 | 5 / 6 | modul 2, kanal A |
| PB1 (kopi) | 17 | tombol ke GND, pull-up internal, tanpa resistor |
| PB2 (teh) | 27 | idem |
| LED status | 22 | anoda ke GPIO22, katoda lewat 330 Ω ke GND |
| Buzzer | 18 | aktif 3–5 V; kalau bervolume kecil, tambahkan transistor |
| GPIO 12 | — | sengaja dibiarkan kosong (tidak ada servo pan) |

### Kenapa 2 modul MX1508 tapi cuma 4 pin GPIO

MX1508 tidak punya pin **ENA/ENB** seperti L298N. Di modul ini PWM masuk langsung
ke pin **IN**, dan arah ditentukan pin pasangannya:

| IN1 | IN2 | Keluaran OUT1–OUT2 |
|---|---|---|
| PWM | 0 | maju, kecepatan = duty |
| 0 | PWM | mundur, kecepatan = duty |
| 0 | 0 | motor diam (rem) |

Jadi satu motor butuh **2 pin**, bukan 3. Dua motor = 4 pin. Yang membuatnya jadi
dua modul adalah **arus**, bukan jumlah pin: satu kanal MX1508 hanya tahan
±1,2–1,5 A kontinu, dan dua motor yang menanjak bersamaan bisa melewatinya.

```
Modul 1 (motor kiri)              Modul 2 (motor kanan)
  IN1 ── GPIO23 (PWM)               IN1 ── GPIO5 (PWM)
  IN2 ── GPIO24                     IN2 ── GPIO6
  OUT1/OUT2 ── motor kiri           OUT1/OUT2 ── motor kanan
  IN3, IN4 ── GND (tidak dipakai)   IN3, IN4 ── GND (tidak dipakai)
  VM  ── +7,4 V                     VM  ── +7,4 V
  GND ── GND baterai/Pi             GND ── GND baterai/Pi
```

Kanal B (IN3/IN4, OUT3/OUT4) di kedua modul sengaja tidak dipakai. Pin IN3/IN4
diikat ke GND supaya tidak mengambang dan mengambil derau — bukan untuk kontrol.

Empat pin itu **hanya cukup** kalau tiap motor memakai kanal A modulnya sendiri.
Jangan memparalel OUT1/OUT2 dua modul ke satu motor (dua saklar saling melawan),
dan jangan menyalakan dua motor pada satu kanal kalau arus totalnya dekat batas.

### Daya

- Baterai 2S → **VM** MX1508, GND baterai–Pi–driver **disatukan**. GND yang tidak
  disatukan adalah penyebab paling sering "motor diam padahal duty 0,5".
- Jangan mengambil daya motor dari 5 V Pi. Jangan memasang beban motor langsung ke
  pin GPIO tanpa driver.
- Buck converter 5 V 3 A untuk Pi kalau baterai 2S; webcam ikut ke 5 V itu.

### Pemasangan kamera

Kamera dipasang **tetap** di depan bodi, menghadap arah gerak, menunduk
±10–20°, tinggi 15–20 cm dari lantai. Syarat praktis: gelas yang berjarak 1 m
harus masuk frame dengan ukuran kotak minimal ±5% lebar frame. Kalau gelas di 1 m
sudah menyentuh tepi frame, kemiringannya terlalu tajam — target akan terpotong
tepat saat robot mendekat.

### Arah maju

Pasang roda, lalu jalankan uji roda sebelum memasang kamera:

```bash
python3 main.py --dry-run --seconds 3      # hanya mencatat, tidak menggerakkan motor
python3 -c "import hardware;hw=hardware.make();hw.drive(0.4,0.4);input('kedua roda maju? enter=');hw.stop()"
```

Kalau salah satu roda berputar terbalik, tukar pin maju/mundur motor itu di
`config.py` — jangan tukar kabel di driver secara asal, karena urutannya juga
dipakai saat memutar badan.

## 3. Pasang Raspberry Pi dan pastikan kamera terlihat

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy python3-gpiozero python3-lgpio git
git clone https://github.com/haudilulum/robot-drink-tracking
cd robot-drink-tracking
```

Cek kamera (resolusi, FPS, dan frame benar-benar terbaca):

```bash
python3 -c "import cv2;c=cv2.VideoCapture(0);c.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'));ok,f=c.read();print('kamera',int(c.get(3)),'x',int(c.get(4)),'@',round(c.get(5)),'fps','frame=ada' if ok else 'frame=GAGAL')"
```

Yang harus terlihat: `640 x 480 @ 30 fps frame=ada`. Kalau `frame=GAGAL`, cek
kabel/kamera lain yang memakai `/dev/video0` (`ls /dev/video*`). Kalau FPS
tertulis 5, kamera tidak masuk mode MJPG — gambar akan tersendat dan robot
terlihat "berpikir lama".

Cek tombol dan LED tanpa menggerakkan motor:

```bash
python3 -c "import hardware;hw=hardware.make();print('tekan tombol (Ctrl-C keluar)');[print('  ->',hw.read_button()) or __import__('time').sleep(0.1) for _ in iter(int,1)]"
```

Setiap tekanan PB1 harus mencetak `kopi`, PB2 mencetak `teh`.

✅ **Lanjut kalau:** kamera memberi frame, kedua tombol terbaca, dan roda sudah
berputar ke arah yang benar.

## 4. Ambil dataset dan latih model di Roboflow

Isi kopi dan teh sama-sama cairan gelap, jadi warna cairan tidak membedakan
keduanya. Yang membedakan adalah **gelas/penandanya** — karena itu model perlu
melihat gelasnya, bukan cairannya. Beri ciri yang benar-benar terlihat beda
(warna gelas, bentuk, atau stiker), kalau tidak akurasi training tidak akan
menolong.

### 4a. Ambil foto (di laptop)

Colok webcam USB yang **sama** dengan yang dipasang di robot ke laptop. Posisikan
setinggi dan semiring seperti di bodi robot, lalu ambil foto dengan variasi:

| Dimensi | Variasi yang perlu ada |
|---|---|
| Jarak | 20, 40, 60, 100 cm |
| Posisi di frame | kiri, tengah, kanan |
| Cahaya | lampu ruangan, dekat jendela, sedikit gelap |
| Latar | dua meja/lantai berbeda |
| Pengganggu | ada gelas lain, ada tangan, meja kosong |
| Sudut | gelas agak miring, sebagian terhalang |

Jumlah bukan target: **±60 foto bervariasi per kelas** (120 total) sudah cukup.
300 foto hasil burst yang nyaris identik tidak menambah apa pun — bagi model itu
satu contoh yang diduplikasi.

### 4b. Label dan latih

1. Buat project **Object Detection** di Roboflow, upload semua foto.
2. Beri label `kopi` dan `teh`, satu kotak per gelas. Gelas yang bukan target
   **jangan dilabeli** (otomatis jadi latar).
3. Split otomatis ±70/20/10, augmentasi cahaya + blur secukupnya.
4. Train **YOLOv8n** (Roboflow hosted atau Colab).
5. Lihat mAP50 dan confusion matrix. Kalau kelas tertukar, tambah foto yang mirip
   dengan kasus yang salah, jangan menambah epoch.

### 4c. Ekspor ke ONNX

Di Roboflow: **Deploy → ONNX**, ukuran input **320×320**, tanpa NMS
(*non-end-to-end*). Unduh, lalu di Pi:

```bash
mkdir -p models
# salin hasil unduhan ke sini
cp ~/unduhan/model.onnx models/kopi_teh_yolov8n.onnx
```

Dua hal yang harus cocok, kalau tidak deteksi akan kosong atau kelas tertukar:

- `YOLO_IMGSZ` di `config.py` = ukuran input saat export (default `320`).
- `YOLO_KELAS` = urutan kelas di `data.yaml` Roboflow (default `["kopi","teh"]`).

Kalau export memakai 640, ubah `YOLO_IMGSZ = 640`; jangan biarkan 320 — blob dan
model harus seukuran. Konsekuensinya satu deteksi naik dari ±1 s ke ±4 s.

## 5. Uji deteksi sebelum menyentuh motor

```bash
python3 main.py --vision yolo --debug foto/debug --diam
```

Biarkan 10–20 detik, tekan Ctrl-C, lalu buka `foto/debug/`:

- kotak harus menempel pada gelas, labelnya benar;
- angka `w=` pada log adalah lebar kotak (0..1) — ini yang nanti jadi ukuran jarak.

Kalau tidak ada kotak sama sekali: turunkan `CONF_MIN` ke 0,20 dulu untuk memastikan
modelnya hidup, lalu naikkan kembali setelah tahu nilai aslinya. Kalau kotak muncul
di latar/meja, `CONF_MIN` dinaikkan (0,45–0,55) dan tambah foto latar ke dataset.

## 6. Kalibrasi empat angka di lantai

Semua angka ada di `config.py`. Nilai bawaan adalah titik awal, bukan hasil ukur.

**a. `SPEED_MIN` (0,35)** — duty terendah yang masih memutar roda dari diam.
Naikkan 0,05 tiap percobaan sampai robot bergerak mulus tanpa bergetar.
Motor TT + 2S biasanya 0,30–0,40.

**b. `W_BERHENTI` (0,48) dan `W_MULAI_PELAN` (0,30)** — jarak berhenti.
Letakkan gelas pada jarak yang Anda inginkan (mis. 35 cm dari kamera), jalankan
`python3 main.py --debug foto/debug`, baca `w=` saat kotak menempel di gelas, lalu
set `W_BERHENTI` ke angka itu dan `W_MULAI_PELAN` = `W_BERHENTI` − 0,18.

**c. `DERAJAT_PER_DETIK` (90)** — kecepatan putar sebenarnya. Jalankan mode cari,
hitung berapa detik robot berputar sampai 360° (12 langkah × 30°), lalu
`DERAJAT_PER_DETIK = 360 / detik`. Menyapu lebih cepat dari ±45°/s membuat gelas
terlewat di antara dua deteksi yang berjarak ±1 s.

**d. `KP_BELOK` (0,85)** — koreksi belok. Terlalu besar: robot mengayun
kiri-kanan. Terlalu kecil: gelas keluar frame sebelum sempat dikoreksi.

Setelah empat angka ini benar, robot sudah memenuhi konsep: tekan tombol,
menyapu mencari, mendekat, berhenti, beep.

## 7. Jalankan sebagai service

```bash
bash scripts/install_pi.sh          # dependensi + unit systemd (sekali saja)
sudo systemctl start robot-drink-tracking
journalctl -u robot-drink-tracking -f
```

Service ini otomatis hidup saat boot. Hentikan dulu sebelum menjalankan `main.py`
manual, supaya GPIO tidak dipakai dua proses sekaligus:

```bash
sudo systemctl stop robot-drink-tracking
python3 main.py                     # mode debug di terminal
```

## 8. Uji tanpa hardware (untuk mengubah kode)

Semua logika bisa diuji tanpa Pi, kamera, atau model — cukup Python + OpenCV:

```bash
python3 main.py --dry-run --seconds 10                  # PB1 otomatis, detektor palsu
python3 main.py --dry-run --seconds 10 --tombol-uji teh
python3 -m unittest discover -s tests                   # 54 tes
python3 tests/uji_integrasi_dunia.py                    # loop tertutup dunia sintetis
```

`uji_integrasi_dunia.py` menggeser gelas ke tengah saat robot berbelok dan
membesarkannya saat robot maju, jadi yang diuji bukan cuma "detektor menyala",
tapi apakah robot benar-benar berhenti dengan gelas di tengah frame.

---

## Lampiran

### A. Kenapa jarak dari lebar kotak

Tidak ada sensor jarak di proyek ini. Lebar kotak deteksi cukup karena geometri
kamera biasa:

```
lebar_piksel = f × LEBAR_GELAS / Z          (f = fokus dalam piksel, Z = jarak)
```

Jadi `w` berbanding terbalik dengan jarak: dua kali lebih dekat = kotak dua kali
lebih lebar. `W_BERHENTI` karena itu **adalah** jarak berhenti, hanya dinyatakan
dalam satuan `w` — Anda tidak perlu tahu `f`.

Ketelitiannya: galat jarak ≈ galat lebar. Kotak bergetar 10% berarti jarak meleset
10%; pada jarak berhenti 35 cm itu ±3,5 cm. Dua penjaga di `main.py`:

- lebar diratakan **median 3 deteksi terakhir** (`W_FILTER_N`), supaya satu frame
  yang kebetulan besar tidak membuat robot berhenti terlalu awal;
- kotak yang **menyentuh tepi frame** dianggap terpotong. Lebarnya justru terukur
  lebih kecil dari aslinya, jadi kalau `w` sudah ≥ 80% `W_BERHENTI` robot langsung
  berhenti — tanpa ini ia akan terus maju menabrak gelas yang memenuhi pandangan.

Batasnya: cara ini mengasumsikan ukuran gelas tetap. Kalau di demo dipakai gelas
dengan ukuran berbeda jauh, setel `W_BERHENTI` untuk yang paling kecil.

### B. Kenapa model terlatih, bukan ambang warna manual

Membedakan dua benda yang pikselnya hampir sama tidak bisa dilakukan dengan batas
warna: batas itu harus disetel ulang setiap kali lampu atau meja berubah, dan satu
rentang untuk `kopi` gampang tumpang tindih dengan `teh`. Model belajar bentuk,
tekstur, dan konteks sekaligus. Ongkosnya dataset berlabel dan satu kali training —
itu sudah dikerjakan di tahap 4.

Di Pi 3B+, YOLOv8n ONNX 640×640 lewat `cv2.dnn` butuh **±1,2 s/frame** (terukur
1171 ms), sementara 320 diperkirakan ±1 s. Karena itu:

- model berjalan di thread terpisah (`AsyncDetector`) — loop kendali tetap ±16 Hz,
  hasil lebih tua dari `ASYNC_BASI_S` dibuang;
- kotak digeser optical flow Lucas-Kanade (±5 ms/frame) di antara dua deteksi
  (`AlurDetector`), jadi kotak tetap menempel pada gelas meski robot berbelok;
- karena gelas diam, deteksi yang putus sesaat bukan alasan berhenti: perintah
  terakhir dilanjutkan sampai `GRACE_HILANG_S` lewat.

### C. Berkas

| Berkas | Isi |
|---|---|
| `config.py` | pin, ambang, gain, setelan model & gerak — satu tempat untuk semua angka |
| `hardware.py` | motor/tombol/LED/buzzer + versi palsu untuk tes |
| `vision.py` | kamera, `YoloDetector`, `AsyncDetector`, `AlurDetector`, `FakeDetector` |
| `main.py` | state machine + CLI |
| `scripts/install_pi.sh` | dependensi + unit systemd |
| `tests/` | 54 unit test + uji integrasi dunia |

### D. Kalau bermasalah

- **`model YOLO belum ada`** — ONNX belum ditaruh di `models/kopi_teh_yolov8n.onnx`.
- **Kelas tertukar (kopi dianggap teh)** — `YOLO_KELAS` tidak sama urutan dengan
  `data.yaml` Roboflow.
- **Tidak ada deteksi sama sekali** — `YOLO_IMGSZ` tidak sama dengan ukuran input
  saat export; atau export memakai NMS/end-to-end sehingga bentuk outputnya beda.
- **Deteksi bagus di laptop, jeblok di robot** — dataset diambil dengan kamera lain.
  Ambil ulang dari webcam yang terpasang di robot.
- **`w=` tidak pernah mencapai `W_BERHENTI`** — kotak terpotong tepi frame: kamera
  terlalu menunduk atau robot sudah terlalu dekat.
- **Robot berhenti-maju berulang** — deteksi sering putus; naikkan
  `GRACE_HILANG_S` atau turunkan `CONF_MIN`.
- **Robot tidak bergerak walau duty 0,4** — deadband motor atau baterai drop; ukur
  tegangan VM saat motor jalan.
- **Robot berputar terus padahal tanpa tombol** — pin motor tertukar dengan pin
  tombol, atau `SPEED_MIN` terlalu tinggi sehingga motor tidak pernah benar-benar 0.
- **Kamera 5 FPS / gelap** — `KAMERA_MJPG=True` belum berlaku; cek dengan perintah
  di tahap 3.

### E. Yang belum ada

- **Model terlatih di repo ini** — `models/` kosong; dataset dan training
  dikerjakan terpisah (tahap 4).
- Sensor jarak sungguhan (VL53L0X/ultrasonik) sebagai pembanding lebar kotak.
- Deteksi halangan saat maju (minimal bumper switch).
- Log CSV per sesi (target, waktu tempuh, `w` akhir) untuk evaluasi.
