"""Konfigurasi robot kopi-teh: PB1 -> cari & dekati kopi, PB2 -> cari & dekati teh.

Semua angka yang biasanya perlu disetel ada di file ini, jangan disebar ke file lain.
Pin memakai penomoran BCM (bukan nomor fisik header).

Catatan penting soal "membedakan kopi dan teh": isi kopi dan teh sama-sama cairan
gelap, jadi warna cairan saja TIDAK cukup (lihat README bagian "Cara membedakan").
Yang dipakai robot adalah penanda pada gelas (tutup/stiker/gelas berwarna).
"""

# ---------------------------------------------------------------- Pin (BCM)
# Motor kiri  : MX1508 kanal A (PWM masuk ke IN, arah dari pin pasangannya)
# Motor kanan : MX1508 kanal B
PIN_MOTOR_KIRI_MAJU = 23
PIN_MOTOR_KIRI_MUNDUR = 24
PIN_MOTOR_KANAN_MAJU = 5
PIN_MOTOR_KANAN_MUNDUR = 6

PIN_PB_KOPI = 17            # PB1, tombol ke GND, pull-up internal, tanpa resistor
PIN_PB_TEH = 27             # PB2
PIN_LED = 22                # LED indikator + resistor 330 ohm ke GND
PIN_BUZZER = 18             # buzzer aktif (3-5 V) atau lewat transistor
PIN_SERVO_PAN = 12          # opsional, SG90; VCC dari 5 V eksternal, GND disatukan

# Servo pan dimatikan secara default: kamera dipasang tetap dan robot mencari
# dengan memutar badannya. Nyalakan hanya kalau servonya benar-benar terpasang
# DAN driver PWM-nya stabil (gpiozero butuh pigpio/lgpio; tanpa itu servo gemetar).
PAKAI_SERVO_PAN = False

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
PROC_W, PROC_H = 320, 240   # pemrosesan diperkecil: ~4x lebih cepat di Pi 3B+
KAMERA_MJPG = True          # wajib di Pi 3B+: tanpa MJPG frame drop jadi ~5 FPS
KAMERA_BUFFER = 1           # selalu ambil frame terbaru, jangan antre frame lama
WARMUP_FRAME = 10           # buang frame awal (kamera masih gelap/AE belum stabil)

# ---------------------------------------------------------------- Visi
# "penanda" : HSV blob pada penanda warna gelas  -> tanpa dataset, paling ringan
# "bentuk"  : siluet gelas, dibedakan dari rasio tinggi/lebar (mug vs gelas tinggi)
# "yolo"    : model 2 kelas hasil latih sendiri, dijalankan lewat cv2.dnn (ONNX)
# "fake"    : simulasi, untuk menguji state machine tanpa kamera
VISION_BACKEND = "penanda"

CONF_MIN = 0.35             # di bawah ini dianggap "tidak yakin"
LUAS_MIN_PIKSEL = 900       # pada resolusi PROC (320x240): ~1,2% frame

# Rentang HSV untuk penanda (OpenCV: H 0..179, S 0..255, V 0..255).
# Nilai default: kopi = tutup/stiker coklat-oranye, teh = hijau.
# Satu label boleh punya beberapa rentang (mis. merah butuh dua sisi H).
WARNA = {
    "kopi": [((5, 90, 40), (22, 255, 220))],
    "teh": [((35, 70, 40), (85, 255, 255))],
}

# Rentang HSV siluet gelas untuk backend "bentuk" (default: gelas terang/putih).
WARNA_GELAS = [((0, 0, 110), (179, 80, 255))]

# Rasio tinggi/lebar siluet gelas -> label. Diukur dari bbox, jadi harus
# dikalibrasi untuk gelas yang benar-benar dipakai (lihat README).
BENTUK = {
    "kopi": (0.85, 1.45),   # mug lebar
    "teh": (1.55, 3.20),    # gelas tinggi
}

# Backend yolo: path model ONNX 2 kelas dan urutan nama kelasnya.
YOLO_MODEL_PATH = "models/kopi_teh_yolov8n.onnx"
YOLO_KELAS = ["kopi", "teh"]     # urutan HARUS sama dengan saat training
YOLO_IMGSZ = 320                 # 320 cukup; 640 terlalu berat untuk Pi 3B+
YOLO_NMS = 0.45
YOLO_ASYNC = True               # deteksi di thread terpisah (WAJIB: YOLO ~1,2 s/frame)
YOLO_ALUR = True                # geser kotak dengan optical flow di antara deteksi
YOLO_ASYNC_JEDA_S = 0.35        # jarak antar pemeriksaan; 0 = secepat thread mampu
ASYNC_BASI_S = 1.5              # hasil deteksi lebih tua dari ini dianggap hilang


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v
