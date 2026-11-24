#!/bin/sh
# Opens the LidSense dashboard full screen on the touchscreen.
# To stop it starting: delete the "lidsense-kiosk" line in ~/.config/labwc/autostart
sleep 8
BROWSER=$(command -v chromium || command -v chromium-browser)
exec "$BROWSER" --kiosk --noerrdialogs --disable-infobars --incognito \
  --password-store=basic http://127.0.0.1:8080
