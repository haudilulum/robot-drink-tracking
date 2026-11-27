"""Tes kewarasan konfigurasi: pin bentrok, ambang terbalik, rentang HSV salah.

Kesalahan di sini paling mahal: pin bentrok baru ketahuan setelah kabel disolder,
ambang terbalik membuat robot never berhenti atau langsung berhenti.
"""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C


def semua_pin():
    return {
        "motor kiri maju": C.PIN_MOTOR_KIRI_MAJU,
        "motor kiri mundur": C.PIN_MOTOR_KIRI_MUNDUR,
        "motor kanan maju": C.PIN_MOTOR_KANAN_MAJU,
        "motor kanan mundur": C.PIN_MOTOR_KANAN_MUNDUR,
        "pb kopi": C.PIN_PB_KOPI,
        "pb teh": C.PIN_PB_TEH,
        "led": C.PIN_LED,
        "buzzer": C.PIN_BUZZER,
        "servo pan": C.PIN_SERVO_PAN,
    }


class TesPin(unittest.TestCase):
    def test_tidak_ada_pin_dipakai_dua_kali(self):
        hitung = Counter(semua_pin().values())
        bentrok = {pin: n for pin, n in hitung.items() if n > 1}
        self.assertEqual(bentrok, {}, f"pin bentrok: {bentrok}")

    def test_pin_dalam_rentang_bcm_yang_ada(self):
        for nama, pin in semua_pin().items():
            self.assertTrue(0 <= pin <= 27, f"{nama} di GPIO{pin} tidak ada di header")

    def test_pin_i2c_dan_uart_tidak_dipakai(self):
        # 0/1 = ID_SD/ID_SC (EEPROM), 14/15 = UART serial konsol
        terpakai = set(semua_pin().values())
        self.assertFalse(terpakai & {0, 1, 14, 15}, "jangan pakai pin khusus ini")


class TesAmbang(unittest.TestCase):
    def test_kecepatan_berurutan(self):
        self.assertGreater(C.SPEED_MIN, 0)
        self.assertLess(C.SPEED_MIN, C.SPEED_MAJU)
        self.assertLessEqual(C.SPEED_MAJU, 1.0)
        self.assertLessEqual(C.SPEED_PUTAR, 1.0)

    def test_ambang_jarak_berurutan(self):
        self.assertLess(C.W_MULAI_PELAN, C.W_BERHENTI)
        self.assertLessEqual(C.W_BERHENTI, 1.0)

    def test_waktu_positif(self):
        for nama in ("TIMEOUT_CARI_S", "TIMEOUT_DEKATI_S", "GRACE_HILANG_S",
                     "JEDA_PERIKSA_S", "MIN_PUTAR_S", "PAUSE_SAMPAI_S"):
            self.assertGreater(getattr(C, nama), 0, nama)

    def test_satu_putaran_penuh(self):
        self.assertAlmostEqual(C.LANGKAH_PER_ARAH * C.SUDUT_LANGKAH, 360)


class TesJalurVisi(unittest.TestCase):
    def test_backend_dikenal(self):
        self.assertIn(C.VISION_BACKEND, {"yolo", "yolo-sync", "fake"})

    def test_dua_kelas_sesuai_urutan_training(self):
        self.assertEqual(C.YOLO_KELAS, ["kopi", "teh"])

    def test_input_model_masuk_akal(self):
        self.assertIn(C.YOLO_IMGSZ, (320, 416, 640))
        self.assertLessEqual(C.YOLO_IMGSZ, 640)

    def test_ambang_keyakinan_wajar(self):
        self.assertGreater(C.CONF_MIN, 0.0)
        self.assertLess(C.CONF_MIN, 1.0)
        self.assertGreater(C.YOLO_NMS, 0.0)
        self.assertLess(C.YOLO_NMS, 1.0)

    def test_async_wajib_untuk_pi_3b(self):
        self.assertTrue(C.YOLO_ASYNC, "deteksi >1 s/frame tidak boleh menahan loop")
        self.assertGreater(C.ASYNC_BASI_S, 0)


if __name__ == "__main__":
    unittest.main()
