"""Alat kalibrasi HSV dari foto (tanpa GUI, aman untuk SSH).

Dipakai begini:
  1. Ambil foto dulu:            python3 tangkap.py --jumlah 3
  2. Lihat fotonya, tentukan kotak penandanya (piksel), lalu:
     python3 kalibrasi.py foto/frame_1.jpg --x 312 --y 180 --w 46 --h 34 --label kopi
  3. Tempel hasilnya ke config.py bagian WARNA.

Kalau belum tahu koordinatnya, pakai --auto: skrip mencari sendiri gumpalan warna
paling menonjol di seluruh gambar dan melaporkan rentang HSV beserta letaknya.
"""

import argparse
import os
import sys

import cv2
import numpy as np


def hsv_region(img, x, y, w, h):
    tinggi, lebar = img.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(lebar, x + max(1, w)), min(tinggi, y + max(1, h))
    potong = img[y0:y1, x0:x1]
    if potong.size == 0:
        raise SystemExit("kotak di luar gambar")
    return cv2.cvtColor(potong, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int32)


def rata_sirkular_hue(hue):
    """Rata-rata hue yang benar untuk data yang melewati batas 0/179 (mis. merah)."""
    rad = np.deg2rad(np.asarray(hue, dtype=np.float64) * 2.0)   # 0..179 -> 0..360
    x = float(np.cos(rad).mean())
    y = float(np.sin(rad).mean())
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return float(np.median(hue))
    return float((np.rad2deg(np.arctan2(y, x)) / 2.0) % 180.0)


def rentang_hue_circular(hue, lebar_persen=97.0):
    """Rentang hue, dipecah dua kalau melewati batas 0/179 (merah)."""
    puncak = rata_sirkular_hue(hue)
    jarak = np.abs(np.asarray(hue, dtype=np.float64) - puncak)
    jarak = np.minimum(jarak, 180.0 - jarak)            # jarak sirkular
    setengah = float(np.percentile(jarak, lebar_persen))
    setengah = max(4.0, min(60.0, setengah))
    lo = int(round((puncak - setengah) % 180))
    hi = int(round((puncak + setengah) % 180))
    if lo <= hi:
        return [(lo, hi)]
    return [(lo, 179), (0, hi)]                         # terbelah di 0/179


def saran(px, label="kopi"):
    h, s, v = px[:, 0], px[:, 1], px[:, 2]
    rentang_h = rentang_hue_circular(h)
    s_lo = int(max(30, np.percentile(s, 3) * 0.7))
    v_lo = int(max(25, np.percentile(v, 3) * 0.7))
    daftar = [((lo, s_lo, v_lo), (hi, 255, 255)) for lo, hi in rentang_h]

    print(f"\n== {label} ==")
    print(f"piksel            : {len(px)}")
    print(f"H  p2/p50/p98     : {np.percentile(h,2):.0f} / {np.median(h):.0f} / {np.percentile(h,98):.0f}")
    print(f"S  p2/p50/p98     : {np.percentile(s,2):.0f} / {np.median(s):.0f} / {np.percentile(s,98):.0f}")
    print(f"V  p2/p50/p98     : {np.percentile(v,2):.0f} / {np.median(v):.0f} / {np.percentile(v,98):.0f}")
    print("\ntempel di config.py:")
    print(f'WARNA = {{"{label}": {daftar}}}')

    if np.median(s) < 45:
        print("\nPERINGATAN: saturasi rendah (<45) — penandanya pudar/putih/abu.")
        print("Rentang S akan menangkap meja juga. Pakai penanda yang lebih pekat.")
    if np.median(v) < 40:
        print("\nPERINGATAN: kecerahan rendah (<40) — ruangan gelap / kamera belum warmup.")
    return daftar


def gumpalan_teratas(img, jumlah=3, min_luas=400):
    """Cari gumpalan warna menonjol (S tinggi) dan kembalikan info per gumpalan."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array((0, 70, 35), np.uint8), np.array((179, 255, 255), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    kontur = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    kotak = []
    for k in kontur:
        luas = cv2.contourArea(k)
        if luas < min_luas:
            continue
        x, y, w, h = cv2.boundingRect(k)
        kotak.append((luas, x, y, w, h))
    kotak.sort(reverse=True)
    return kotak[:jumlah]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Saran rentang HSV dari foto")
    ap.add_argument("foto")
    ap.add_argument("--label", default="kopi", choices=["kopi", "teh"])
    ap.add_argument("--x", type=int, default=None)
    ap.add_argument("--y", type=int, default=None)
    ap.add_argument("--w", type=int, default=None)
    ap.add_argument("--h", type=int, default=None)
    ap.add_argument("--auto", action="store_true", help="cari gumpalan warna otomatis")
    ap.add_argument("--potong", default=None, help="simpan potongan kotak ke file ini")
    args = ap.parse_args(argv)

    if not os.path.exists(args.foto):
        raise SystemExit(f"foto tidak ada: {args.foto}")
    img = cv2.imread(args.foto)
    if img is None:
        raise SystemExit(f"gagal membaca gambar: {args.foto}")
    print(f"gambar {args.foto}: {img.shape[1]}x{img.shape[0]}")

    if args.auto or args.x is None:
        kotak = gumpalan_teratas(img)
        if not kotak:
            raise SystemExit("tidak ada gumpalan warna menonjol; pakai --x/--y/--w/--h manual")
        print(f"\nditemukan {len(kotak)} gumpalan (urut luas):")
        for i, (luas, x, y, w, h) in enumerate(kotak, 1):
            print(f"  {i}. luas={luas:7.0f}  x={x:4d} y={y:4d} w={w:3d} h={h:3d}"
                  f"   rasio h/w={h/w:.2f}")
        if args.x is None:
            _, x, y, w, h = kotak[0]
            print(f"\nmemakai gumpalan terbesar: x={x} y={y} w={w} h={h}")
            if args.potong:
                cv2.imwrite(args.potong, img[y:y + h, x:x + w])
                print(f"potongan disimpan: {args.potong}")
            saran(hsv_region(img, x, y, w, h), args.label)
            return 0

    if args.w is None or args.h is None:
        raise SystemExit("butuh --x --y --w --h lengkap")
    px = hsv_region(img, args.x, args.y, args.w, args.h)
    if args.potong:
        cv2.imwrite(args.potong, img[args.y:args.y + args.h, args.x:args.x + args.w])
        print(f"potongan disimpan: {args.potong}")
    saran(px, args.label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
