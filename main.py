"""State machine robot kopi-teh.

Alur:
    IDLE --PB1/PB2--> CARI (putar-periksa) --target stabil--> DEKATI --cukup dekat--> SAMPAI
    CARI --timeout--> GAGAL
    DEKATI --target hilang > GRACE--> CARI
    Tekan tombol yang sama saat robot bergerak = berhenti.

Jalan di Pi      : python3 main.py
Uji tanpa HW     : python3 main.py --dry-run --seconds 20
Lihat gambar kotak: python3 main.py --debug --vision yolo
"""

import argparse
import os
import sys
import time

import config as C
import hardware
import vision


class Robot:
    def __init__(self, hw=None, det=None, verbose=True, jam=None, tidur=None):
        self.hw = hw if hw is not None else hardware.make()
        self.det = det if det is not None else vision.make()
        self.verbose = verbose
        self.jam = jam if jam is not None else time.monotonic
        self.tidur = tidur if tidur is not None else time.sleep

        self.state = "IDLE"
        self.target = None

        self.t_mulai = 0.0          # masuk state sekarang
        self.t_lihat = 0.0          # terakhir target terlihat
        self.t_fase = 0.0           # masuk fase putar/periksa
        self.stabil = 0
        self.fase = "periksa"
        self.arah = 1               # +1 kiri, -1 kanan
        self.langkah = 0
        self.deteksi_terakhir = []
        self.perintah_ingat = (0.0, 0.0)   # duty terakhir saat maju ke target
        self.generasi_stabil = -1          # generasi hasil deteksi yang dihitung

    # ---------------------------------------------------------------- utilitas
    def log(self, *a):
        if self.verbose:
            print(f"[{self.state:6}]", *a, flush=True)

    def ke(self, state):
        self.state = state
        self.t_mulai = self.jam()

    def mulai(self, target):
        if self.state != "IDLE":
            self.hw.stop()
        self.target = target
        if hasattr(self.det, "set_target"):
            self.det.set_target(target)
        self.ke("CARI")
        self.stabil = 0
        self.arah = 1
        self.langkah = 0
        self.fase = "periksa"
        self.t_fase = self.jam()
        self.perintah_ingat = (0.0, 0.0)
        self.generasi_stabil = -1
        self.hw.led_set(True)
        self.log(f"tombol {target} -> mulai mencari")

    def berhenti(self, alasan=""):
        self.hw.stop()
        self.hw.led_set(False)
        self.target = None
        if hasattr(self.det, "set_target"):
            self.det.set_target(None)
        self.ke("IDLE")
        self.log("berhenti", alasan)

    def sampai(self):
        self.hw.stop()
        self.hw.led_set(False)
        self.hw.beep(1)
        self.log(f"sampai di {self.target}")
        self.tidur(C.PAUSE_SAMPAI_S)
        self.berhenti("(sampai)")

    def gagal(self, alasan):
        self.hw.stop()
        self.hw.led_set(False)
        self.hw.beep(2)
        self.log(f"menyerah: {alasan}")
        self.target = None
        if hasattr(self.det, "set_target"):
            self.det.set_target(None)
        self.ke("IDLE")

    def _duty(self, nilai):
        """Duty satu roda: 0 kalau kecil (deadband), selain itu minimal SPEED_MIN."""
        if abs(nilai) < 0.05:
            return 0.0
        tanda = 1.0 if nilai > 0 else -1.0
        return tanda * max(abs(nilai), C.SPEED_MIN)

    # ------------------------------------------------------------------- loop
    def step(self, frame):
        t = self.jam()

        pb = self.hw.read_button()
        if pb:
            if self.state != "IDLE" and pb == self.target:
                self.berhenti("(tombol sama ditekan lagi)")
                return
            self.mulai(pb)                    # tombol lain = ganti target
            return

        if self.state == "IDLE":
            self.hw.stop()
            return

        if self.state == "CARI":
            self._cari(frame, t)
            return

        if self.state == "DEKATI":
            self._dekati(frame, t)

    # ------------------------------------------------------------ cari target
    def _cari(self, frame, t):
        if self.fase == "putar":
            self.hw.drive(C.SPEED_PUTAR * self.arah, -C.SPEED_PUTAR * self.arah)
            if t - self.t_fase >= self._durasi_putar():
                self.hw.stop()
                self.fase = "periksa"
                self.t_fase = t
            return

        # fase periksa: chassis diam dulu, baru kamera dipercaya
        self.hw.stop()
        d = vision.pilih_target(self.det.detect(frame), self.target)
        if d is not None:
            # Dengan detektor async, detect() mengembalikan hasil cache yang sama
            # berkali-kali; tanpa cek generasi, satu deteksi bisa langsung
            # dianggap "3 frame stabil".
            generasi = getattr(self.det, "generasi", None)
            if generasi is None or generasi != self.generasi_stabil:
                self.stabil += 1
                self.generasi_stabil = generasi
            self.t_lihat = t
            self.t_fase = t
            if self.stabil >= C.FRAME_STABIL:
                self.ke("DEKATI")
                self.log(f"target {d} -> dekati")
            return

        self.stabil = 0
        if t - self.t_fase < C.JEDA_PERIKSA_S:
            return
        if t - self.t_mulai > C.TIMEOUT_CARI_S:
            self.gagal(f"{C.TIMEOUT_CARI_S:.0f} s tidak menemukan {self.target}")
            return
        self._langkah_berikut()

    def _durasi_putar(self):
        return max(C.MIN_PUTAR_S, C.SUDUT_LANGKAH / float(C.DERAJAT_PER_DETIK))

    def _langkah_berikut(self):
        self.langkah += 1
        if self.langkah >= C.LANGKAH_PER_ARAH:
            self.langkah = 0
            self.arah *= -1                   # sudah 360 derajat, balik arah
        self.fase = "putar"
        self.t_fase = self.jam()

    # -------------------------------------------------------------- mendekati
    def _dekati(self, frame, t):
        d = vision.pilih_target(self.det.detect(frame), self.target)

        if d is None:
            # Gelas tidak bergerak: deteksi yang putus sesaat (osilasi kamera,
            # bayangan, satu frame buram) bukan alasan berhenti. Lanjutkan
            # perintah terakhir supaya robot tidak berhenti-maju berulang.
            self.hw.drive(*self.perintah_ingat)
            if t - self.t_lihat > C.GRACE_HILANG_S:
                self.log("target hilang -> cari ulang")
                self.ke("CARI")
                self.stabil = 0
                self.fase = "periksa"
                self.t_fase = t
            return

        self.t_lihat = t
        if d.w >= C.W_BERHENTI:
            self.sampai()
            return

        if t - self.t_mulai > C.TIMEOUT_DEKATI_S:
            self.gagal(f"{C.TIMEOUT_DEKATI_S:.0f} s tidak sampai (tersangkut?)")
            return

        # gas: penuh saat jauh, turun linier saat mendekat (anti-tabrak)
        if d.w <= C.W_MULAI_PELAN:
            dasar = C.SPEED_MAJU
        else:
            f = ((d.w - C.W_MULAI_PELAN) /
                 (C.W_BERHENTI - C.W_MULAI_PELAN))
            dasar = C.SPEED_MAJU + (C.SPEED_MIN - C.SPEED_MAJU) * C.clamp(f, 0, 1)

        error = d.cx - 0.5                    # >0 berarti target di kanan
        belok = C.clamp(C.KP_BELOK * error, -C.KOREKSI_MAKS, C.KOREKSI_MAKS)
        # target di kanan -> roda kiri lebih cepat -> badan berbelok ke kanan
        kiri, kanan = self._duty(dasar + belok), self._duty(dasar - belok)
        self.perintah_ingat = (kiri, kanan)   # target statis: dipakai saat deteksi putus
        self.hw.drive(kiri, kanan)


# ---------------------------------------------------------------------- CLI
def _jadwal_dry_run(hw, t_mulai, saat=1.0, tombol=None):
    """Suntik satu tekanan tombol pada mode --dry-run."""
    if hasattr(hw, "tekan") and time.monotonic() - t_mulai > saat:
        hw.tekan(tombol or os.environ.get("ROBOT_FAKE_PB", "kopi"))
        return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Robot pencari kopi/teh (Pi 3B+)")
    ap.add_argument("--dry-run", action="store_true",
                    help="tanpa GPIO dan kamera (hardware + visi palsu)")
    ap.add_argument("--seconds", type=float, default=0, help="batas waktu uji (detik)")
    ap.add_argument("--vision", default=None,
                    choices=["yolo", "yolo-sync", "fake"],
                    help="backend visi (menimpa config)")
    ap.add_argument("--debug", metavar="DIR", default=None,
                    help="simpan frame beranotasi tiap N frame")
    ap.add_argument("--debug-setiap", type=int, default=15)
    ap.add_argument("--tombol-uji", default="kopi",
                    choices=["kopi", "teh"], help="tombol yang disuntik saat --dry-run")
    ap.add_argument("--diam", action="store_true", help="log hanya perpindahan state")
    args = ap.parse_args(argv)

    if args.dry_run:
        os.environ["ROBOT_DRY"] = "1"
        os.environ["VISION_BACKEND"] = "fake"
    elif args.vision:
        os.environ["VISION_BACKEND"] = args.vision
    hardware.DRY = os.environ.get("ROBOT_DRY") == "1"

    if args.debug:
        os.makedirs(args.debug, exist_ok=True)

    robot = Robot(verbose=not args.diam)
    print(f"visi={os.environ.get('VISION_BACKEND', C.VISION_BACKEND)} "
          f"servo_pan={'ya' if C.PAKAI_SERVO_PAN else 'tidak'} "
          f"berhenti_di_w={C.W_BERHENTI:.2f}")
    print("siap — PB1 = kopi, PB2 = teh. Ctrl-C untuk keluar.")

    t0 = time.monotonic()
    periode = 1.0 / max(1, C.LOOP_HZ)
    sudah_disuntik = False
    nomor = 0
    try:
        while True:
            frame = robot.det.read()
            if not sudah_disuntik and args.dry_run:
                sudah_disuntik = _jadwal_dry_run(robot.hw, t0, 1.0, args.tombol_uji)
            robot.step(frame)

            if args.debug and hasattr(frame, "shape"):
                nomor += 1
                if nomor % max(1, args.debug_setiap) == 0:
                    daftar = robot.det.detect(frame)
                    robot.deteksi_terakhir = daftar
                    berkas = os.path.join(args.debug, f"frame_{nomor:06d}.jpg")
                    vision.cv2.imwrite(berkas, vision.gambar_debug(frame, daftar))

            if args.seconds and time.monotonic() - t0 > args.seconds:
                print(f"--- uji {args.seconds:.0f} s selesai, state={robot.state}")
                break
            time.sleep(periode)
    except KeyboardInterrupt:
        print("\ninterupsi")
    finally:
        robot.hw.close()
        robot.det.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
