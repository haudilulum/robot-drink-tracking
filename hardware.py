"""Lapisan hardware: 4 motor DC 4WD (2 modul MX1508), 2 tombol, LED, buzzer.

Empat roda digerakkan semua (skid-steer). Sisi kiri dan sisi kanan selalu diberi
duty yang sama, jadi kontrol tetap dua angka: (kiri, kanan).


Dua implementasi:
  Hardware     -> Raspberry Pi + gpiozero
  FakeHardware -> merekam semua aksi, dipakai tes dan mode --dry-run

Tombol dibaca lewat event (when_pressed -> antrean), bukan polling, supaya tekan
singkat tidak hilang walau loop sedang sibuk memproses frame.
"""

from collections import deque
import os
import time

import config as C


class Hardware:
    def __init__(self):
        from gpiozero import Button, Motor, Buzzer, LED

        self.kiri_depan = Motor(forward=C.PIN_MOTOR_KIRI_DEPAN_MAJU,
                                backward=C.PIN_MOTOR_KIRI_DEPAN_MUNDUR)
        self.kiri_belakang = Motor(forward=C.PIN_MOTOR_KIRI_BELAKANG_MAJU,
                                   backward=C.PIN_MOTOR_KIRI_BELAKANG_MUNDUR)
        self.kanan_depan = Motor(forward=C.PIN_MOTOR_KANAN_DEPAN_MAJU,
                                 backward=C.PIN_MOTOR_KANAN_DEPAN_MUNDUR)
        self.kanan_belakang = Motor(forward=C.PIN_MOTOR_KANAN_BELAKANG_MAJU,
                                    backward=C.PIN_MOTOR_KANAN_BELAKANG_MUNDUR)
        self.led = LED(C.PIN_LED)
        self.buzzer = Buzzer(C.PIN_BUZZER)

        self._antrian = deque()
        self.pb = {}
        for nama, pin in (("kopi", C.PIN_PB_KOPI), ("teh", C.PIN_PB_TEH)):
            tombol = Button(pin, pull_up=True, bounce_time=C.BOUNCE_S)
            tombol.when_pressed = (lambda n=nama: self._antrian.append(n))
            self.pb[nama] = tombol

    # ------------------------------------------------------------------ tombol
    def read_button(self):
        """Nama tombol yang ditekan sejak pembacaan terakhir, atau None."""
        return self._antrian.popleft() if self._antrian else None

    # ------------------------------------------------------------------- motor
    def drive(self, kiri, kanan):
        k = C.clamp(kiri, -1.0, 1.0)
        n = C.clamp(kanan, -1.0, 1.0)
        self.kiri_depan.value = k
        self.kiri_belakang.value = k
        self.kanan_depan.value = n
        self.kanan_belakang.value = n

    def stop(self):
        for roda in (self.kiri_depan, self.kiri_belakang,
                     self.kanan_depan, self.kanan_belakang):
            roda.value = 0.0

    # ------------------------------------------------------------------- suara
    def beep(self, n=1, dur=0.12):
        for _ in range(n):
            self.buzzer.on()
            time.sleep(dur)
            self.buzzer.off()
            time.sleep(dur)

    def led_set(self, nyala):
        self.led.value = 1 if nyala else 0

    def close(self):
        self.stop()
        self.led.off()
        self.buzzer.off()
        for tombol in self.pb.values():
            tombol.close()


class FakeHardware:
    """Tanpa GPIO. Semua aksi dicatat di ``aksi`` supaya bisa diperiksa tes."""

    def __init__(self):
        self._antrian = deque()
        self.aksi = []
        self.drive_terakhir = (0.0, 0.0)
        self.led = False
        self.ditutup = False

    # Tes / dry-run memanggil ini untuk meniru jari menekan tombol.
    def tekan(self, nama):
        self._antrian.append(nama)

    def read_button(self):
        return self._antrian.popleft() if self._antrian else None

    def drive(self, kiri, kanan):
        self.drive_terakhir = (round(C.clamp(kiri, -1.0, 1.0), 3),
                               round(C.clamp(kanan, -1.0, 1.0), 3))
        self.aksi.append(("drive",) + self.drive_terakhir)

    def stop(self):
        self.drive_terakhir = (0.0, 0.0)
        self.aksi.append(("stop",))

    def beep(self, n=1, dur=0.12):
        self.aksi.append(("beep", n))

    def led_set(self, nyala):
        self.led = bool(nyala)
        self.aksi.append(("led", self.led))

    def close(self):
        self.ditutup = True
        self.stop()


def make():
    """Hardware asli kecuali ROBOT_DRY=1."""
    if os.environ.get("ROBOT_DRY") == "1":
        return FakeHardware()
    return Hardware()
