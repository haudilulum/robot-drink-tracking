"""Tangkap foto dari webcam untuk kalibrasi dan cek kamera.

    python3 tangkap.py --cek              # info kamera (resolusi, fourcc, fps)
    python3 tangkap.py --jumlah 5         # simpan 5 foto ke ./foto
    python3 tangkap.py --video 10         # rekam 10 detik ke foto/uji.avi

Kenapa perlu: HSV tidak bisa ditebak dari mata. Foto asli + kalibrasi.py jauh
lebih cepat daripada coba-coba angka di config.
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

import config as C


def buka(indeks=C.KAMERA_INDEKS):
    cap = cv2.VideoCapture(indeks)
    if not cap.isOpened():
        raise SystemExit(f"kamera {indeks} tidak bisa dibuka (cek /dev/video*)")
    if C.KAMERA_MJPG:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, C.FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, C.FRAME_H)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, C.KAMERA_BUFFER)
    return cap


def info(cap):
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    nama = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4))
    print(f"resolusi : {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
    print(f"fourcc   : {nama!r}")
    print(f"fps kamera: {cap.get(cv2.CAP_PROP_FPS):.1f}")


def ukur(cap, n=30):
    for _ in range(C.WARMUP_FRAME):
        cap.read()
    t0 = time.monotonic()
    berhasil = 0
    kecerahan = []
    for _ in range(n):
        ok, frame = cap.read()
        if not ok:
            continue
        berhasil += 1
        kecerahan.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 2].mean()))
    dt = time.monotonic() - t0
    print(f"frame     : {berhasil}/{n} dalam {dt:.2f} s -> {berhasil/dt:.1f} FPS")
    if kecerahan:
        print(f"kecerahan : rata-rata V={np.mean(kecerahan):.0f} (min {np.min(kecerahan):.0f})")
        if np.mean(kecerahan) < 40:
            print("  PERINGATAN: gambar gelap. Buka tutup lensa / tambah cahaya.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tangkap foto dari webcam")
    ap.add_argument("--indeks", type=int, default=C.KAMERA_INDEKS)
    ap.add_argument("--jumlah", type=int, default=0, help="jumlah foto yang disimpan")
    ap.add_argument("--video", type=float, default=0, help="rekam N detik")
    ap.add_argument("--keluar", default="foto")
    ap.add_argument("--cek", action="store_true", help="hanya info + ukur FPS")
    args = ap.parse_args(argv)

    cap = buka(args.indeks)
    try:
        info(cap)
        ukur(cap)
        if args.cek:
            return 0
        os.makedirs(args.keluar, exist_ok=True)

        if args.video > 0:
            keluar = os.path.join(args.keluar, "uji.avi")
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            vw = cv2.VideoWriter(keluar, cv2.VideoWriter_fourcc(*"MJPG"), 15, (w, h))
            t0 = time.monotonic()
            n = 0
            while time.monotonic() - t0 < args.video:
                ok, frame = cap.read()
                if ok:
                    vw.write(frame)
                    n += 1
            vw.release()
            print(f"rekaman {n} frame -> {keluar}")
            return 0

        for i in range(max(1, args.jumlah)):
            ok, frame = cap.read()
            if not ok:
                print("gagal membaca frame")
                continue
            berkas = os.path.join(args.keluar, f"frame_{i + 1}.jpg")
            cv2.imwrite(berkas, frame)
            print(f"disimpan {berkas}")
            time.sleep(0.3)
        return 0
    finally:
        cap.release()


if __name__ == "__main__":
    sys.exit(main())
