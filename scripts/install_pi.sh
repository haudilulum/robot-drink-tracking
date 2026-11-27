#!/usr/bin/env bash
# Pasang dependensi + service systemd untuk Robot Drink Tracking.
# Jalankan di Raspberry Pi:  bash scripts/install_pi.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT=/etc/systemd/system/robot-drink-tracking.service
USER_RUN="${SUDO_USER:-$(id -un)}"

echo "== folder : $DIR"
echo "== user   : $USER_RUN"

sudo apt-get update
sudo apt-get install -y python3-opencv python3-numpy python3-gpiozero python3-lgpio

# cek cepat sebelum service dipasang
cd "$DIR"
python3 -c "import cv2;c=cv2.VideoCapture(0);c.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'));ok,f=c.read();print('kamera',int(c.get(3)),'x',int(c.get(4)),'@',round(c.get(5)),'fps','frame=ada' if ok else 'frame=GAGAL')" || echo "!! kamera belum terbaca — cek kabel webcam"

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
