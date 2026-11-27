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

    def test_luas_minimum_masuk_akal(self):
        self.assertLess(C.LUAS_MIN_PIKSEL, C.PROC_W * C.PROC_H * 0.1)

    def test_waktu_positif(self):
        for nama in ("TIMEOUT_CARI_S", "TIMEOUT_DEKATI_S", "GRACE_HILANG_S",
                     "JEDA_PERIKSA_S", "MIN_PUTAR_S", "PAUSE_SAMPAI_S"):
            self.assertGreater(getattr(C, nama), 0, nama)

    def test_satu_putaran_penuh(self):
        self.assertAlmostEqual(C.LANGKAH_PER_ARAH * C.SUDUT_LANGKAH, 360)


class TesRentangHSV(unittest.TestCase):
    def test_rentang_penanda_valid(self):
        for label, daftar in C.WARNA.items():
            self.assertTrue(daftar, f"{label} tidak punya rentang")
            for lo, hi in daftar:
                self.assertLessEqual(0, lo[0]); self.assertLessEqual(hi[0], 179)
                self.assertLessEqual(lo[0], hi[0], f"hue {label} terbalik")
                for i, nama in ((1, "S"), (2, "V")):
                    self.assertLessEqual(0, lo[i])
                    self.assertLessEqual(lo[i], hi[i], f"{nama} {label} terbalik")
                    self.assertLessEqual(hi[i], 255)

    def test_warna_gelas_valid(self):
        for lo, hi in C.WARNA_GELAS:
            self.assertLessEqual(lo[0], hi[0])
            self.assertLessEqual(lo[1], hi[1])

    def test_rentang_kopi_dan_teh_tidak_tumpang_tindih(self):
        def himpunan(daftar):
            return {h for lo, hi in daftar for h in range(lo[0], hi[0] + 1)}
        irisan = himpunan(C.WARNA["kopi"]) & himpunan(C.WARNA["teh"])
        self.assertEqual(irisan, set(), f"hue tumpang tindih: {sorted(irisan)}")

    def test_rentang_bentuk_berurutan_dan_tidak_tumpang(self):
        kopi = C.BENTUK["kopi"]
        teh = C.BENTUK["teh"]
        self.assertLess(kopi[0], kopi[1])
        self.assertLess(teh[0], teh[1])
        self.assertLess(kopi[1], teh[0], "rentang mug dan gelas tinggi beririsan")


class TesBackend(unittest.TestCase):
    def test_backend_dikenal(self):
        self.assertIn(C.VISION_BACKEND, {"penanda", "bentuk", "yolo", "fake"})

    def test_kelas_yolo_cocok_dengan_label(self):
        self.assertEqual(set(C.YOLO_KELAS), set(C.WARNA))


if __name__ == "__main__":
    unittest.main()
