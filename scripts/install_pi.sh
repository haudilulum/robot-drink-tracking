#!/usr/bin/env bash
# Pasang dependensi + service systemd untuk Robot Drink Tracking.
# Target: Raspberry Pi OS Trixie (Debian 13), 32-bit atau 64-bit.
# Jalankan di Raspberry Pi:  bash scripts/install_pi.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT=/etc/systemd/system/robot-drink-tracking.service
USER_RUN="${SUDO_USER:-$(id -un)}"

echo "== folder : $DIR"
echo "== user   : $USER_RUN"

if [ -r /etc/os-release ]; then
    . /etc/os-release
    echo "== sistem : ${PRETTY_NAME:-?} (${VERSION_CODENAME:-?})"
    if [ "${VERSION_CODENAME:-}" != "trixie" ]; then
        echo "   catatan: repo ini diuji di Trixie; nama paket di rilis lain bisa beda"
    fi
fi

sudo apt-get update
sudo apt-get install -y python3-opencv python3-numpy python3-gpiozero git
# lgpio disediakan repo Raspberry Pi, bukan Debian. Kalau tidak ada, gpiozero
# tetap bisa memakai backend lain (rpi-lgpio / RPi.GPIO).
sudo apt-get install -y python3-lgpio || echo "!! python3-lgpio tidak tersedia; lewati"

cd "$DIR"
echo "== cek pustaka"
python3 - <<'PY'
import sys
print("python  :", sys.version.split()[0])
try:
    import cv2
    print("opencv  :", cv2.__version__, "| dnn:", hasattr(cv2, "dnn"))
    if not hasattr(cv2, "dnn"):
        print("!! OpenCV tanpa modul dnn — pasang ulang python3-opencv dari apt")
except Exception as e:                       # noqa: BLE001
    print("!! opencv GAGAL:", e)
try:
    import gpiozero
    print("gpiozero:", gpiozero.__version__, "| backend:", gpiozero.Device.pin_factory)
    if gpiozero.Device.pin_factory is None:
        print("!! tidak ada pin factory — cek /dev/gpiochip* dan paket python3-lgpio")
except Exception as e:                       # noqa: BLE001
    print("!! gpiozero GAGAL:", e)
PY

echo "== cek kamera"
python3 -c "import cv2;c=cv2.VideoCapture(0);c.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'));ok,f=c.read();print('kamera',int(c.get(3)),'x',int(c.get(4)),'@',round(c.get(5)),'fps','frame=ada' if ok else 'frame=GAGAL')" \
    || echo "!! kamera belum terbaca — cek kabel webcam"

sed -e "s|__DIR__|$DIR|g" -e "s|__USER__|$USER_RUN|g" \
    "$DIR/systemd/robot-drink-tracking.service" | sudo tee "$UNIT" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable robot-drink-tracking.service
echo
echo "Service terpasang (belum dijalankan). Perintah:"
echo "  sudo systemctl start robot-drink-tracking     # jalankan sekarang"
echo "  journalctl -u robot-drink-tracking -f         # lihat log"
echo "  sudo systemctl stop robot-drink-tracking      # hentikan"
echo
echo "Catatan: hentikan service sebelum menjalankan main.py manual dari terminal,"
echo "         supaya GPIO tidak dipakai dua proses sekaligus."
