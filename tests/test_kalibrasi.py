"""Tes alat kalibrasi HSV (tanpa kamera)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

import kalibrasi as K


class TesRataSirkular(unittest.TestCase):
    def test_klaster_biasa(self):
        self.assertAlmostEqual(K.rata_sirkular_hue([10, 11, 12]), 11, delta=0.5)

    def test_klaster_melewati_batas_179(self):
        # 176..179 dan 0..4 sebenarnya berdekatan (merah)
        nilai = [2.0, 178.0, 1.0, 179.0]
        rata = K.rata_sirkular_hue(nilai)
        jarak = min(abs(rata), abs(rata - 180))
        self.assertLess(jarak, 4.0)

    def test_semua_nilai_sama(self):
        self.assertAlmostEqual(K.rata_sirkular_hue([90] * 5), 90, delta=0.01)


class TesRentangHue(unittest.TestCase):
    def test_satu_rentang_untuk_warna_jauh_dari_batas(self):
        hasil = K.rentang_hue_circular(np.array([50, 52, 48, 51]))
        self.assertEqual(len(hasil), 1)
        lo, hi = hasil[0]
        self.assertLessEqual(lo, 50)
        self.assertGreaterEqual(hi, 52)

    def test_dua_rentang_untuk_merah(self):
        hasil = K.rentang_hue_circular(np.array([1, 2, 178, 179, 0]))
        self.assertEqual(len(hasil), 2)
        gabungan = [(lo, hi) for lo, hi in hasil]
        self.assertTrue(any(lo == 0 for lo, _ in gabungan))
        self.assertTrue(any(hi == 179 for _, hi in gabungan))

    def test_rentang_selalu_valid(self):
        for data in ([0, 1, 2], [88, 90, 92], [179, 0, 1, 90]):
            for lo, hi in K.rentang_hue_circular(np.array(data)):
                self.assertTrue(0 <= lo <= 179)
                self.assertTrue(0 <= hi <= 179)


class TesSaran(unittest.TestCase):
    def test_saran_menghasilkan_rentang_dalam_batas(self):
        px = np.tile(np.array([[12, 200, 150]], np.int32), (100, 1))
        daftar = K.saran(px, "kopi")
        self.assertTrue(daftar)
        for lo, hi in daftar:
            self.assertTrue(0 <= lo[0] <= 179)
            self.assertTrue(0 <= lo[1] <= hi[1] <= 255)
            self.assertTrue(0 <= lo[2] <= hi[2] <= 255)


class TesRegion(unittest.TestCase):
    def test_potong_region_mengembalikan_hsv_yang_benar(self):
        hsv = np.uint8([[[12, 200, 150]]])
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0]
        img = np.full((100, 100, 3), bgr, np.uint8)
        px = K.hsv_region(img, 10, 10, 20, 20)
        self.assertEqual(px.shape, (400, 3))
        self.assertAlmostEqual(float(np.median(px[:, 0])), 12, delta=1)

    def test_kotak_di_luar_gambar_dipotong(self):
        img = np.full((50, 50, 3), 120, np.uint8)
        px = K.hsv_region(img, 40, 40, 100, 100)
        self.assertEqual(px.shape[0], 10 * 10)

    def test_kotak_sepenuhnya_di_luar_gagal_cepat(self):
        img = np.full((50, 50, 3), 120, np.uint8)
        with self.assertRaises(SystemExit):
            K.hsv_region(img, 200, 200, 10, 10)


class TesGumpalan(unittest.TestCase):
    def test_menemukan_gumpalan_berwarna(self):
        img = np.full((240, 320, 3), 40, np.uint8)
        cv2.rectangle(img, (20, 20), (80, 80), (30, 60, 200), -1)
        kotak = K.gumpalan_teratas(img)
        self.assertTrue(kotak)
        luas, x, y, w, h = kotak[0]
        self.assertGreater(luas, 1000)
        self.assertLess(abs(x - 20), 10)
        self.assertLess(abs(y - 20), 10)


if __name__ == "__main__":
    unittest.main()
