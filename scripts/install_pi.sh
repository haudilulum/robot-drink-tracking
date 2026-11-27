#!/usr/bin/env bash
# Pasang dependensi + service systemd untuk Robot Drink Tracking.
# Target: Raspberry Pi OS 32-bit (Trixie / Debian 13), Pi 3B+.
# Jalankan di Raspberry Pi:  bash scripts/install_pi.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT=/etc/systemd/system/robot-drink-tracking.service
USER_RUN="${SUDO_USER:-$(id -un)}"
VENV="$DIR/.venv"

echo "== folder : $DIR"
echo "== user   : $USER_RUN"

if [ -r /etc/os-release ]; then
    . /etc/os-release
    echo "== sistem : ${PRETTY_NAME:-?} (${VERSION_CODENAME:-?})"
    echo "== arch   : $(uname -m)"
fi

sudo apt-get update
sudo apt-get install -y python3-venv python3-numpy python3-gpiozero git
# lgpio disediakan repo Raspberry Pi, bukan Debian. Kalau tidak ada, gpiozero
# tetap bisa memakai backend lain (rpi-lgpio / RPi.GPIO).
sudo apt-get install -y python3-lgpio || echo "!! python3-lgpio tidak tersedia; lewati"

cd "$DIR"

# OpenCV dari apt (4.10 di Trixie) memuat ONNX opset baru tanpa error tetapi
# hasil forward-nya salah -> deteksi selalu kosong. Wheel piwheels 5.x benar
# untuk armv7l, jadi OpenCV dipasang di venv, bukan lewat apt.
echo "== venv + OpenCV 5.x (piwheels)"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv --system-site-packages "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet \
    --index-url https://www.piwheels.org/simple \
    --extra-index-url https://pypi.org/simple \
    "opencv-python-headless>=5.0"
PY="$VENV/bin/python"

echo "== cek pustaka"
"$PY" - <<'PY'
import sys
print("python  :", sys.version.split()[0], "|", sys.executable)
try:
    import cv2
    print("opencv  :", cv2.__version__, "| dnn:", hasattr(cv2, "dnn"))
    if not hasattr(cv2, "dnn"):
        print("!! OpenCV tanpa modul dnn — pasang ulang opencv-python-headless di venv")
    elif int(cv2.__version__.split(".")[0]) < 5:
        print("!! OpenCV < 5: ONNX opset baru bisa termuat tapi hasilnya salah/kosong")
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
"$PY" -c "import cv2;c=cv2.VideoCapture(0);c.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'));ok,f=c.read();print('kamera',int(c.get(3)),'x',int(c.get(4)),'@',round(c.get(5)),'fps','frame=ada' if ok else 'frame=GAGAL')" \
    || echo "!! kamera belum terbaca — cek kabel webcam"

sed -e "s|__DIR__|$DIR|g" -e "s|__USER__|$USER_RUN|g" -e "s|__PY__|$PY|g" \
    "$DIR/systemd/robot-drink-tracking.service" | sudo tee "$UNIT" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable robot-drink-tracking.service
echo
echo "Service terpasang (belum dijalankan), memakai: $PY"
echo "  sudo systemctl start robot-drink-tracking     # jalankan sekarang"
echo "  journalctl -u robot-drink-tracking -f         # lihat log"
echo "  sudo systemctl stop robot-drink-tracking      # hentikan"
echo
echo "Catatan: hentikan service sebelum menjalankan main.py manual dari terminal,"
echo "         supaya GPIO tidak dipakai dua proses sekaligus."
