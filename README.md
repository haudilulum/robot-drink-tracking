# Robot Drink Tracking

Robot beroda diferensial: tekan **PB1 → cari & dekati kopi**, tekan **PB2 → cari &
dekati teh**. Robot memutar badannya untuk menyapu pandangan, mengunci gelas
target, maju sampai jarak berhenti, lalu berhenti + beep.

Target perangkat: **Raspberry Pi 3B+ (1 GB)**, Raspberry Pi OS 32-bit, webcam UVC,
2× modul driver MX1508, 2 motor DC gearbox.

```
IDLE ──PB1/PB2──▶ CARI (putar 30°, periksa, ulangi) ──target stabil──▶ DEKATI
DEKATI ──gelas cukup besar──▶ SAMPAI (stop + beep 1×) ──▶ IDLE
DEKATI ──target hilang > 1 s──▶ CARI
CARI   ──20 s tanpa target──▶ GAGAL (beep 2×) ──▶ IDLE
DEKATI ──30 s tidak sampai──▶ GAGAL (beep 2×) ──▶ IDLE
tombol sama ditekan saat bergerak ──▶ berhenti seketika
tombol lain ditekan saat bergerak ──▶ ganti target, mulai cari lagi
```

## Masalah utama: kopi dan teh terlihat sama

Isi kopi dan teh sama-sama cairan gelap. **Dari piksel saja keduanya tidak bisa
dibedakan** — ini bukan soal model yang kurang canggih, informasinya memang tidak
ada di gambar. Jadi yang dibedakan adalah penandanya. Tiga backend disediakan:

| Backend | Yang dibedakan | Butuh | Kelebihan / kekurangan |
|---|---|---|---|
| `penanda` (default) | warna stiker/tutup/gelas | penanda warna beda | paling ringan (~25 FPS di Pi 3B+), tanpa dataset; salah kalau penanda tertutup tangan |
| `bentuk` | siluet gelas: mug lebar vs gelas tinggi | gelas yang bentuknya beda | tanpa penanda; rapuh kalau gelas separuh di belakang benda lain |
| `yolo` | model 2 kelas hasil latih | dataset + training | paling tahan variasi; butuh ±300 foto dan waktu training |

### Kalau memilih jalur YOLO (Roboflow)

Pembuatan model dilakukan di laptop/Colab, bukan di Pi — jadi biaya training
tidak jadi soal. Yang jadi soal adalah **inference**: YOLOv8n ONNX 640×640 di
`cv2.dnn` pada CPU kelas Cortex-A53 terukur **1171 ms/frame (0,85 FPS)**,
sementara HSV blob 320×240 hanya **4,9 ms (≈200 FPS)**.

Karena itu backend `yolo` sekarang otomatis membungkus model dalam
`vision.AsyncDetector`: model berjalan di thread sendiri, loop kendali tetap
mengambil hasil terakhir tanpa menunggu (terukur: loop tetap ~16–20 Hz saat model
butuh 1,2 s per frame). Hasil yang lebih tua dari `ASYNC_BASI_S` dibuang agar
robot tidak mengejar posisi gelas lama. Backend `yolo-sync` (menahan loop) hanya
untuk menyetel/mengukur.

Alur pembuatan model:

1. `python3 tangkap.py --jumlah 300` — foto dari **kamera dan sudut pemasangan
   yang sama** dengan saat dipakai; sertakan variasi terang/gelap dan posisi.
2. Upload ke Roboflow, beri label `kopi` / `teh`, augmentasi cahaya + blur.
3. Train (Roboflow hosted atau Colab gratis), export **ONNX** dengan input 320.
4. `models/kopi_teh_yolov8n.onnx`, lalu `python3 main.py --vision yolo`.
5. `YOLO_KELAS` di `config.py` harus sama urutannya dengan saat training.

Yang perlu disadari: model tetap hanya bisa membedakan apa yang **terlihat beda**.
Kalau dua gelasnya identik, akurasi training tidak menolong — penandanya tetap
yang dipakai. YOLO menggantikan kerapuhan HSV terhadap cahaya, bukan menggantikan
penanda.

Saran praktis: **tempel stiker/lakban warna di gelas** (kopi = coklat/oranye,
teh = hijau) lalu pakai backend `penanda`. Ini yang paling cepat stabil dan
paling mudah dibela saat demo.

## Pin (BCM, bukan nomor fisik header)

| Fungsi | GPIO | Catatan |
|---|---|---|
| MX1508 kiri IN1 / IN2 | 23 / 24 | PWM masuk ke pin IN, arah dari pin pasangannya |
| MX1508 kanan IN1 / IN2 | 5 / 6 |  |
| PB1 (kopi) | 17 | tombol ke GND, pull-up internal, tanpa resistor |
| PB2 (teh) | 27 | idem |
| LED status | 22 | + resistor 330 Ω ke GND |
| Buzzer | 18 | buzzer aktif 3–5 V, atau lewat transistor |
| Servo pan (opsional) | 12 | default **dimatikan** (`PAKAI_SERVO_PAN=False`), kamera dipasang tetap |

Daya: 2S 7.4 V ke VM MX1508 (maksimum 10 V), GND baterai–Pi–driver **disatukan**.
Jangan mengambil daya motor dari 5 V Pi, dan jangan memparalel dua motor pada satu
kanal MX1508 (batas kontinu ±1,2–1,5 A per kanal).

Servo SG90 hanya dipakai kalau memang terpasang, dan PWM-nya harus dari
**lgpio/pigpio** — dengan RPi.GPIO software PWM servo akan gemetar.

## Pasang di Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy python3-gpiozero python3-lgpio
cd ~/robot-drink-tracking
python3 tangkap.py --cek        # ukur FPS kamera + kecerahan
python3 main.py
```

Autostart saat boot:

```bash
bash scripts/install_pi.sh
sudo systemctl status robot-drink-tracking
journalctl -u robot-drink-tracking -f
```

Backend `yolo` tidak memakai `ultralytics`/torch — model ONNX dijalankan lewat
`cv2.dnn`, supaya RAM 1 GB tidak habis. Taruh model di `models/kopi_teh_yolov8n.onnx`
lalu jalankan `python3 main.py --vision yolo`.

## Kalibrasi sebelum dipakai di lantai

Angka di `config.py` adalah nilai awal, bukan hasil ukur. Empat langkah ini wajib:

1. **Warna penanda** — `python3 tangkap.py --jumlah 3`, lalu
   `python3 kalibrasi.py foto/frame_1.jpg --auto --label kopi`. Tempel hasilnya ke
   `config.py` bagian `WARNA`. Lakukan di ruangan tempat robot dipakai, bukan di
   meja terang. Ulangi untuk `teh`.
2. **Jarak berhenti** — letakkan gelas di jarak berhenti yang diinginkan, jalankan
   `python3 main.py --debug foto/debug`, baca `w=` pada log, set `W_BERHENTI` ke nilai itu (dan
   `W_MULAI_PELAN` ±0,18 lebih kecil).
3. **Deadband motor** — naikkan `SPEED_MIN` sampai robot benar-benar bergerak
   dari diam (motor TT + 2S biasanya 0,30–0,40). Kalau robot diam bergetar,
   `SPEED_MIN` terlalu rendah.
4. **Sudut putar** — ukur dengan busur: jalankan mode CARI, tandai posisi awal,
   bandingkan dengan posisi setelah satu langkah. Sesuaikan `DERAJAT_PER_DETIK`
   supaya 12 langkah ≈ 360°.

Yang biasanya masih perlu disetel setelah itu: `KP_BELOK` (terlalu besar =
osilasi kiri-kanan) dan `SPEED_MAJU`.

## Uji tanpa hardware

```bash
python3 main.py --dry-run --seconds 10                 # PB1 otomatis
python3 main.py --dry-run --seconds 10 --tombol-uji teh
python3 -m unittest discover -s tests                  # 59 tes
python3 tests/uji_integrasi_dunia.py                   # kamera sintetis closed-loop
```

`uji_integrasi_dunia.py` menutup loop kendali: gelas bergeser ke tengah saat robot
berbelok dan membesar saat robot maju, jadi terlihat apakah robot benar-benar
berhenti dengan gelas di tengah — bukan cuma apakah detektor menyala.

## Berkas

| Berkas | Isi |
|---|---|
| `config.py` | semua pin, ambang, gain, rentang HSV |
| `hardware.py` | motor/tombol/LED/buzzer/servo + versi palsu untuk tes |
| `vision.py` | kamera, deteksi `penanda` / `bentuk` / `yolo` / `fake` |
| `main.py` | state machine + CLI |
| `kalibrasi.py` | saran rentang HSV dari foto (tanpa GUI) |
| `tangkap.py` | ambil foto, rekam video, ukur FPS & kecerahan |
| `tests/` | 59 unit test + uji integrasi |

## Troubleshooting

- **Kamera gelap / 5 FPS.** Pastikan `KAMERA_MJPG=True`; tanpa MJPG webcam jatuh ke
  YUYV dan frame drop. Cek dengan `python3 tangkap.py --cek`.
- **Robot tidak bergerak walau duty 0,4.** Deadband motor terlalu tinggi atau
  baterai drop. Ukur tegangan VM saat motor jalan.
- **Robot berputar terus di IDLE.** Pin motor tertukar dengan pin tombol, atau
  `SPEED_MIN` terlalu tinggi sehingga motor tidak pernah benar-benar 0.
- **Meja ikut terdeteksi sebagai kopi.** Saturasi penanda terlalu rendah —
  `kalibrasi.py` akan memperingatkan kalau S < 45.
- **Robot berhenti terlalu cepat.** `W_BERHENTI` terlalu kecil, atau gelas
  terpotong tepi frame sehingga lebar kotak tidak pernah mencapai ambang.
  Pastikan gelas masuk penuh di frame saat mendekat.
- **Servo gemetar.** Pakai `python3-gpiozero` + `python3-lgpio`, atau biarkan
  `PAKAI_SERVO_PAN=False` (default) dan biarkan badan robot yang menyapu.

## Yang belum ada

- Pengukur jarak sesungguhnya (VL53L0X/ultrasonik) — sekarang jarak ditebak dari
  lebar kotak, jadi akurasinya bergantung pada ukuran penanda.
- Deteksi halangan saat maju (minimal bumper switch) dan penghindaran rintangan.
- Log CSV per sesi (target, waktu tempuh, `w` akhir) untuk evaluasi.
- Dataset & training model 2 kelas; kerangka skripnya ada di `~/coffee-tea-dataset`
  (`prepare.py`, `train_colab.ipynb`) tapi belum ada gambarnya.
