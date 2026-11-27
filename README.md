# Robot Drink Tracking

Robot beroda dua yang **mengantar pesanan**: tekan tombol, robot memutar badannya
mencari gelas yang diminta, mendekatinya, lalu berhenti di depannya.

- **PB1 → kopi**, **PB2 → teh**.
- Kopi dan teh dibedakan oleh **model YOLO hasil latih sendiri** (Roboflow → ONNX),
  bukan ambang warna.
- Target perangkat: **Raspberry Pi 3B+ (1 GB)**, Raspberry Pi OS **32-bit (Trixie)***,
  webcam USB, 2× driver MX1508, 4 motor DC gearbox (4WD).

> Status: kode selesai dan teruji (56 tes, uji loop tertutup). Yang belum ada di
> repo hanya **model terlatih** — dibuat sendiri di tahap 4.

```
IDLE ──PB1/PB2──▶ CARI (putar 30°, diam, periksa, ulangi) ──target stabil──▶ DEKATI
DEKATI ──gelas sudah cukup besar──▶ SAMPAI (stop) ──▶ IDLE
DEKATI ──target hilang > 1 s──▶ CARI
CARI   ──20 s tanpa target──▶ GAGAL ──▶ IDLE
DEKATI ──30 s tak pernah sampai──▶ GAGAL ──▶ IDLE
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
| microSD 16 GB+ | 1 | Raspberry Pi OS **32-bit** (Debian 13, Trixie) |
| Webcam USB (UVC) | 1 | yang mendukung **MJPG** 640×480 @30 FPS |
| Modul driver MX1508 | 2 | 4 kanal terpakai, **satu motor satu kanal**; jangan diparalel (batas ±1,2–1,5 A/kanal) |
| Motor DC gearbox + roda | 4 set | motor "TT" kuning sudah cukup; 4 roda digerakkan semua |
| Baterai 2S (7,4 V) | 1 | 2× 18650 + holder, atau LiPo 2S; **maksimal 10 V** ke MX1508 |
| Saklar on/off | 1 | pemutus daya baterai |
| Push button | 2 | tombol tekan biasa, tidak perlu modul |
| Bodi | 1 | akrilik/3D print; kamera dipasang tetap di depan bodi |

Yang **tidak** dibutuhkan: roda bebas/castor, sensor jarak, layar, keyboard. Karena keempat roda digerakkan (skid-steer), bodi tidak butuh titik
tumpu ketiga — castor hanya dipakai pada robot 2WD. Robot sepenuhnya dikendalikan
dua tombol, dan jarak ditebak dari ukuran kotak deteksi.

## 2. Rakit dan kabel

### Peta pin (BCM, bukan nomor fisik header)

| Fungsi | GPIO | Keterangan |
|---|---|---|
| modul 1 kanal A → **kiri depan** | 23 (IN1) / 24 (IN2) | OUT1/OUT2 ke motor kiri depan |
| modul 1 kanal B → **kiri belakang** | 25 (IN3) / 16 (IN4) | OUT3/OUT4 ke motor kiri belakang |
| modul 2 kanal A → **kanan depan** | 5 (IN1) / 6 (IN2) | OUT1/OUT2 ke motor kanan depan |
| modul 2 kanal B → **kanan belakang** | 19 (IN3) / 26 (IN4) | OUT3/OUT4 ke motor kanan belakang |
| PB1 (kopi) | 17 | tombol ke GND, pull-up internal, tanpa resistor |
| PB2 (teh) | 27 | idem |

### Empat kanal, delapan pin

MX1508 tidak punya pin **ENA/ENB** seperti L298N. PWM masuk langsung ke pin **IN**,
dan arah ditentukan pin pasangannya:

| IN maju | IN mundur | Keluaran |
|---|---|---|
| PWM | 0 | maju, kecepatan = duty |
| 0 | PWM | mundur, kecepatan = duty |
| 0 | 0 | motor diam (rem) |

Jadi satu motor butuh **2 pin**, bukan 3. Empat motor = 8 pin = empat kanal, dua
kanal per modul. Semua kanal dipakai; tidak ada motor yang diparalel.

```
Modul 1                            Modul 2
 kanal A (kiri depan)               kanal A (kanan depan)
   IN1 ── GPIO23 (PWM)                IN1 ── GPIO5 (PWM)
   IN2 ── GPIO24                      IN2 ── GPIO6
   OUT1/OUT2 ── motor LD              OUT1/OUT2 ── motor KnD
 kanal B (kiri belakang)            kanal B (kanan belakang)
   IN3 ── GPIO25 (PWM)                IN3 ── GPIO19 (PWM)
   IN4 ── GPIO16                      IN4 ── GPIO26
   OUT3/OUT4 ── motor LB              OUT3/OUT4 ── motor KnB
 VM  ── +7,4 V                      VM  ── +7,4 V
 GND ── GND baterai/Pi              GND ── GND baterai/Pi
```

Sisi kiri (GPIO 23/24/25/16) dan sisi kanan (5/6/19/26) selalu diberi duty yang
sama oleh `hardware.drive(kiri, kanan)` — jadi kontrolnya tetap dua angka, tapi
torsi dibagi empat roda dan tiap kanal hanya menanggung satu motor (±0,6 A saat
maju biasa, jauh dari batas 1,2–1,5 A).

Yang **tidak** boleh: memparalel OUT1/OUT2 dua modul ke satu motor (dua jembatan H
saling melawan), atau menaruh dua motor pada satu kanal (arus dobel, dan dua motor
yang tidak identik akan saling menyeret).

### Konsekuensi mekanik 4WD

- **Tidak ada castor.** Keempat roda menopang bodi sekaligus menggerakkan, jadi
  tidak ada roda yang cuma "ikut".
- **Belok = mengerem sisi dalam.** Karena tidak ada kemudi, robot berbelok dengan
  membuat roda kiri dan kanan berlawanan. Pada bodi kaku, empat roda akan sedikit
  menyeret (skid) saat berbelok — di lantai keramik/licin tidak terasa, di karpet
  tebal butuh duty belok lebih tinggi (`SPEED_PUTAR`).
- **Diameter roda harus sama.** Satu roda lebih kecil membuat robot menarik ke
  sisi itu terus-menerus; kalau terjadi, `KP_BELOK` akan terus mengoreksi dan
  gerak jadi mengayun.

### Daya

- Baterai 2S → **VM** MX1508 lewat saklar, GND baterai–Pi–driver **disatukan**. GND yang tidak
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
.venv/bin/python main.py --dry-run --seconds 3      # hanya mencatat, tidak menggerakkan motor

# tiap roda sendiri-sendiri, 1,5 s
.venv/bin/python - <<'PY'
import hardware, time
hw = hardware.make()
for nama in ("kiri_depan", "kiri_belakang", "kanan_depan", "kanan_belakang"):
    print(nama, "-> maju")
    getattr(hw, nama).value = 0.4
    time.sleep(1.5)
    getattr(hw, nama).value = 0.0
    time.sleep(0.4)
hw.stop()
PY

# berbelok di tempat: kiri maju, kanan mundur
.venv/bin/python -c "import hardware,time;hw=hardware.make();hw.drive(0.45,-0.45);time.sleep(1.5);hw.stop()"
```

Periksa satu per satu: keempat roda harus berputar **maju** (menuju depan bodi).
Kalau satu roda terbalik, tukar pin maju/mundur motor itu di `config.py` — jangan
tukar kabel di driver secara asal, karena urutan pin juga dipakai saat memutar
badan. Uji belok terakhir memastikan kedua sisi melawan arah dengan benar; kalau
robot justru maju lurus, salah satu sisi masih terbalik.

## 3. Pasang Raspberry Pi OS Trixie dan pastikan kamera terlihat

Repo ini diuji untuk **Raspberry Pi OS (32-bit) Trixie** — image "Raspberry Pi OS
(32-bit)" dengan Desktop, Debian 13, Python 3.13, OpenCV 4.10 dari apt. Image
**64-bit** juga jalan dengan kode yang sama, tapi sisa RAM untuk kamera + model
lebih ketat di board 1 GB.

Image Desktop boleh dipakai, tapi robot tidak butuh layar. Kalau RAM terasa sesak
saat model + kamera jalan, ubah boot ke console:

```bash
sudo raspi-config   # System Options -> Boot / Auto Login -> Console autologin
```

Itu mematikan desktop (±250 MB) dan tetap menyisakan SSH.

```bash
grep VERSION_CODENAME /etc/os-release          # harus: VERSION_CODENAME=trixie

sudo apt update
sudo apt install -y python3-venv python3-numpy python3-gpiozero git
sudo apt install -y python3-lgpio || echo "python3-lgpio tidak ada; lewati"
#  ^ lgpio ada di repo Raspberry Pi, tidak di Debian. gpiozero tetap jalan
#    dengan backend lain kalau paket ini tidak tersedia.

git clone https://github.com/haudilulum/robot-drink-tracking
cd robot-drink-tracking

# OpenCV TIDAK dari apt: versi apt (4.10 di Trixie) memuat ONNX opset baru
# tanpa error tapi hasil forward-nya salah -> deteksi selalu kosong.
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --index-url https://www.piwheels.org/simple \
    --extra-index-url https://pypi.org/simple "opencv-python-headless>=5.0"

.venv/bin/python - <<'PY'
import gpiozero, cv2, sys
print("python  :", sys.version.split()[0])
print("opencv  :", cv2.__version__, "| dnn:", hasattr(cv2, "dnn"))
print("gpiozero:", gpiozero.__version__, "| backend:", gpiozero.Device.pin_factory)
PY
```

Yang harus terlihat: `python 3.13.x`, `opencv 5.x | dnn: True`, dan
`gpiozero ... backend:` berisi sesuatu seperti `LGPIOPinFactory` (bukan `None`).
Kalau `dnn: False`, wheel OpenCV gagal terpasang — ulangi perintah `pip` di atas.

**Kenapa bukan `apt install python3-opencv`.** Stack yang sama sudah dipakai
proyek human tracking di board dan OS ini, dan pelajarannya jelas: OpenCV 4.10
dari apt *berhasil memuat* model ONNX hasil ekspor Ultralytics (opset 20) tanpa
satu pun pesan error, tetapi hasil forward-nya salah sehingga deteksi tampak
kosong — persis seperti model rusak. Wheel `opencv-python-headless` 5.x untuk
armv7l disediakan piwheels, jadi pasang di venv seperti di atas dan jalankan
semua perintah dengan `.venv/bin/python`.

Seluruh perintah Python di README ini memakai `.venv/bin/python`; installer
(`scripts/install_pi.sh`) membuat venv itu dan menuliskan path-nya ke unit
systemd, jadi `systemctl start` juga memakai OpenCV yang benar.

Cek kamera (resolusi, FPS, dan frame benar-benar terbaca):

```bash
.venv/bin/python -c "import cv2;c=cv2.VideoCapture(0);c.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'));ok,f=c.read();print('kamera',int(c.get(3)),'x',int(c.get(4)),'@',round(c.get(5)),'fps','frame=ada' if ok else 'frame=GAGAL')"
```

Yang harus terlihat: `640 x 480 @ 30 fps frame=ada`. Kalau `frame=GAGAL`, cek
kabel/kamera lain yang memakai `/dev/video0` (`ls /dev/video*`). Kalau FPS
tertulis 5, kamera tidak masuk mode MJPG — gambar akan tersendat dan robot
terlihat "berpikir lama".

Cek kedua tombol tanpa menggerakkan motor:

```bash
.venv/bin/python -c "import hardware;hw=hardware.make();print('tekan tombol (Ctrl-C keluar)');[print('  ->',hw.read_button()) or __import__('time').sleep(0.1) for _ in iter(int,1)]"
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
4. Train **YOLO11 nano** (Roboflow hosted atau Colab).
5. Lihat mAP50 dan confusion matrix. Kalau kelas tertukar, tambah foto yang mirip
   dengan kasus yang salah, jangan menambah epoch.

### 4c. Pilih arsitektur yang bisa jalan di `cv2.dnn`

Roboflow menawarkan beberapa arsitektur; tidak semuanya bisa dipakai robot ini.
Yang menentukan adalah bentuk keluaran ONNX-nya, karena `vision.py` membaca tensor
mentah `(1, 4+nc, N)` lalu melakukan NMS sendiri.

| Pilihan di Roboflow | Untuk robot ini | Sebabnya |
|---|---|---|
| **YOLO11** (nano / small) | **pakai ini** | keluaran sama seperti YOLOv8 yang sudah terbukti di Pi 3B+ |
| YOLOv12 | hindari | blok attention lebih berat; belum tentu semua ops-nya didukung `cv2.dnn` di Pi |
| YOLO26 | tidak cocok | sudah *NMS-free* (end-to-end), keluarannya `(1, 300, 6)` — parser kita butuh tensor mentah |
| YOLO-NAS | tidak dipakai | lebih berat, butuh `super-gradients` untuk ekspor |
| RF-DETR | tidak cocok | transformer; butuh decoder sendiri dan terlalu berat untuk CPU Pi 3B+ |
| Roboflow 3.0 | tidak dipakai | dijalankan lewat Roboflow Inference (butuh internet, tidak tersedia untuk Pi 3B+ 32-bit) |
| YOLOLite | tidak dipakai | ditujukan untuk runtime Roboflow, bukan ONNX `cv2.dnn` |

Ukuran: **nano** kalau tersedia, kalau hanya ada Small tetap boleh — selisih
waktunya kecil di 320, tapi nano lebih ringan di RAM 1 GB.

### 4d. Ekspor ke ONNX

Di Roboflow: **Deploy → ONNX**, ukuran input **320×320**, tanpa NMS
(*non-end-to-end*). Unduh, lalu di Pi:

```bash
mkdir -p models
# salin hasil unduhan ke sini
cp ~/unduhan/model.onnx models/kopi_teh.onnx
```

Dua hal yang harus cocok, kalau tidak deteksi akan kosong atau kelas tertukar:

- `YOLO_IMGSZ` di `config.py` = ukuran input saat export (default `320`).
- `YOLO_KELAS` = urutan kelas di `data.yaml` Roboflow (default `["kopi","teh"]`).

Kalau export memakai 640, ubah `YOLO_IMGSZ = 640`; jangan biarkan 320 — blob dan
model harus seukuran. Konsekuensinya satu deteksi naik dari ±1 s ke ±4 s.

## 5. Uji deteksi sebelum menyentuh motor

```bash
.venv/bin/python main.py --vision yolo --debug foto/debug --diam
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
`.venv/bin/python main.py --debug foto/debug`, baca `w=` saat kotak menempel di gelas, lalu
set `W_BERHENTI` ke angka itu dan `W_MULAI_PELAN` = `W_BERHENTI` − 0,18.

**c. `DERAJAT_PER_DETIK` (90)** — kecepatan putar sebenarnya. Jalankan mode cari,
hitung berapa detik robot berputar sampai 360° (12 langkah × 30°), lalu
`DERAJAT_PER_DETIK = 360 / detik`. Menyapu lebih cepat dari ±45°/s membuat gelas
terlewat di antara dua deteksi yang berjarak ±1 s.

**d. `KP_BELOK` (0,85)** — koreksi belok. Terlalu besar: robot mengayun
kiri-kanan. Terlalu kecil: gelas keluar frame sebelum sempat dikoreksi.

Setelah empat angka ini benar, robot sudah memenuhi konsep: tekan tombol,
menyapu mencari, mendekat, berhenti.

Tandanya hanya gerak: **sampai** = robot diam tepat di depan gelas, **gagal** =
robot diam tanpa pernah mendekat (sebabnya ada di log).

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
.venv/bin/python main.py                     # mode debug di terminal
```

## 8. Uji tanpa hardware (untuk mengubah kode)

Semua logika bisa diuji tanpa Pi, kamera, atau model — cukup Python + OpenCV:

```bash
.venv/bin/python main.py --dry-run --seconds 10                  # PB1 otomatis, detektor palsu
.venv/bin/python main.py --dry-run --seconds 10 --tombol-uji teh
.venv/bin/python -m unittest discover -s tests                   # 56 tes
.venv/bin/python tests/uji_integrasi_dunia.py                    # loop tertutup dunia sintetis
```

**Dua lapis, dua pertanyaan berbeda.**

`unittest discover` (56 tes, ±2 s) menjawab *"apakah satu aturan masih benar"* —
satu tes untuk satu aturan, jadi kalau gagal, namanya langsung menunjuk penyebabnya.
`uji_integrasi_dunia.py` menjawab *"apakah semuanya bekerja bersama"*: kamera
sintetis menggeser gelas ke tengah saat robot berbelok dan membesarkannya saat
robot maju, lalu memeriksa robot berhenti dengan gelas di tengah frame
(`cx_akhir=0.50`).

Urutannya: unit test dulu. Kalau integrasi yang gagal tanpa unit test, Anda hanya
tahu "robot tidak sampai" dan harus menebak apakah itu median lebar, penjaga kotak
tepi, timeout, atau pemilihan target. Dengan unit test lulus, kegagalan integrasi
berarti masalahnya di interaksi antar-bagian, bukan di satu aturan.

Yang dicek masing-masing berkas tes:

| Berkas | Menjaga |
|---|---|
| `test_config.py` (15) | peta pin tidak dobel, GPIO 12/18/22 kosong, urutan kelas, ambang berurutan |
| `test_state.py` (22) | state machine: PB, timeout, target hilang sesaat, median lebar, kotak di tepi |
| `test_vision.py` (10) | pemilihan target + penjaga jalur tunggal (HSV/bentuk tidak boleh kembali) |
| `test_async.py` (5) | deteksi 1,2 s tidak menahan loop, hasil basi dibuang |
| `test_alur.py` (4) | optical flow: kotak mengikuti gerakan, dilepas saat tekstur hilang |

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

Di Pi 3B+, YOLO nano ONNX 640×640 lewat `cv2.dnn` butuh **±1,2 s/frame** (terukur
1171 ms pada YOLOv8n, YOLO11n sekelas), sementara 320 diperkirakan ±1 s. Karena itu:

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
| `hardware.py` | motor/tombol + versi palsu untuk tes |
| `vision.py` | kamera, `YoloDetector`, `AsyncDetector`, `AlurDetector`, `FakeDetector` |
| `main.py` | state machine + CLI |
| `scripts/install_pi.sh` | dependensi (Trixie) + cek pustaka/kamera + unit systemd |
| `tests/` | 5 berkas unit test (56 tes) + `uji_integrasi_dunia.py` (loop tertutup, manual) |

### D. Kalau bermasalah

- **Deteksi selalu kosong padahal model ada** — cek `.venv/bin/python -c "import cv2;print(cv2.__version__)"`.
  Kalau yang muncul 4.x, itu OpenCV dari apt: model termuat tanpa error tapi
  hasil forward-nya salah. Pasang ulang `opencv-python-headless>=5.0` di venv.
- **`model YOLO belum ada`** — ONNX belum ditaruh di `models/kopi_teh.onnx`.
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
- **`gpiozero` bilang `no pin factory found`** — `ls /dev/gpiochip*` harus ada;
  kalau tidak, paket `python3-lgpio` belum terpasang atau board butuh reboot.
  Jalankan juga sebagai user biasa (anggota grup `gpio`), bukan hanya root.
- **`pip install` menolak dengan `externally-managed-environment`** — memang
  disengaja di Trixie; pakai `apt install python3-...` saja.
- **Robot tidak bergerak walau duty 0,4** — deadband motor atau baterai drop; ukur
  tegangan VM saat motor jalan.
- **Robot menarik ke satu sisi walau lurus** — diameter roda tidak sama atau satu
  motor lebih lemah; tukar posisi roda kiri/kanan untuk memastikan penyebabnya.
- **Belok tersendat / roda berdecit** — normal pada 4WD bodi kaku (roda menyeret);
  naikkan `SPEED_PUTAR`, atau kurangi grip roda depan.
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
