#!/bin/bash
# LidSense installer for Raspberry Pi OS Bookworm (Raspberry Pi 5).
# Run from the unpacked folder:  sudo bash pi/install.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/lidsense

echo "== packages"
apt-get update
apt-get install -y chromium python3-numpy python3-serial python3-flask python3-requests python3-yaml rsync

echo "== user and folders"
id lidsense >/dev/null 2>&1 || useradd --system --home /var/lib/lidsense --groups dialout lidsense
mkdir -p "$DEST" /etc/lidsense /var/lib/lidsense
rsync -a --delete --exclude data/ "$SRC/pi" "$SRC/frontend" "$DEST/"
mkdir -p "$DEST/pi/data"
# keep calibration on upgrades: only copy calibration files that are not there yet
cp -n "$SRC"/pi/data/* "$DEST/pi/data/" 2>/dev/null || true
chown -R lidsense:lidsense /var/lib/lidsense "$DEST/pi/data"

[ -f /etc/lidsense/config.yaml ] || cp "$SRC/pi/config.example.yaml" /etc/lidsense/config.yaml
if [ ! -f /etc/lidsense/secrets.env ]; then
  echo "LIDSENSE_API_KEY=paste-the-device-key-from-the-server-here" > /etc/lidsense/secrets.env
fi
chown root:lidsense /etc/lidsense/secrets.env && chmod 640 /etc/lidsense/secrets.env

echo "== udev, service, kiosk"
cp "$SRC/pi/deploy/99-nanovna.rules" /etc/udev/rules.d/
udevadm control --reload-rules && udevadm trigger
cp "$SRC/pi/deploy/lidsense.service" /etc/systemd/system/
# Touchscreen kiosk: open the dashboard full screen when the desktop starts (labwc, the
# default desktop on Raspberry Pi OS Bookworm/Trixie). Added for the user who ran sudo.
DESK_USER="${SUDO_USER:-}"
if [ -n "$DESK_USER" ] && [ "$DESK_USER" != "root" ]; then
  HOME_DIR="$(getent passwd "$DESK_USER" | cut -d: -f6)"
  mkdir -p "$HOME_DIR/.config/labwc"
  touch "$HOME_DIR/.config/labwc/autostart"
  if ! grep -q "lidsense-kiosk" "$HOME_DIR/.config/labwc/autostart"; then
    echo "/opt/lidsense/pi/deploy/lidsense-kiosk.sh &  # lidsense-kiosk" >> "$HOME_DIR/.config/labwc/autostart"
  fi
  chown -R "$DESK_USER":"$DESK_USER" "$HOME_DIR/.config/labwc"
fi
systemctl daemon-reload
systemctl enable lidsense
timedatectl set-ntp true || true

# Remove the old boot chain (ngrok + auto_run.sh) if it is still installed
for f in /etc/systemd/system/biosensor*.service; do
  [ -e "$f" ] && { systemctl disable --now "$(basename "$f")" || true; }
done

echo
echo "Done. Next:"
echo " 1. Edit /etc/lidsense/config.yaml (device_id, ingest_url)"
echo " 2. Put the device API key in /etc/lidsense/secrets.env"
echo " 3. sudo systemctl start lidsense ; journalctl -u lidsense -f"
