"""Visi: mengubah frame kamera menjadi daftar kandidat target.

Setiap deteksi: (label, cx, cy, w, h, conf) dengan semua nilai ternormalisasi 0..1
terhadap ukuran frame. ``w`` dipakai sebagai ukuran jarak: makin lebar kotak,
makin dekat gelasnya.

Backend yang tersedia (pilih di config.VISION_BACKEND atau --vision):
  yolo    : model 2 kelas ONNX lewat cv2.dnn, dijalankan di thread terpisah
            (tanpa torch; wajib async karena satu frame butuh ~1,2 s di Pi 3B+)
  fake    : simulasi untuk menguji state machine tanpa kamera
"""

import os
import threading
import time

import config as C

try:
    import cv2
    import numpy as np
    ADA_CV = True
except Exception:                       # pragma: no cover - board tanpa opencv
    ADA_CV = False


# --------------------------------------------------------------------- kamera
class Kamera:
    """Webcam UVC dengan pengaturan yang benar untuk Pi 3B+ (MJPG + bufer kecil)."""

    def __init__(self, indeks=None, lebar=None, tinggi=None):
        if not ADA_CV:
            raise RuntimeError("opencv belum terpasang (sudo apt install python3-opencv)")
        self.indeks = C.KAMERA_INDEKS if indeks is None else indeks
        self.lebar = C.FRAME_W if lebar is None else lebar
        self.tinggi = C.FRAME_H if tinggi is None else tinggi
        self.cap = cv2.VideoCapture(self.indeks)
        if not self.cap.isOpened():
            raise RuntimeError(f"kamera {self.indeks} tidak bisa dibuka (cek /dev/video*)")
        if C.KAMERA_MJPG:
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.lebar)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.tinggi)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, C.KAMERA_BUFFER)
        self.ukuran = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                       int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self._hangat = 0
        for _ in range(C.WARMUP_FRAME):
            self.cap.read()

    def baca(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def tutup(self):
        self.cap.release()


# ------------------------------------------------------------------- deteksi
class Deteksi:
    __slots__ = ("label", "cx", "cy", "w", "h", "conf")

    def __init__(self, label, cx, cy, w, h, conf):
        self.label = label
        self.cx = cx
        self.cy = cy
        self.w = w
        self.h = h
        self.conf = conf

    def __repr__(self):
        return (f"{self.label}(cx={self.cx:.2f}, cy={self.cy:.2f}, "
                f"w={self.w:.2f}, h={self.h:.2f}, c={self.conf:.2f})")


def pilih_target(daftar, target):
    """Kandidat paling dekat (kotak terlebar) untuk label yang diminta."""
    kandidat = [d for d in daftar
                if d.label == target and d.conf >= C.CONF_MIN]
    return max(kandidat, key=lambda d: d.w) if kandidat else None


class DetektorKamera:
    """Dasar untuk backend yang membaca dari kamera.

    ``kamera=None`` berarti detektor ini tidak memegang kamera sama sekali —
    dipakai tes yang menyuntikkan frame sendiri lewat ``detect(frame)``.
    """

    def __init__(self, kamera=None):
        self.kamera = kamera

    def read(self):
        if self.kamera is None:
            raise RuntimeError("detektor dibuat tanpa kamera; gunakan detect(frame)")
        return self.kamera.baca()

    def close(self):
        if self.kamera is not None:
            self.kamera.tutup()

    def detect(self, frame):                                # pragma: no cover
        raise NotImplementedError

# ------------------------------------------------------------------ backend yolo
class YoloDetector(DetektorKamera):
    """YOLO (v8/v11) ONNX lewat cv2.dnn. Butuh model hasil latih sendiri (2 kelas).

    Keluaran mentahnya tensor (1, 4+nc, N): 4 baris pertama cx,cy,w,h
    dalam piksel input, sisanya skor per kelas. Tidak perlu torch/ultralytics.
    """

    def __init__(self, kamera=None, path=None):
        super().__init__(kamera)
        if not ADA_CV:
            raise RuntimeError("opencv belum terpasang")
        path = path or C.YOLO_MODEL_PATH
        if not os.path.exists(path):
            raise RuntimeError(f"model YOLO tidak ada: {path}")
        self.net = cv2.dnn.readNetFromONNX(path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def detect(self, frame):
        if frame is None:
            return []
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (C.YOLO_IMGSZ, C.YOLO_IMGSZ),
                                     swapRB=True, crop=False)
        self.net.setInput(blob)
        keluar = self.net.forward()[0]                # (4+nc, N)
        keluar = keluar.T                             # (N, 4+nc)

        kotak, skor, kelas = [], [], []
        for baris in keluar:
            nilai = baris[4:]
            idx = int(nilai.argmax())
            s = float(nilai[idx])
            if s < C.CONF_MIN or idx >= len(C.YOLO_KELAS):
                continue
            cx, cy, bw, bh = (float(v) for v in baris[:4])
            kotak.append([cx - bw / 2, cy - bh / 2, bw, bh])
            skor.append(s)
            kelas.append(idx)
        if not kotak:
            return []

        simpan = cv2.dnn.NMSBoxes(kotak, skor, C.CONF_MIN, C.YOLO_NMS)
        hasil = []
        for i in np.array(simpan).flatten():
            x, y, bw, bh = kotak[int(i)]
            hasil.append(Deteksi(C.YOLO_KELAS[kelas[int(i)]],
                                 C.clamp(x / C.YOLO_IMGSZ, 0, 1),
                                 C.clamp(y / C.YOLO_IMGSZ, 0, 1),
                                 C.clamp(bw / C.YOLO_IMGSZ, 0, 1),
                                 C.clamp(bh / C.YOLO_IMGSZ, 0, 1),
                                 skor[int(i)]))
        return hasil


# ------------------------------------------------------------------ backend fake
class FakeDetector:
    """Gelas target muncul setelah jeda, lalu membesar seolah didekati."""

    def __init__(self, jeda_s=0.5, langkah=0.035):
        self.target = None
        self.jeda_s = jeda_s
        self.langkah = langkah
        self.t0 = None
        self.w = 0.10
        self.cx = 0.30
        self.cy = 0.5

    def set_target(self, label):
        if label != self.target:
            self.target = label
            self.t0 = None
            self.w = 0.10
            self.cx = 0.30

    def read(self):
        return object()                     # frame dummy, isinya tidak dipakai

    def detect(self, _frame):
        if self.target is None:
            return []
        if self.t0 is None:
            self.t0 = time.monotonic()
        if time.monotonic() - self.t0 < self.jeda_s:
            return []
        self.w = min(0.95, self.w + self.langkah)
        self.cx += (0.5 - self.cx) * 0.5    # makin ke tengah saat robot membelok
        return [Deteksi(self.target, self.cx, self.cy, self.w, self.w * 0.8, 0.90)]

    def close(self):
        pass


class AsyncDetector:
    """Jalankan deteksi mahal (YOLO) di thread terpisah.

    Loop kendali tetap berjalan 20 Hz: ``detect(frame)`` hanya menyerahkan frame
    terbaru ke thread pekerja, lalu langsung mengembalikan hasil terakhir — tidak
    pernah menunggu. Tanpa ini, YOLOv8n di Pi 3B+ menghentikan robot ~1,2 detik
    setiap kali memeriksa gambar, dan fase mencari menjadi tersendat.

    Hasil yang lebih tua dari ``batas_usang_s`` sengaja dibuang (dianggap target
    hilang) supaya robot tidak mengejar posisi gelas yang sudah tidak berlaku.
    """

    def __init__(self, dalam, jeda_s=None, batas_usang_s=None):
        self.dalam = dalam
        self.jeda_s = C.YOLO_ASYNC_JEDA_S if jeda_s is None else jeda_s
        self.batas_usang_s = C.ASYNC_BASI_S if batas_usang_s is None else batas_usang_s
        self._frame = None
        self._nomor = 0
        self._diproses = 0
        self._hasil = []
        self._waktu = 0.0
        self.generasi = 0
        self._kunci = threading.Lock()
        self._bangun = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._kerja, name="deteksi-async", daemon=True)
        self._thread.start()

    def read(self):
        return self.dalam.read()

    def detect(self, frame):
        if frame is not None:
            with self._kunci:
                self._frame = frame
                self._nomor += 1
            self._bangun.set()
        with self._kunci:
            if self._hasil and time.monotonic() - self._waktu > self.batas_usang_s:
                return []
            return list(self._hasil)

    def close(self):
        self._stop.set()
        self._bangun.set()
        self._thread.join(timeout=2.0)
        self.dalam.close()

    def _kerja(self):
        while not self._stop.is_set():
            if not self._bangun.wait(timeout=0.2):
                continue
            self._bangun.clear()
            with self._kunci:
                if self._frame is None or self._nomor == self._diproses:
                    continue
                frame, nomor = self._frame, self._nomor
            mulai = time.monotonic()
            try:
                hasil = self.dalam.detect(frame)
            except Exception:                    # jangan biarkan thread mati diam-diam
                hasil = []
            with self._kunci:
                self._diproses = nomor
                self._hasil = hasil
                self._waktu = time.monotonic()
                self.generasi += 1          # tanda: ada hasil deteksi baru
            sisa = self.jeda_s - (time.monotonic() - mulai)
            if sisa > 0:
                self._stop.wait(sisa)


class AlurDetector:
    """Geser kotak deteksi antar-inferensi dengan optical flow (Lucas-Kanade).

    YOLO 416 di Pi 3B+ butuh ~1,75 s per deteksi (angka terukur di proyek
    human-tracking-robot-v2), jadi kotak yang dibiarkan diam akan tertinggal jauh
    dari gelas begitu robot berbelok. Optical flow hanya ~5 ms/frame, sehingga
    kotak tetap menempel di gelas pada setiap frame kamera; YOLO dipakai untuk
    mengunci ulang posisi + label, bukan untuk setiap frame.

    Bila titik fitur habis (gelas tertutup, frame buram), kotak dilepas dan
    detektor mengembalikan daftar kosong — state machine akan menanganinya
    sebagai target hilang, bukan mengejar posisi palsu.
    """

    def __init__(self, dalam, aktif=True, titik_maks=40):
        self.dalam = dalam
        self.aktif = bool(aktif) and ADA_CV
        self.titik_maks = titik_maks
        self._abu = None
        self._titik = None
        self._kotak = None
        self._masuk = None

    @property
    def generasi(self):
        return getattr(self.dalam, "generasi", None)

    def read(self):
        return self.dalam.read()

    def close(self):
        self.dalam.close()

    def detect(self, frame):
        masuk = self.dalam.detect(frame)
        if not self.aktif or frame is None:
            return masuk
        if not ADA_CV:
            return masuk
        abu = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if masuk and masuk != self._masuk:                 # deteksi baru: kunci ulang
            self._masuk = masuk
            self._kotak = masuk[0]
            self._titik = self._benih(abu, self._kotak)
            self._abu = abu
            return masuk
        self._masuk = masuk
        if self._kotak is None or self._abu is None or self._titik is None:
            self._abu = abu
            return masuk
        baru, status, _ = cv2.calcOpticalFlowPyrLK(
            self._abu, abu, self._titik, None, winSize=(15, 15), maxLevel=2)
        self._abu = abu
        if baru is None or status is None:
            self._lepas()
            return []
        baik = status.reshape(-1) == 1
        if int(baik.sum()) < 4:
            self._lepas()
            return []
        geser = (baru[baik] - self._titik[baik]).reshape(-1, 2)
        dx, dy = float(np.median(geser[:, 0])), float(np.median(geser[:, 1]))
        tinggi, lebar = abu.shape[:2]
        k = self._kotak
        self._kotak = Deteksi(k.label,
                              C.clamp(k.cx + dx / lebar, 0, 1),
                              C.clamp(k.cy + dy / tinggi, 0, 1),
                              k.w, k.h, k.conf)
        self._titik = baru[baik].reshape(-1, 1, 2).astype("float32")
        if len(self._titik) < 8:                           # fitur menipis: isi ulang
            tambahan = self._benih(abu, self._kotak)
            if tambahan is not None:
                self._titik = tambahan
        return [self._kotak]

    def _lepas(self):
        self._kotak = None
        self._titik = None

    def _benih(self, abu, d):
        tinggi, lebar = abu.shape[:2]
        x0 = int(max(0, (d.cx - d.w / 2) * lebar))
        x1 = int(min(lebar - 1, (d.cx + d.w / 2) * lebar))
        y0 = int(max(0, (d.cy - d.h / 2) * tinggi))
        y1 = int(min(tinggi - 1, (d.cy + d.h / 2) * tinggi))
        if x1 - x0 < 10 or y1 - y0 < 10:
            return None
        roi = abu[y0:y1, x0:x1]
        titik = cv2.goodFeaturesToTrack(roi, maxCorners=self.titik_maks,
                                        qualityLevel=0.01, minDistance=4)
        if titik is None:
            return None
        titik = titik.reshape(-1, 2) + np.array([x0, y0], dtype="float32")
        return titik.reshape(-1, 1, 2).astype("float32")


# -------------------------------------------------------------------- pabrik
def make(backend=None, kamera=None):
    backend = backend or os.environ.get("VISION_BACKEND", C.VISION_BACKEND)
    if backend == "fake":
        return FakeDetector()
    if backend not in ("yolo", "fake"):
        raise ValueError(f"backend visi tidak dikenal: {backend}")
    if not ADA_CV:
        raise RuntimeError("opencv belum terpasang (sudo apt install python3-opencv)")
    # Periksa model DULU: di instalasi baru yang paling sering kurang adalah model,
    # bukan kamera. Pesan "kamera tidak bisa dibuka" hanya menyesatkan.
    if not os.path.exists(C.YOLO_MODEL_PATH):
        raise RuntimeError(
            f"model YOLO belum ada: {C.YOLO_MODEL_PATH}\n"
            "latih dulu di Roboflow/Colab lalu taruh berkas ONNX di models/")
    kamera = kamera if kamera is not None else Kamera()
    # YOLO selalu async: satu frame butuh ~1,2 s, loop kendali tidak boleh menunggu.
    return AlurDetector(AsyncDetector(YoloDetector(kamera)), aktif=C.YOLO_ALUR)


# --------------------------------------------------------------------- debug
def gambar_debug(frame, daftar):
    """Kotak + label untuk disimpan/dilihat saat menyetel."""
    if frame is None or not ADA_CV:
        return frame
    tinggi, lebar = frame.shape[:2]
    for d in daftar:
        x0 = int((d.cx - d.w / 2) * lebar)
        y0 = int((d.cy - d.h / 2) * tinggi)
        x1 = int((d.cx + d.w / 2) * lebar)
        y1 = int((d.cy + d.h / 2) * tinggi)
        warna = (0, 200, 0) if d.label == "teh" else (0, 140, 255)
        cv2.rectangle(frame, (x0, y0), (x1, y1), warna, 2)
        cv2.putText(frame, f"{d.label} {d.conf:.2f}", (x0, max(12, y0 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, warna, 1, cv2.LINE_AA)
    cv2.line(frame, (lebar // 2, 0), (lebar // 2, tinggi), (255, 255, 0), 1)
    return frame
