"""Uji integrasi: dunia sintetis closed-loop -> Robot (tanpa HSV, tanpa model).

Gelas bergeser ke tengah saat robot berbelok dan membesar saat robot maju.
Detektornya menggantikan model YOLO: ia membaca keadaan dunia langsung, jadi
yang teruji adalah loop kendali — bukan akurasi model.
"""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

import config as C
import hardware as hw_mod
import vision
from main import Robot


def bgr(h, s=200, v=150):
    return tuple(int(x) for x in cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0, 0])


class Dunia:
    """cx 0..1 posisi gelas di frame, u = ukuran gelas dalam piksel."""

    def __init__(self, h=12, cx=0.80, u=100):
        self.h, self.cx, self.u = h, cx, u

    def frame(self, kiri, kanan):
        # berbelok menggeser gelas ke arah tengah; maju mendekatkan
        self.cx += (0.5 - self.cx) * 0.25 + (kanan - kiri) * 0.12
        self.cx = float(np.clip(self.cx, 0.05, 0.95))
        if (kiri + kanan) > 0:
            self.u = min(420.0, self.u + 6.0 * (kiri + kanan))
        img = np.full((C.FRAME_H, C.FRAME_W, 3), bgr(0, 0, 30), np.uint8)
        x = int(self.cx * C.FRAME_W - self.u / 2)
        y = int(240 - self.u / 2)
        cv2.rectangle(img, (x, y), (x + int(self.u), y + int(self.u)), bgr(self.h), -1)
        return img


class DetektorDunia:
    """Pengganti model YOLO: kotak diambil dari keadaan dunia, bukan dari piksel."""

    def __init__(self, dunia, hw, label="kopi"):
        self.dunia, self.hw, self.label = dunia, hw, label
        self.generasi = 0

    def read(self):
        kiri, kanan = self.hw.drive_terakhir
        self.dunia.frame(kiri, kanan)      # gelas bergeser sesuai gerak robot
        return self.dunia

    def detect(self, dunia):
        self.generasi += 1                 # tiap panggilan = deteksi baru
        u = dunia.u / C.FRAME_W
        return [vision.Deteksi(self.label, dunia.cx, 0.5, u, u, 0.90)]

    def close(self):
        pass


class Jam:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def maju(self, dt):
        self.t += dt


def jalankan(label, cx_awal, hue=12):
    dunia = Dunia(h=hue, cx=cx_awal)
    hw = hw_mod.FakeHardware()
    det = DetektorDunia(dunia, hw, label=label)
    jam = Jam()
    r = Robot(hw=hw, det=det, verbose=False, jam=jam, tidur=lambda _s: None)

    hw.tekan(label)
    jejak = []
    for i in range(400):
        r.step(det.read())
        jejak.append((i, r.state, hw.drive_terakhir, round(dunia.cx, 2), round(dunia.u)))
        jam.maju(0.05)
        if r.state == "IDLE" and i > 10:
            break

    masalah = []
    if ("stop",) not in hw.aksi:
        masalah.append("motor tidak pernah dihentikan")
    if r.state != "IDLE":
        masalah.append(f"state akhir {r.state}")
    if hw.drive_terakhir != (0.0, 0.0):
        masalah.append("motor tidak berhenti")
    if abs(dunia.cx - 0.5) > 0.15:
        masalah.append(f"berhenti saat gelas tidak di tengah (cx={dunia.cx:.2f})")

    arah_awal = "kanan" if cx_awal > 0.5 else "kiri"
    belok = [d for _, st, d, _, _ in jejak if st == "DEKATI"]
    if arah_awal == "kanan" and not any(d[0] > d[1] for d in belok):
        masalah.append("tidak berbelok kanan")
    if arah_awal == "kiri" and not any(d[1] > d[0] for d in belok):
        masalah.append("tidak berbelok kiri")

    print(f"{label}: langkah={len(jejak)} cx_akhir={dunia.cx:.2f} "
          f"-> {'LULUS' if not masalah else 'GAGAL: ' + '; '.join(masalah)}")
    return not masalah


ok = True
ok &= jalankan("kopi", 0.80)     # gelas di kanan
ok &= jalankan("teh", 0.15, hue=55)   # gelas hijau di kiri
sys.exit(0 if ok else 1)
