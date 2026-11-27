"""Visi: mengubah frame kamera menjadi daftar kandidat target.

Setiap deteksi: (label, cx, cy, w, h, conf) dengan semua nilai ternormalisasi 0..1
terhadap ukuran frame. ``w`` dipakai sebagai ukuran jarak: makin lebar kotak,
makin dekat gelasnya.

Backend yang tersedia (pilih di config.VISION_BACKEND atau --vision):
  penanda : HSV blob pada penanda warna gelas (tutup/stiker/gelas berwarna)
  bentuk  : siluet gelas, dibedakan dari rasio tinggi/lebar
  yolo    : model 2 kelas ONNX lewat cv2.dnn, dijalankan di thread terpisah
            (tanpa torch; wajib async karena satu frame butuh ~1,2 s di Pi 3B+)
  yolo-sync : sama, tapi deteksi menahan loop — hanya untuk mengukur/menyetel
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


def _kecilkan(frame):
    """Perkecil ke resolusi pemrosesan. Kembalikan (frame_kecil, faktor_w, faktor_h)."""
    tinggi, lebar = frame.shape[:2]
    if (lebar, tinggi) == (C.PROC_W, C.PROC_H):
        return frame, 1.0, 1.0
    return (cv2.resize(frame, (C.PROC_W, C.PROC_H), interpolation=cv2.INTER_AREA),
            C.PROC_W / lebar, C.PROC_H / tinggi)


def _mask(hsv, rentang):
    hasil = None
    for lo, hi in rentang:
        m = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        hasil = m if hasil is None else cv2.bitwise_or(hasil, m)
    return hasil


def _rapikan(mask):
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)     # buang bintik
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)    # tutup lubang
    return mask


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


# -------------------------------------------------------------- backend penanda
class MarkerDetector(DetektorKamera):
    """Cari blob penanda warna. Label ditentukan oleh rentang HSV-nya."""

    def detect(self, frame):
        if frame is None:
            return []
        kecil, _, _ = _kecilkan(frame)
        hsv = cv2.cvtColor(kecil, cv2.COLOR_BGR2HSV)
        hsv = cv2.GaussianBlur(hsv, (5, 5), 0)
        luas_proc = float(C.PROC_W * C.PROC_H)

        hasil = []
        for label, rentang in C.WARNA.items():
            mask = _rapikan(_mask(hsv, rentang))
            kontur = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                      cv2.CHAIN_APPROX_SIMPLE)[-2]
            if not kontur:
                continue
            terbaik = max(kontur, key=cv2.contourArea)
            luas = cv2.contourArea(terbaik)
            if luas < C.LUAS_MIN_PIKSEL:
                continue
            x, y, bw, bh = cv2.boundingRect(terbaik)
            if bw < 8 or bh < 8:
                continue
            padat = luas / float(bw * bh)
            if padat < 0.55:            # bentuk acak (bayangan, pantulan)
                continue
            porsi = luas / luas_proc
            conf = C.clamp(0.35 + 0.65 * porsi / 0.05, 0.0, 1.0) * padat
            hasil.append(Deteksi(label,
                                 (x + bw / 2) / C.PROC_W,
                                 (y + bh / 2) / C.PROC_H,
                                 bw / C.PROC_W,
                                 bh / C.PROC_H,
                                 conf))
        return hasil


# ---------------------------------------------------------------- backend bentuk
class ShapeDetector(DetektorKamera):
    """Deteksi siluet gelas terang, lalu klasifikasi dari rasio tinggi/lebar."""

    def detect(self, frame):
        if frame is None:
            return []
        kecil, _, _ = _kecilkan(frame)
        hsv = cv2.cvtColor(kecil, cv2.COLOR_BGR2HSV)
        hsv = cv2.GaussianBlur(hsv, (9, 9), 0)
        mask = _rapikan(_mask(hsv, C.WARNA_GELAS))
        kontur = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                  cv2.CHAIN_APPROX_SIMPLE)[-2]

        hasil = []
        for kontur_satu in kontur:
            luas = cv2.contourArea(kontur_satu)
            if luas < C.LUAS_MIN_PIKSEL * 4:       # gelas utuh, bukan bintik
                continue
            x, y, bw, bh = cv2.boundingRect(kontur_satu)
            if bw < 10 or bh < 10:
                continue
            rasio = bh / float(bw)
            label, keyakinan = _label_dari_rasio(rasio)
            if label is None:
                continue
            porsi = luas / float(C.PROC_W * C.PROC_H)
            conf = C.clamp(keyakinan * (0.4 + porsi / 0.08), 0.0, 1.0)
            hasil.append(Deteksi(label,
                                 (x + bw / 2) / C.PROC_W,
                                 (y + bh / 2) / C.PROC_H,
                                 bw / C.PROC_W,
                                 bh / C.PROC_H,
                                 conf))
        return hasil


def _label_dari_rasio(rasio):
    """Kembalikan (label, keyakinan 0..1) atau (None, 0)."""
    for label, (lo, hi) in C.BENTUK.items():
        if lo <= rasio <= hi:
            tengah = 0.5 * (lo + hi)
            lebar = max(1e-6, 0.5 * (hi - lo))
            keyakinan = 1.0 - min(1.0, abs(rasio - tengah) / lebar) * 0.5
            return label, keyakinan
    return None, 0.0


# ------------------------------------------------------------------ backend yolo
class YoloDetector(DetektorKamera):
    """YOLOv8 ONNX lewat cv2.dnn. Butuh model hasil latih sendiri (2 kelas).

    Keluaran YOLOv8 adalah tensor (1, 4+nc, 8400): 4 baris pertama cx,cy,w,h
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
            sisa = self.jeda_s - (time.monotonic() - mulai)
            if sisa > 0:
                self._stop.wait(sisa)


# -------------------------------------------------------------------- pabrik
def make(backend=None, kamera=None):
    backend = backend or os.environ.get("VISION_BACKEND", C.VISION_BACKEND)
    if backend == "fake":
        return FakeDetector()
    if backend not in ("yolo", "yolo-sync", "bentuk", "penanda"):
        raise ValueError(f"backend visi tidak dikenal: {backend}")
    if not ADA_CV:
        raise RuntimeError("opencv belum terpasang (sudo apt install python3-opencv)")
    kamera = kamera if kamera is not None else Kamera()
    if backend == "yolo-sync":
        return YoloDetector(kamera)
    if backend == "yolo":
        det = YoloDetector(kamera)
        return AsyncDetector(det) if C.YOLO_ASYNC else det
    if backend == "bentuk":
        return ShapeDetector(kamera)
    return MarkerDetector(kamera)


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
