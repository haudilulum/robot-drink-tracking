"""Konfigurasi robot kopi-teh: PB1 -> cari & dekati kopi, PB2 -> cari & dekati teh.

Semua angka yang biasanya perlu disetel ada di file ini, jangan disebar ke file lain.
Pin memakai penomoran BCM (bukan nomor fisik header).

Catatan penting soal "membedakan kopi dan teh": isi kopi dan teh sama-sama cairan
gelap, jadi warna cairan saja TIDAK cukup (lihat README "Satu jalur").
Jalur yang dipakai: model YOLO hasil training (Roboflow/Colab) diekspor ke ONNX.
Tidak ada ambang warna di proyek ini; tidak ada yang perlu dikalibrasi HSV.
"""

# ---------------------------------------------------------------- Pin (BCM)
# 4WD skid-steer: 4 motor, 4 kanal, tiap motor punya kanal sendiri (tidak ada yang
# diparalel). Dua modul MX1508 x 2 kanal, delapan pin total.
#
#   modul 1 kanal A -> roda kiri depan   : IN1=23 (PWM), IN2=24
#   modul 1 kanal B -> roda kiri belakang: IN3=25 (PWM), IN4=16
#   modul 2 kanal A -> roda kanan depan  : IN1=5  (PWM), IN2=6
#   modul 2 kanal B -> roda kanan belakang: IN3=19 (PWM), IN4=26
#
# 2 pin per motor sudah cukup karena MX1508 tidak punya ENA/ENB: PWM masuk ke pin
# IN, arah ditentukan pin pasangannya (IN1 PWM + IN2 rendah = maju, dibalik =
# mundur). Pasangan kiri/kanan selalu diberi duty yang sama oleh lapisan hardware.
PIN_MOTOR_KIRI_DEPAN_MAJU = 23
PIN_MOTOR_KIRI_DEPAN_MUNDUR = 24
PIN_MOTOR_KIRI_BELAKANG_MAJU = 25
PIN_MOTOR_KIRI_BELAKANG_MUNDUR = 16
PIN_MOTOR_KANAN_DEPAN_MAJU = 5
PIN_MOTOR_KANAN_DEPAN_MUNDUR = 6
PIN_MOTOR_KANAN_BELAKANG_MAJU = 19
PIN_MOTOR_KANAN_BELAKANG_MUNDUR = 26

PIN_PB_KOPI = 17            # PB1, tombol ke GND, pull-up internal, tanpa resistor
PIN_PB_TEH = 27             # PB2
PIN_LED = 22                # LED indikator + resistor 330 ohm ke GND
PIN_BUZZER = 18             # buzzer aktif (3-5 V) atau lewat transistor

# GPIO12 sengaja tidak dipakai: kamera dipasang tetap di bodi, robot "melihat ke
# samping" dengan memutar badannya sendiri. Tidak ada servo pan di proyek ini.

# ---------------------------------------------------------------- Tombol
BOUNCE_S = 0.06             # debounce gpiozero; event-driven, tidak ada press yang hilang

# ---------------------------------------------------------------- Motor (duty 0..1)
SPEED_MAJU = 0.55           # kecepatan dasar saat mendekat
SPEED_MIN = 0.35            # batas bawah yang masih menggerakkan roda (kalibrasi!)
KOREKSI_MAKS = 0.45         # batas koreksi belok
KP_BELOK = 0.85             # P-gain: error tengah frame -> belok
SPEED_PUTAR = 0.50          # duty saat memutar badan untuk mencari
W_MULAI_PELAN = 0.30        # lebar bbox / lebar frame saat mulai mengurangi gas
W_BERHENTI = 0.48           # lebar bbox / lebar frame -> anggap sudah sampai
                            # lebar kotak = f * LEBAR_GELAS / Z (Z = jarak), jadi
                            # ambang ini setara jarak berhenti tertentu: ukur
                            # sekali di lantai, catat w dari log --debug.
W_FILTER_N = 3              # median lebar N deteksi terakhir (tekan jitter)
TEPI_FRAME = 0.02           # kotak lebih dekat dari ini ke tepi = terpotong

# ---------------------------------------------------------------- Pencarian (putar-periksa)
SUDUT_LANGKAH = 30          # derajat per langkah putar
DERAJAT_PER_DETIK = 90      # kecepatan putar terukur (kalibrasi di lantai)
MIN_PUTAR_S = 0.18          # kompensasi deadband motor saat mulai berputar
JEDA_PERIKSA_S = 0.12       # diamkan chassis dulu sebelum kamera dipercaya
LANGKAH_PER_ARAH = 12       # setelah 12 langkah (360 derajat) balik arah putar
FRAME_STABIL = 3            # butuh N frame berturut-turut sebelum target dipercaya

# ---------------------------------------------------------------- Waktu
TIMEOUT_CARI_S = 20.0       # menyerah kalau target tak ketemu
TIMEOUT_DEKATI_S = 30.0     # menyerah kalau sudah dekat tapi tak pernah sampai
GRACE_HILANG_S = 1.0        # toleransi target hilang sesaat saat mendekat
LOOP_HZ = 20
PAUSE_SAMPAI_S = 0.25       # jeda sebelum kembali IDLE setelah sampai

# ---------------------------------------------------------------- Kamera
KAMERA_INDEKS = 0
FRAME_W, FRAME_H = 640, 480
KAMERA_MJPG = True          # wajib di Pi 3B+: tanpa MJPG frame drop jadi ~5 FPS
KAMERA_BUFFER = 1           # selalu ambil frame terbaru, jangan antre frame lama
WARMUP_FRAME = 10           # buang frame awal (kamera masih gelap/AE belum stabil)

# ---------------------------------------------------------------- Visi
# Satu jalur identifikasi: model YOLO 2 kelas (kopi, teh) hasil training sendiri,
# diekspor ke ONNX. Tidak ada ambang warna di proyek ini.
#   "yolo" : model di thread terpisah + kotak dirapatkan optical flow
#   "fake" : pengganti saat --dry-run (tanpa kamera, tanpa model)
VISION_BACKEND = "yolo"

PROC_W, PROC_H = 320, 240        # frame kecil untuk optical flow & hemat memori
                                 # (kamera tetap 640x480; hanya flow memakai 320x240)

YOLO_MODEL_PATH = "models/kopi_teh_yolov8n.onnx"
YOLO_KELAS = ["kopi", "teh"]     # urutan HARUS sama dengan saat training
YOLO_IMGSZ = 320                 # 320 cukup; 640 terlalu berat untuk Pi 3B+
YOLO_NMS = 0.45
CONF_MIN = 0.35                  # ambang keyakinan deteksi
YOLO_ALUR = True                # geser kotak dengan optical flow di antara deteksi
YOLO_ASYNC_JEDA_S = 0.35        # jarak antar pemeriksaan; 0 = secepat thread mampu
ASYNC_BASI_S = 1.5              # hasil deteksi lebih tua dari ini dianggap hilang

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v
