"""Tes backend visi dengan gambar sintetis (tanpa kamera)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

import config as C
import vision


def warna_bgr(h, s, v):
    """BGR dari HSV yang dijamin masuk rentang tertentu."""
    hsv = np.uint8([[[h, s, v]]])
    return tuple(int(x) for x in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])


def kanvas(v_bg=35):
    return np.full((C.FRAME_H, C.FRAME_W, 3), warna_bgr(0, 0, v_bg), np.uint8)


def tempel(img, hsv_warna, x, y, w, h):
    img[y:y + h, x:x + w] = warna_bgr(*hsv_warna)
    return img


class TesPenanda(unittest.TestCase):
    def setUp(self):
        self.det = vision.MarkerDetector(kamera=None)

    def test_kopi_terdeteksi_dengan_pusat_benar(self):
        img = tempel(kanvas(), (12, 200, 150), 280, 200, 80, 80)   # coklat-oranye
        hasil = self.det.detect(img)
        label = [d.label for d in hasil]
        self.assertIn("kopi", label)
        kopi = vision.pilih_target(hasil, "kopi")
        self.assertIsNotNone(kopi)
        self.assertAlmostEqual(kopi.cx, 0.5, delta=0.03)
        self.assertGreater(kopi.w, 0.05)

    def test_teh_terdeteksi_tanpa_tertukar(self):
        img = tempel(kanvas(), (55, 180, 140), 280, 200, 80, 80)   # hijau
        hasil = self.det.detect(img)
        self.assertIn("teh", [d.label for d in hasil])
        self.assertNotIn("kopi", [d.label for d in hasil])

    def test_bintik_kecil_diabaikan(self):
        img = tempel(kanvas(), (12, 200, 150), 300, 220, 20, 20)
        self.assertEqual(self.det.detect(img), [])

    def test_frame_kosong_aman(self):
        self.assertEqual(self.det.detect(kanvas()), [])
        self.assertEqual(self.det.detect(None), [])

    def test_pilih_target_memilih_yang_paling_dekat(self):
        img = tempel(kanvas(), (12, 200, 150), 60, 220, 40, 40)
        tempel(img, (12, 200, 150), 280, 160, 160, 160)
        hasil = self.det.detect(img)
        self.assertEqual(len([d for d in hasil if d.label == "kopi"]), 1)
        terpilih = vision.pilih_target(hasil, "kopi")
        self.assertGreater(terpilih.w, 0.2)          # yang besar, bukan yang kecil

    def test_conf_di_bawah_ambang_ditolak(self):
        det = vision.Deteksi("kopi", 0.5, 0.5, 0.1, 0.1, C.CONF_MIN - 0.01)
        self.assertIsNone(vision.pilih_target([det], "kopi"))

    def test_label_lain_tidak_terpilih(self):
        det = vision.Deteksi("teh", 0.5, 0.5, 0.4, 0.3, 0.99)
        self.assertIsNone(vision.pilih_target([det], "kopi"))


class TesBentuk(unittest.TestCase):
    def setUp(self):
        self.det = vision.ShapeDetector(kamera=None)

    def _gelas(self, w, h):
        img = kanvas(30)
        tempel(img, (0, 0, 220), 320 - w // 2, 240 - h // 2, w, h)   # putih terang
        return self.det.detect(img)

    def test_gelas_tinggi_dianggap_teh(self):
        hasil = self._gelas(120, 240)
        self.assertIn("teh", [d.label for d in hasil], hasil)

    def test_mug_lebar_dianggap_kopi(self):
        hasil = self._gelas(170, 150)
        self.assertIn("kopi", [d.label for d in hasil], hasil)

    def test_benda_kecil_diabaikan(self):
        self.assertEqual(self._gelas(30, 40), [])


class TesRasio(unittest.TestCase):
    def test_rasio_di_luar_rentang_tidak_diberi_label(self):
        label, yakin = vision._label_dari_rasio(0.30)     # sangat lebar
        self.assertIsNone(label)
        self.assertEqual(yakin, 0.0)

    def test_rasio_di_tengah_rentang_paling_yakin(self):
        lo, hi = C.BENTUK["teh"]
        tengah = 0.5 * (lo + hi)
        _, yakin_tengah = vision._label_dari_rasio(tengah)
        _, yakin_tepi = vision._label_dari_rasio(hi - 1e-6)
        self.assertGreater(yakin_tengah, yakin_tepi)


class TesKameraFake(unittest.TestCase):
    def test_fake_tidak_butuh_opencv(self):
        det = vision.make("fake")
        self.assertIsInstance(det, vision.FakeDetector)
        det.jeda_s = 0                        # jangan tunggu setengah detik
        det.set_target("teh")
        self.assertTrue(det.detect(None))

    def test_backend_tidak_dikenal(self):
        with self.assertRaises(ValueError):
            vision.make("tidak-ada")


if __name__ == "__main__":
    unittest.main()
