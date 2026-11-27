"""Tes state machine tanpa Raspberry Pi dan tanpa kamera.

Jalankan: python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
import hardware as hw_mod
import vision
from main import Robot


class Jam:
    """Jam palsu: waktu hanya maju saat tes memintanya."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def maju(self, dt):
        self.t += dt


class DetUji:
    """Detektor yang daftar deteksinya bisa diubah kapan saja."""

    def __init__(self, daftar=()):
        self.daftar = list(daftar)
        self.target = None
        self.read_count = 0

    def set_target(self, target):
        self.target = target

    def read(self):
        self.read_count += 1
        return object()

    def detect(self, _frame):
        return list(self.daftar)

    def close(self):
        pass


def kotak(label="kopi", cx=0.5, w=0.2, conf=0.9):
    return vision.Deteksi(label, cx, 0.5, w, w * 0.8, conf)


def robot_uji(det=None):
    hw = hw_mod.FakeHardware()
    jam = Jam()
    r = Robot(hw=hw, det=det or DetUji(), verbose=False, jam=jam,
              tidur=lambda _s: None)
    return r, hw, jam


def jalankan(r, jam, langkah, dt=0.05):
    for _ in range(langkah):
        r.step(None)
        jam.maju(dt)


class TesMulai(unittest.TestCase):
    def test_pb_kopi_masuk_cari(self):
        r, hw, jam = robot_uji()
        hw.tekan("kopi")
        r.step(None)
        self.assertEqual(r.state, "CARI")
        self.assertEqual(r.target, "kopi")

    def test_pb_teh_memilih_target_teh(self):
        r, hw, _ = robot_uji()
        hw.tekan("teh")
        r.step(None)
        self.assertEqual(r.target, "teh")

    def test_tombol_sama_saat_jalan_menghentikan(self):
        r, hw, jam = robot_uji(DetUji([kotak(w=0.2)]))
        hw.tekan("kopi")
        r.step(None)
        jalankan(r, jam, 3)
        self.assertEqual(r.state, "DEKATI")
        hw.tekan("kopi")
        r.step(None)
        self.assertEqual(r.state, "IDLE")
        self.assertEqual(hw.drive_terakhir, (0.0, 0.0))
        self.assertIn(("stop",), hw.aksi)

    def test_tombol_lain_mengganti_target(self):
        r, hw, jam = robot_uji(DetUji([kotak("kopi", w=0.2)]))
        hw.tekan("kopi")
        r.step(None)
        jalankan(r, jam, 3)
        hw.tekan("teh")
        r.step(None)
        self.assertEqual(r.state, "CARI")
        self.assertEqual(r.target, "teh")


class TesSampai(unittest.TestCase):
    def test_menemukan_lalu_dekati_lalu_berhenti(self):
        det = DetUji([kotak(w=0.2)])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 1)          # step pertama: mulai
        jalankan(r, jam, C.FRAME_STABIL)
        self.assertEqual(r.state, "DEKATI")
        r.step(None)                 # satu langkah lagi: baru motor digerakkan
        self.assertTrue(any(a[0] == "drive" and a[1] > 0 for a in hw.aksi))

        det.daftar = [kotak(w=C.W_BERHENTI + 0.02)]
        r.step(None)
        self.assertEqual(r.state, "IDLE")
        self.assertEqual(hw.drive_terakhir, (0.0, 0.0))
        self.assertIn(("stop",), hw.aksi)

    def test_gas_turun_saat_mendekat(self):
        r, hw, jam = robot_uji(DetUji([kotak(w=0.15)]))
        hw.tekan("kopi")
        jalankan(r, jam, 1)
        jalankan(r, jam, C.FRAME_STABIL)
        r.step(None)
        gas_jauh = hw.drive_terakhir[0]

        r.det.daftar = [kotak(w=C.W_BERHENTI - 0.01)]
        r.step(None)
        gas_dekat = hw.drive_terakhir[0]
        self.assertLess(gas_dekat, gas_jauh)

    def test_belok_ke_arah_target(self):
        r, hw, jam = robot_uji(DetUji([kotak(cx=0.85, w=0.2)]))
        hw.tekan("kopi")
        jalankan(r, jam, 1)
        jalankan(r, jam, C.FRAME_STABIL)
        r.step(None)
        kiri, kanan = hw.drive_terakhir
        self.assertGreater(kiri, kanan, "target di kanan -> roda kiri harus lebih cepat")


class TesGagal(unittest.TestCase):
    def test_timeout_cari_menyerah(self):
        r, hw, jam = robot_uji(DetUji([]))
        hw.tekan("kopi")
        r.step(None)
        jalankan(r, jam, int(C.TIMEOUT_CARI_S / 0.05) + 5)
        self.assertEqual(r.state, "IDLE")
        self.assertEqual(hw.drive_terakhir, (0.0, 0.0))

    def test_timeout_dekati_menyerah(self):
        r, hw, jam = robot_uji(DetUji([kotak(w=0.2)]))
        hw.tekan("kopi")
        jalankan(r, jam, 1)
        jalankan(r, jam, int(C.TIMEOUT_DEKATI_S / 0.05) + 5)
        self.assertEqual(r.state, "IDLE")
        self.assertEqual(hw.drive_terakhir, (0.0, 0.0))

    def test_target_hilang_saat_dekati_kembali_cari(self):
        det = DetUji([kotak(w=0.25)])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 1)
        jalankan(r, jam, C.FRAME_STABIL)
        self.assertEqual(r.state, "DEKATI")

        det.daftar = []
        langkah_grace = int(C.GRACE_HILANG_S / 0.05) + 2
        jalankan(r, jam, langkah_grace)
        self.assertEqual(r.state, "CARI")
        self.assertEqual(hw.drive_terakhir, (0.0, 0.0))


class TesCariPutar(unittest.TestCase):
    def test_tidak_ketemu_memutar_badan(self):
        r, hw, jam = robot_uji(DetUji([]))
        hw.tekan("kopi")
        r.step(None)
        langkah = int((C.JEDA_PERIKSA_S + C.MIN_PUTAR_S) / 0.05) + 6
        jalankan(r, jam, langkah)
        self.assertEqual(r.state, "CARI")
        putar = [a for a in hw.aksi if a[0] == "drive" and a[1] * a[2] < 0]
        self.assertTrue(putar, "roda harus berlawanan arah saat memutar badan")

    def test_arah_putar_berbalik_setelah_satu_putaran(self):
        r, hw, jam = robot_uji(DetUji([]))
        hw.tekan("kopi")
        r.step(None)
        arah_awal = r.arah
        for _ in range(C.LANGKAH_PER_ARAH):
            r._langkah_berikut()
        self.assertNotEqual(r.arah, arah_awal)
        self.assertEqual(r.langkah, 0)


class TesDuty(unittest.TestCase):
    def test_deadband_dan_batas_minimal(self):
        r, _, _ = robot_uji()
        self.assertEqual(r._duty(0.02), 0.0)
        self.assertAlmostEqual(r._duty(0.10), C.SPEED_MIN)
        self.assertAlmostEqual(r._duty(-0.10), -C.SPEED_MIN)
        self.assertAlmostEqual(r._duty(0.80), 0.80)


class TesFakeDetector(unittest.TestCase):
    def test_target_membesar_sampai_ambang(self):
        det = vision.FakeDetector(jeda_s=0, langkah=0.05)
        det.set_target("kopi")
        w_awal = None
        for _ in range(20):
            d = det.detect(None)
            if d:
                w_awal = w_awal if w_awal is not None else d[0].w
                terakhir = d[0]
        self.assertGreater(terakhir.w, w_awal)
        self.assertGreaterEqual(terakhir.w, C.W_BERHENTI)

    def test_target_kosong_sebelum_tombol(self):
        det = vision.FakeDetector(jeda_s=0)
        self.assertEqual(det.detect(None), [])


if __name__ == "__main__":
    unittest.main()


class TesTargetStatis(unittest.TestCase):
    """Gelas tidak bergerak: deteksi putus sesaat bukan alasan berhenti."""

    def test_hilang_sesaat_tetap_maju(self):
        det = DetUji([kotak(w=0.30)])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 1 + C.FRAME_STABIL + 2)      # masuk DEKATI lalu menggas
        self.assertEqual(r.state, "DEKATI")
        self.assertNotEqual(hw.drive_terakhir, (0.0, 0.0))
        sebelum = hw.drive_terakhir

        det.daftar = []                                # satu-dua frame buram
        r.step(None)
        self.assertEqual(r.state, "DEKATI", "jangan langsung cari ulang")
        self.assertEqual(hw.drive_terakhir, sebelum,
                         "perintah terakhir harus dilanjutkan, bukan stop")

    def test_setelah_grace_baru_cari_ulang(self):
        det = DetUji([kotak(w=0.30)])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 1 + C.FRAME_STABIL + 2)
        det.daftar = []
        langkah = int(C.GRACE_HILANG_S / 0.05) + 3
        jalankan(r, jam, langkah)
        self.assertEqual(r.state, "CARI")


class DetUjiBasi(DetUji):
    """Meniru detektor async: hasil sama terus, generasi tidak naik."""

    generasi = 7

    def detect(self, _frame):
        return list(self.daftar)


class TesGenerasiStabil(unittest.TestCase):
    def test_hasil_basi_tidak_dihitung_sebagai_frame_baru(self):
        det = DetUjiBasi([kotak()])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 20)
        self.assertEqual(r.state, "CARI",
                         "satu deteksi basi tidak boleh langsung mengunci target")

    def test_generasi_baru_mengunci_target(self):
        det = DetUjiBasi([kotak()])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        r.step(None)                       # langkah ini hanya membaca tombol
        for i in range(C.FRAME_STABIL):
            det.generasi = 10 + i
            r.step(None)
            jam.maju(0.05)
        self.assertEqual(r.state, "DEKATI")


class TesJarakDariKotak(unittest.TestCase):
    """Jarak ditebak dari lebar kotak; dua penjaga harus bekerja."""

    def test_satu_frame_besar_tidak_membuat_berhenti(self):
        det = DetUji([kotak(w=0.40)])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 1 + C.FRAME_STABIL + 2)
        self.assertEqual(r.state, "DEKATI")

        det.daftar = [kotak(w=0.55)]        # satu deteksi kebetulan besar
        r.step(None)
        self.assertEqual(r.state, "DEKATI", "median menahan lonjakan satu frame")

        jalankan(r, jam, 2)                 # 0.55 berulang -> memang sudah dekat
        self.assertEqual(r.state, "IDLE")

    def test_kotak_terpotong_tepi_dianggap_sudah_dekat(self):
        # kanan kotak melewati tepi -> lebar terukur lebih kecil dari aslinya,
        # jadi tanpa penjaga robot akan terus maju menabrak gelas
        det = DetUji([kotak(cx=0.78, w=0.45)])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 1 + C.FRAME_STABIL + 2)
        self.assertEqual(r.state, "IDLE")

    def test_kotak_terpotong_tapi_kecil_tidak_menghentikan(self):
        det = DetUji([kotak(cx=0.06, w=0.10)])
        r, hw, jam = robot_uji(det)
        hw.tekan("kopi")
        jalankan(r, jam, 1 + C.FRAME_STABIL + 2)
        self.assertEqual(r.state, "DEKATI")
        self.assertEqual(len(r.lebar_riwayat), 0,
                         "lebar terpotong tidak boleh masuk riwayat jarak")

