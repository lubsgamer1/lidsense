# LidSense v2: automated hydration monitoring

Raspberry Pi 5 + NanoVNA V2 + ferrite-loaded patch biosensor → MySQL database (managed in phpMyAdmin) → live web dashboard, also shown on the 5" touchscreen.

```
 Patch sensor ──SMA── NanoVNA V2 ──USB── Raspberry Pi 5  (lidsense.service, systemd)
                                          │  sweep → SOL calibration → resonance/S11 → quality
                                          │  check → classification → baseline → alerts
                                          │
                                          ├─ SQLite (offline buffer + local history)
                                          ├─ http://127.0.0.1:8080  → 5" touchscreen (kiosk)
                                          │
                                          └─ HTTPS POST + device API key
                                                   ▼
                                Web hosting (PHP + MySQL, e.g. Hostinger)
                                 api/ingest.php → MySQL tables  ← phpMyAdmin
                                 index.html (login) → live dashboard, alerts, CSV
```

**New to this?** Follow the step-by-step guide: **[docs/SETUP.md](docs/SETUP.md)**. It covers everything from flashing the SD card to the first measurement.

### Quick start

```bash
git clone https://github.com/YOUR-ACCOUNT/lidsense.git
cd lidsense
./make_release.sh     # builds dist/lidsense-v2.zip (Pi) and dist/lidsense-web-upload.zip (web host)
```

* **Web host:** upload `dist/lidsense-web-upload.zip` to Hostinger `public_html`, then follow [SETUP.md Step 4](docs/SETUP.md#step-4-set-up-the-database-and-web-dashboard-hostinger).
* **Raspberry Pi:** `git clone` (or copy the zip), then run `sudo bash pi/install.sh`. See [SETUP.md Step 5](docs/SETUP.md#step-5-install-lidsense-on-the-pi).
* **Never commit** `server/public_html/lidsense/api/config.php` or any `.env` file. `.gitignore` already blocks them.

## 1. Do this first: security

* **Change the MySQL password now.** `ghg.py` contains the database user, password and server IP in plain text, and it lives in the GitHub repo and its release tarballs. Anyone who has seen the repo can read or delete the data. In hPanel, go to Databases, change the password, then remove the file from git history (`git filter-repo --path ghg.py --invert-paths`, or start a fresh repository).
* **Retire `auto_run.sh`.** It downloads a tarball from GitHub on every boot, deletes the app folder and runs whatever it received, with no signature or checksum. It also runs the Python file with `bash ghg.py`, so the app never actually started that way.
* **Retire ngrok.** `start.sh` exposed the Flask `/measure` endpoint to the internet with no authentication.

In the new design the Pi never holds database credentials. It has a per-device API key that can only add readings, and the dashboard requires a login.

## 2. What changed compared with ghg.py

| Old (ghg.py) | New |
|---|---|
| Only measured when someone POSTed `/measure` through ngrok | Measures automatically every 10 s (configurable) |
| Picked the max return loss anywhere in 1.5–3.0 GHz (15 MHz steps) | Searches only 2.0–2.5 GHz. Finds the dip on a smoothed trace, then refines it on the raw trace by parabolic interpolation, which resolves well below one 15 MHz step |
| One sweep per reading | 3 sweeps per reading (thesis §6.6.1). Their spread is a motion check |
| Overlapping status bands ("Moderately Hydrated" could never be reached) that disagree with the thesis | Thesis Table 6.3 thresholds, editable in `config.yaml` |
| Table stored only `perm_value` + status: no time, frequency or device | Full record: UTC time, device, participant code, S11, return loss, resonant frequency, bandwidth, Q, quality, baseline, Δ from baseline, alert, calibration ID, plus stored S11 sweeps |
| Wrote straight to remote MySQL (password in code); data lost if offline | Local SQLite outbox. Uploads over HTTPS when online, retries, no duplicates |
| Serial reads could hang forever; port never closed; `calibration_process()` broken | Timeouts, auto-reconnect after USB resets, working calibration wizard with a verification step |
| No contact or motion detection | Free-air comparison (sensor off skin), sweep-spread check, resonance-at-band-edge check |
| No personal baseline, no alerts | Per-participant baseline (thesis: "potential for personalisation"). Dehydration, over-hydration and check-contact alerts with debouncing |
| Old Python 3.7 pins (numpy 1.21) that will not install on Pi OS Bookworm | Uses the Bookworm system packages (Python 3.11) |

Your existing `calibration_S/O/L.npy` files are included in `pi/data/` and still work. They were taken on ghg.py's 1.5–3.0 GHz / 101-point grid, so that grid is the default.

## 3. Server: MySQL + phpMyAdmin + dashboard

Any PHP 8 + MySQL/MariaDB host works. These steps are for Hostinger, which your current database is on.

1. **hPanel → Databases → MySQL Databases:** create a database and user, e.g. `u…_lidsense`. A new database is better than reusing the old database used by `ghg.py`.
2. Run `./build_server.sh` on your computer. Then upload the folder `server/public_html/lidsense/` into `public_html/` with File Manager or FTP. The dashboard will live at `https://your-domain/lidsense/`.
3. In `lidsense/api/`, copy `config.sample.php` to **`config.php`** and fill in the database name, user and password (host is usually `localhost`). Set `setup_token` to a long random string.
4. Open `https://your-domain/lidsense/setup.php?token=YOUR-TOKEN`:
   * **Create tables.** Alternatively, phpMyAdmin → your database → *Import* → `server/sql/schema.sql`.
   * **Register a Raspberry Pi.** This shows a `LIDSENSE_API_KEY=…` line exactly once. Copy it.
   * **Create a dashboard login.** Paste the generated line into `'users'` in `config.php`.
5. Set `'setup_token' => ''` again, or delete `setup.php`.
6. Make sure HTTPS is on (hPanel → SSL). `.htaccess` already redirects HTTP to HTTPS.

**phpMyAdmin:** the tables are `devices`, `readings`, `sweeps`, `alerts` and `baselines`. The view `v_readings` gives a tidy table to browse or export.

## 4. Raspberry Pi 5

```bash
# on the Pi (Raspberry Pi OS Bookworm), from the unpacked lidsense folder
sudo bash pi/install.sh
sudo nano /etc/lidsense/config.yaml      # device_id, ingest_url = https://your-domain/lidsense/api/ingest.php
sudo nano /etc/lidsense/secrets.env      # paste LIDSENSE_API_KEY=... from setup.php
sudo systemctl start lidsense
journalctl -u lidsense -f                # live log
```

Also remove the old boot entry that ran `boot.sh` (check `crontab -l`, `/etc/rc.local` and `~/.config/autostart`).

The installer:
* adds a udev rule, so the NanoVNA always appears as `/dev/nanovna`;
* installs the service, which starts on boot and restarts on crashes;
* adds the touchscreen kiosk to the desktop start-up (`~/.config/labwc/autostart` of the user who ran the installer).

**Calibration (recommended).** Stop the service, then run the wizard:

```bash
sudo systemctl stop lidsense
cd /opt/lidsense/pi && sudo -u lidsense python3 -m lidsense.calibrate --config /etc/lidsense/config.yaml
sudo -u lidsense python3 -m lidsense.calibrate --config /etc/lidsense/config.yaml --check
sudo systemctl start lidsense
```

For better resolution, first set the sweep to `2.0e+9 … 2.5e+9`, 201 points (2.5 MHz steps instead of 15 MHz), then calibrate. A calibration only matches the grid it was taken on, and the service refuses to run on a mismatch.

## 5. Using it (touchscreen)

1. **Record free-air:** lift the sensor off the skin, then tap the button. The device uses this to recognise when nothing is on the sensor, and it then stops storing readings.
2. **Set participant code:** for example `P07`. This is anonymised, and readings and baselines are kept per code.
3. **Capture baseline:** wrist on the sensor, seated, in a known well-hydrated state. 5 good readings are averaged.
4. Monitoring then runs on its own. The cloud dashboard shows the same data, read-only, for every device.

Alerts (all in `config.yaml`):
* **Dehydration:** status is Hypohydrated, **or** the reading is ≥ 3 dB drier than the personal baseline (thesis §6.6: a 3–5 dB shift marks euhydrated → hypohydrated), for 3 readings in a row. It clears after 3 normal readings.
* **Over-hydration:** status is Hyperhydrated for 3 readings in a row (can be switched off).
* **Check sensor:** 6 unreliable readings in a row (movement or contact).

## 6. Direction of the effect: please check

The thesis says two different things about which way the reading moves:

* §6.6.2 and Table 6.3: *more negative S11 (higher return loss) = more hydrated*. Hypohydrated is S11 ≥ −15 dB; Hyperhydrated is S11 < −22 dB.
* The results in the same section imply the opposite. The mean return loss is **26.0 dB for hypohydration** and **9.7 dB for hyperhydration**. Drinking 500 mL *lowered* return loss by 2–5 dB, and running *raised* it from 18 to 26 dB.
* ghg.py used yet another mapping.

The software defaults to Table 6.3 (`dehydration_sign: -1`). If your measured data shows return loss **rising** as people dry out, swap the `Hyperhydrated` and `Hypohydrated` labels in `classification.bands` and set `baseline.dehydration_sign: 1`, on both the Pi and in `config.php`. The baseline-relative alert is the more trustworthy signal while this is unresolved.

## 7. Trying it without hardware

```bash
cd pi && pip install -r requirements.txt
python -m lidsense.service --config config.example.yaml --simulate   # set paths.* and cloud.enabled first
# open http://127.0.0.1:8080
```

The simulator cycles from well hydrated to dehydrated and back every 15 minutes, and sometimes lifts the sensor off the skin, so every screen and alert can be seen.

## 8. Hardware recommendations (from the prototype)

* **Fixed contact pressure.** The thesis notes that the sensor was hand-held and that sub-millimetre air gaps shift the resonance. A 3D-printed wrist cradle or strap over the sensor port, with the 5 mm standoff the thesis found optimal, will reduce scatter more than any software change.
* **Power.** A Pi 5 on a 5 V / 3 A supply limits all USB ports *together* to 600 mA, which is shared by the NanoVNA and the display. Use the official 27 W (5 V / 5 A) USB-C supply.
* **RF stability.** Keep the NanoVNA-to-sensor coax short and fixed inside the case, put a ferrite clamp on the USB cable, and recalibrate whenever the cable is changed.
* **Temperature.** Every study measurement was taken at 22 °C. A DS18B20 skin/ambient sensor on the Pi's GPIO would allow temperature correction later. The database has room for extra fields.
* **Case material.** PLA starts to soften at about 55–60 °C, and a Pi 5 under load gets warm. Use PETG for the next print, and keep the vents in line with the fan.
* **Thesis edits noticed:** the display is described as 7-inch in §6.5.2 and 5-inch in Fig 6.15. The NanoVNA link is "Micro-USB" in §6.5.2 and USB-C in Fig 6.16. The Fig 6.9 caption says "downward shift" while the text reports an upward shift (2.20 → 2.24 GHz).

## 9. Files

```
pi/lidsense/nanovna_v2.py   NanoVNA V2 USB driver (from ghg.py, with timeouts and reconnect)
pi/lidsense/calibration.py  SOL calibration (same maths, works with the old .npy files)
pi/lidsense/features.py     resonance, S11, bandwidth/Q, contact check
pi/lidsense/logic.py        classification, baseline, alert state machine
pi/lidsense/service.py      main loop + uploader + local dashboard
pi/lidsense/calibrate.py    calibration wizard / quick check
pi/lidsense/simulator.py    fake NanoVNA for testing
pi/install.sh, pi/deploy/   systemd service, udev rule, kiosk autostart
server/sql/schema.sql       MySQL schema (phpMyAdmin import)
server/public_html/lidsense PHP API, login, setup page (dashboard copied in by build_server.sh)
frontend/                   the dashboard (shared by the cloud and the touchscreen)
```

Research prototype. Not a medical device.
