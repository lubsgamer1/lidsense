# LidSense Raspberry Pi 5 Setup Guide

This guide takes you from a blank SD card to a running system. At the end the Pi starts by itself, takes a hydration reading every 10 seconds from the NanoVNA, and shows it on the 5" touchscreen. It also uploads each reading to a MySQL database: you can browse the data in phpMyAdmin and see it on a password-protected web dashboard. Allow about 2–3 hours the first time.

Work through the steps in order. Commands go in the Pi's **Terminal**, or in an SSH window from your laptop. Type them exactly, one line at a time. Lines starting with `#` are comments; you don't need to type them.

## What you need

| Item | Notes |
| --- | --- |
| Raspberry Pi 5 (4 GB or 8 GB) | In the 3D-printed case, with the active cooler fitted |
| Official 27 W USB-C power supply (5 V / 5 A) | On a 3 A supply, all USB ports together are limited to 600 mA. That is not enough for the NanoVNA plus the display |
| microSD card, 32 GB or larger, A2 rated | |
| SD card reader for your laptop | |
| 5" touchscreen and its cable | HDMI or DSI |
| NanoVNA V2 and USB cable | Fit a clip-on ferrite to the USB cable if you have one |
| Patch biosensor and a short SMA coax cable | Plus the Short, Open and Load calibration standards |
| USB keyboard and mouse | Only needed for the first boot |
| A laptop | Windows, macOS or Linux |
| Release files | `lidsense-v2.zip` (for the Pi) and `lidsense-web-upload.zip` (for the web host). Build them with `./make_release.sh` or download them from the repository's Releases page |

Have these ready:
- your Wi-Fi name and password. Avoid networks that make you sign in on a web page first.
- your Hostinger hPanel login.
- somewhere safe to record the Pi password, the database password, the device API key and the dashboard password.

## Step 1: Flash Raspberry Pi OS to the SD card

Use Raspberry Pi Imager 2.0 to write **Raspberry Pi OS (64-bit)** to the card. The current release is based on Debian 13 "Trixie".

1. Install Raspberry Pi Imager from <https://www.raspberrypi.com/software/> and open it.
2. Insert the microSD card. Everything on it will be erased.
3. **Device:** Raspberry Pi 5.
4. **Operating system:** Raspberry Pi OS (64-bit), the version with the desktop. Don't choose "Lite".
5. **Storage:** your SD card. Check that the size matches, so you don't wipe a different drive.
6. **Customisation:**
   - **Hostname:** `lidsense-01`
   - **Location:** London
   - **User:** your own username, for example `innocent`, and a strong password. **Do not use `lidsense`**: the installer creates a system account with that name.
   - **Wireless LAN:** your Wi-Fi name and password
   - **Remote access:** turn SSH on
   - **Raspberry Pi Connect:** optional
7. **Write:** this takes 5–15 minutes. Eject the card when Imager says it has finished.

## Step 2: Assemble the hardware and boot

1. With the power off, insert the card into the slot on the underside of the Pi.
2. Fit the active cooler, with its cable plugged into the FAN header, and close the case.
3. Connect the touchscreen. For HDMI, use **HDMI0**, the port next to the USB-C power socket. If the screen has a separate touch USB lead, plug that in too.
4. Plug in a keyboard and mouse. **Leave the NanoVNA unplugged** until Step 6.
5. Plug in the 27 W power supply. The first boot takes 2–5 minutes and may restart once.

## Step 3: First login, updates and remote access

Open the Terminal on the Pi, or connect from your laptop with SSH:

```
ssh innocent@lidsense-01.local
```

Then update the system and restart:

```
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

After the restart, check the basics:

```
hostname -I              # the Pi's IP address
timedatectl              # should show "System clock synchronized: yes"
vcgencmd get_throttled   # throttled=0x0 means power and cooling are fine
```

Optional: run `sudo raspi-config` and set **Display → Screen blanking: off** and **System → Auto login: Desktop autologin**.

## Step 4: Set up the database and web dashboard (Hostinger)

### 4.1 Create the database
1. In hPanel go to **Websites → Manage → Databases → Management**.
2. Create a new database and database user with a strong password. Write down the full names hPanel shows (they look like `u…_lidsense`) and the password.
3. Change the password of the old database used by `ghg.py`: it is exposed in that file.

### 4.2 Upload the web folder
1. Open hPanel → **Files → File Manager** → `public_html`.
2. Upload `lidsense-web-upload.zip`, right-click it, choose **Extract**, then delete the zip. You should now have `public_html/lidsense/`.
3. Check that SSL is active: hPanel → **Security → SSL**.

### 4.3 Create config.php
1. In `public_html/lidsense/api/`, copy `config.sample.php` and name the copy `config.php`.
2. Fill in `db_host` (`localhost`), `db_name`, `db_user` and `db_pass`.
3. Set `setup_token` to a long random string.

### 4.4 Run the setup page
Open `https://YOUR-DOMAIN/lidsense/setup.php?token=YOUR-SETUP-TOKEN` and do the following:
1. Click **Create tables**.
2. **Register a Raspberry Pi** with device ID `lidsense-01`, then copy the `LIDSENSE_API_KEY=…` line it shows. The key is shown only once.
3. **Create a dashboard login.** Paste the line it gives you into the `'users'` list in `config.php`.
4. Set `'setup_token' => ''` in `config.php`. This switches the setup page off.

### 4.5 Check
- `https://YOUR-DOMAIN/lidsense/` shows the sign-in page, and your login works.
- In phpMyAdmin, the new database has the tables `alerts`, `baselines`, `devices`, `readings` and `sweeps`, plus the view `v_readings`.

## Step 5: Install LidSense on the Pi

Copy the release file from your laptop to the Pi:

```
scp lidsense-v2.zip innocent@lidsense-01.local:~
```

Or clone the repository directly on the Pi:

```
git clone https://github.com/YOUR-ACCOUNT/lidsense.git
```

Then, on the Pi:

```
cd ~
unzip lidsense-v2.zip      # skip this line if you used git clone
cd lidsense
sudo bash pi/install.sh
```

Next, open the settings file:

```
sudo nano /etc/lidsense/config.yaml
```

Set these two lines:
- `device_id: lidsense-01`
- `ingest_url: https://YOUR-DOMAIN/lidsense/api/ingest.php`

Then open the secrets file:

```
sudo nano /etc/lidsense/secrets.env
```

Replace its contents with the `LIDSENSE_API_KEY=…` line from Step 4.4.

If this card ran the old system before, remove any `boot.sh`, `auto_run.sh` or ngrok entries from `crontab -e`, `sudo crontab -e` and `/etc/rc.local`.

## Step 6: Connect the NanoVNA and calibrate

1. Connect the sensor coax to **PORT 1 (CH0)** and the NanoVNA to a USB port on the Pi. Switch the NanoVNA on.
2. Run `ls -l /dev/nanovna`. It should show `-> ttyACM0`.
3. Calibrate:

```
sudo systemctl stop lidsense
cd /opt/lidsense/pi
sudo -u lidsense python3 -m lidsense.calibrate --config /etc/lidsense/config.yaml
```

When asked, connect SHORT, then OPEN, then LOAD at the end of the coax, pressing Enter after each one. You should see "Good calibration" (return loss above 30 dB).

4. Test a reading with your wrist on the sensor:

```
sudo -u lidsense python3 -m lidsense.calibrate --config /etc/lidsense/config.yaml --check
```

You should see a resonance around 2.2–2.3 GHz and `edge=False`.

Optional, for better resolution: set the sweep to 2.0e+9 – 2.5e+9 Hz with 201 points, then calibrate again.

## Step 7: Start LidSense and run the first session

```
sudo systemctl start lidsense
systemctl status lidsense
journalctl -u lidsense -f
sudo reboot      # the touchscreen opens the dashboard after the reboot
```

On the touchscreen:
1. Lift the sensor clear of the skin and tap **Record free-air**.
2. Enter a participant code, for example `P01`, and tap **Set**.
3. With the participant's wrist still on the sensor and the participant well hydrated, tap **Capture baseline**. Wait about a minute.
4. Monitoring now runs on its own.

You can view the data remotely at `https://YOUR-DOMAIN/lidsense/`. The raw data is in phpMyAdmin, in the `v_readings` view.

## Step 8: End-to-end check

- [ ] `vcgencmd get_throttled` shows `throttled=0x0`
- [ ] `ls -l /dev/nanovna` shows the NanoVNA
- [ ] The calibration reported "Good calibration"
- [ ] `systemctl status lidsense` shows "active (running)"
- [ ] The touchscreen opens the dashboard after a reboot
- [ ] With the sensor in the air, the screen shows "Not on skin"
- [ ] With a wrist on the sensor, a status appears within about 20 seconds
- [ ] The web dashboard shows the device as **online**
- [ ] New rows appear in the `readings` table in phpMyAdmin
- [ ] After turning Wi-Fi off for 2 minutes, the queued readings upload without gaps once it's back on

## Everyday use and maintenance

| Task | How |
| --- | --- |
| Shut down | `sudo shutdown now`, then wait for the green LED to stop flashing |
| New participant | Set the participant code, then tap **Capture baseline** |
| Change settings | Edit `/etc/lidsense/config.yaml`, then run `sudo systemctl restart lidsense` |
| Recalibrate | Repeat Step 6 after any change to the cable, connectors or sweep |
| Update the OS | `sudo apt update && sudo apt full-upgrade -y && sudo reboot` |
| Update LidSense | `cd ~/lidsense && git pull && sudo bash pi/install.sh`. Your config, API key, calibration and data are kept |
| Back up | phpMyAdmin → Export (SQL). On the Pi, copy `/var/lib/lidsense/lidsense.sqlite` and `/opt/lidsense/pi/data/` |

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Black screen | Use HDMI0, or re-flash the card |
| `lidsense-01.local` not found | Use the IP address from `hostname -I` instead |
| `get_throttled` is not `0x0` | Use the 27 W supply and check that the fan is running |
| `/dev/nanovna` missing | Switch the NanoVNA on and try another cable. `lsusb` should list `04b4:0008` |
| Log says "Calibration grid does not match" | Recalibrate (Step 6) |
| Log says "LIDSENSE_API_KEY is not set" | Fill in `/etc/lidsense/secrets.env`, then restart the service |
| "Waiting to upload" keeps rising | Check the internet connection, `ingest_url` and the API key (HTTP 403 means the key is wrong) |
| Web dashboard shows "offline" | Run `systemctl status lidsense` on the Pi |
| Web page shows "database error" | Check the database settings in `config.php` |
| Screen always shows "Not on skin" | Lift the sensor clear and record free-air again |
| Kiosk doesn't open | Turn on desktop autologin, and check that `~/.config/labwc/autostart` contains the lidsense line |

### Useful commands
```
sudo systemctl start|stop|restart lidsense
systemctl status lidsense
journalctl -u lidsense -f
sudo nano /etc/lidsense/config.yaml
ls -l /dev/nanovna
vcgencmd get_throttled
hostname -I
sudo shutdown now
```

### Where things live on the Pi
| Path | Contents |
| --- | --- |
| `/etc/lidsense/config.yaml` | Settings |
| `/etc/lidsense/secrets.env` | Device API key |
| `/opt/lidsense/` | Program and dashboard |
| `/opt/lidsense/pi/data/` | Calibration files |
| `/var/lib/lidsense/lidsense.sqlite` | Local readings and the upload queue |
