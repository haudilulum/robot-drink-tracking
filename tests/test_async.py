"""Tes detektor async: deteksi mahal tidak boleh menahan loop kendali."""

import sys
import time
import unittest
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import vision


class DetLambat:
    """Detektor yang sengaja lambat, meniru YOLOv8n di Pi 3B+ (~1,2 s/frame)."""

    def __init__(self, tunda_s=0.20):
        self.tunda_s = tunda_s
        self.panggilan = 0
        self.ditutup = False

    def read(self):
        return object()

    def detect(self, _frame):
        self.panggilan += 1
        time.sleep(self.tunda_s)
        return [vision.Deteksi("kopi", 0.5, 0.5, 0.3, 0.25, 0.9)]

    def close(self):
        self.ditutup = True


class TesAsync(unittest.TestCase):
    def test_detect_tidak_menahan_loop(self):
        lambat = DetLambat(0.20)
        det = vision.AsyncDetector(lambat, jeda_s=0.0)
        try:
            t = time.perf_counter()
            for _ in range(20):
                det.detect(object())
                time.sleep(0.05)          # meniru loop 20 Hz
            total = time.perf_counter() - t
            self.assertLess(total, 1.2, "loop utama tertahan oleh deteksi")
        finally:
            det.close()

    def test_hasil_muncul_setelah_beberapa_saat(self):
        det = vision.AsyncDetector(DetLambat(0.05), jeda_s=0.0, batas_usang_s=5.0)
        try:
            for _ in range(30):
                hasil = det.detect(object())
                if hasil:
                    break
                time.sleep(0.05)
            self.assertEqual(len(hasil), 1)
            self.assertAlmostEqual(hasil[0].cx, 0.5)
        finally:
            det.close()

    def test_hasil_basi_dibuang(self):
        det = vision.AsyncDetector(DetLambat(0.01), jeda_s=0.0, batas_usang_s=0.10)
        try:
            for _ in range(20):
                det.detect(object())
                time.sleep(0.01)
            time.sleep(0.25)              # hasil sekarang lebih tua dari batas
            self.assertEqual(det.detect(object()), [],
                             "hasil basi harus dianggap target hilang")
        finally:
            det.close()

    def test_close_menutup_detektor_dalam(self):
        lambat = DetLambat(0.01)
        det = vision.AsyncDetector(lambat, jeda_s=0.0)
        det.close()
        self.assertFalse(det._thread.is_alive())
        self.assertTrue(lambat.ditutup)

    def test_yolo_memakai_async(self):
        import inspect
        kode = inspect.getsource(vision.make)
        self.assertIn("AsyncDetector", kode)
        self.assertNotIn("YOLO_ASYNC", kode, "tidak ada jalan sinkron: YOLO selalu async")


if __name__ == "__main__":
    unittest.main(verbosity=2)
