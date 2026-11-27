"""Tes bagian visi yang tidak butuh model ONNX.

Jalur identifikasi tunggal = YOLO. Modelnya diuji terpisah dengan foto nyata
(lihat README), jadi di sini yang diuji adalah logika di sekelilingnya:
pemilihan target, pabrik detektor, dan bukti bahwa jalur HSV sudah tidak ada.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
import vision

AKAR = Path(__file__).resolve().parents[1]


class TesPilihTarget(unittest.TestCase):
    def test_conf_di_bawah_ambang_ditolak(self):
        det = vision.Deteksi("kopi", 0.5, 0.5, 0.1, 0.1, C.CONF_MIN - 0.01)
        self.assertIsNone(vision.pilih_target([det], "kopi"))

    def test_label_lain_tidak_terpilih(self):
        det = vision.Deteksi("teh", 0.5, 0.5, 0.4, 0.3, 0.99)
        self.assertIsNone(vision.pilih_target([det], "kopi"))

    def test_memilih_kotak_terbesar_walau_dua_kandidat(self):
        jauh = vision.Deteksi("kopi", 0.2, 0.5, 0.04, 0.05, 0.60)
        dekat = vision.Deteksi("kopi", 0.7, 0.5, 0.22, 0.26, 0.55)
        self.assertIs(vision.pilih_target([jauh, dekat], "kopi"), dekat)


class TesFake(unittest.TestCase):
    def test_fake_tidak_butuh_model(self):
        det = vision.make("fake")
        self.assertIsInstance(det, vision.FakeDetector)
        det.jeda_s = 0                        # jangan tunggu setengah detik
        det.set_target("teh")
        self.assertTrue(det.detect(None))

    def test_backend_tidak_dikenal(self):
        with self.assertRaises(ValueError):
            vision.make("tidak-ada")


class TesSatuJalur(unittest.TestCase):
    """Kalau jalur HSV dihidupkan lagi, tes ini gagal."""

    def test_detektor_hsv_sudah_dihapus(self):
        for nama in ("MarkerDetector", "ShapeDetector", "_mask", "_label_dari_rasio"):
            self.assertFalse(hasattr(vision, nama), nama)

    def test_tidak_ada_ambang_warna_di_config(self):
        for nama in ("WARNA", "WARNA_GELAS", "BENTUK", "LUAS_MIN_PIKSEL"):
            self.assertFalse(hasattr(C, nama), nama)

    def test_alat_kalibrasi_hsv_sudah_dihapus(self):
        self.assertFalse((AKAR / "kalibrasi.py").exists())

    def test_tidak_ada_jalur_kedua(self):
        # satu jalur saja: tidak ada backend sinkron
        kode = (AKAR / "vision.py").read_text() + (AKAR / "hardware.py").read_text()
        self.assertNotIn("yolo-sync", kode)
        self.assertFalse((AKAR / "tangkap.py").exists(),
                         "dataset diambil di laptop; repo tidak perlu alat tangkap")

    def test_backend_default_yolo(self):
        self.assertEqual(C.VISION_BACKEND, "yolo")
        self.assertEqual(C.YOLO_KELAS, ["kopi", "teh"])


if __name__ == "__main__":
    unittest.main()
