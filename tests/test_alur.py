"""Tes optical flow: kotak harus mengikuti gelas di antara dua deteksi YOLO."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

import vision


def kanvas(geser_x=0, geser_y=0, lebar=320, tinggi=240):
    """Latar bertekstur + kotak bercorak; digeser meniru gerakan relatif gelas."""
    img = np.full((tinggi, lebar, 3), 40, np.uint8)
    acak = np.random.RandomState(7).randint(60, 200, (60, 60, 3)).astype(np.uint8)
    cv2.rectangle(img, (100 + geser_x, 90 + geser_y), (160 + geser_x, 150 + geser_y), (200, 200, 200), -1)
    img[90 + geser_y:150 + geser_y, 100 + geser_x:160 + geser_x] = acak
    cv2.circle(img, (30, 30), 10, (0, 255, 0), -1)      # tekstur latar, bukan target
    return img


class DetSekali:
    """Meniru AsyncDetector: hasil sama terus sampai ada deteksi baru."""

    def __init__(self, kotak):
        self.kotak = kotak
        self.kunci = False

    def read(self):
        return object()

    def detect(self, _frame):
        if self.kunci:
            return self.kotak
        self.kunci = True
        return self.kotak

    def close(self):
        pass


class TesAlur(unittest.TestCase):
    def setUp(self):
        self.det_masuk = [vision.Deteksi("kopi", 130 / 320, 120 / 240, 60 / 320, 60 / 240, 0.9)]

    def test_kotak_mengikuti_gerakan(self):
        alur = vision.AlurDetector(DetSekali(self.det_masuk), aktif=True)
        alur.detect(kanvas(0, 0))                       # deteksi pertama: kunci
        hasil = alur.detect(kanvas(12, 8))              # gelas bergeser 12 px kanan
        self.assertEqual(len(hasil), 1)
        self.assertAlmostEqual(hasil[0].cx, 130 / 320 + 12 / 320, places=3)
        self.assertAlmostEqual(hasil[0].cy, 120 / 240 + 8 / 240, places=3)
        hasil = alur.detect(kanvas(24, 16))             # bergeser lagi
        self.assertAlmostEqual(hasil[0].cx, 130 / 320 + 24 / 320, places=3)
        self.assertEqual(hasil[0].label, "kopi")         # label dipertahankan
        alur.close()

    def test_kotak_dilepas_saat_frame_kehilangan_tekstur(self):
        alur = vision.AlurDetector(DetSekali(self.det_masuk), aktif=True)
        alur.detect(kanvas(0, 0))
        kosong = np.full((240, 320, 3), 128, np.uint8)   # kamera tertutup total
        self.assertEqual(alur.detect(kosong), [],
                         "tanpa tekstur, kotak harus dilepas bukan dikarang")
        alur.close()

    def test_deteksi_baru_menimpa_kotak_lama(self):
        alur = vision.AlurDetector(DetSekali(self.det_masuk), aktif=True)
        alur.detect(kanvas(0, 0))
        baru = [vision.Deteksi("teh", 0.80, 0.20, 0.10, 0.10, 0.8)]
        alur.dalam.kotak = baru
        hasil = alur.detect(kanvas(0, 0))
        self.assertEqual(hasil[0].label, "teh")
        self.assertAlmostEqual(hasil[0].cx, 0.80)
        alur.close()

    def test_alur_bisa_dimatikan(self):
        alur = vision.AlurDetector(DetSekali(self.det_masuk), aktif=False)
        alur.detect(kanvas(0, 0))
        hasil = alur.detect(kanvas(12, 8))
        self.assertAlmostEqual(hasil[0].cx, 130 / 320)   # tidak digeser
        alur.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
