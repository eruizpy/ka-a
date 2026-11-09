# Raspberry Pi installation and commissioning

## Base OS

Use the current **Raspberry Pi OS Lite 64-bit** image from the official Raspberry Pi
Imager. It supports headless operation on Raspberry Pi 4. Choose the current stable
image, not an old image copied into this repository. Python 3.11+ is required.

Official sources: [OS images](https://www.raspberrypi.com/software/operating-systems/)
and [Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/os.html).

Configure your own hostname, SSH user/key, Wi-Fi, and correct wireless country in
Imager. No device or Wi-Fi credentials are supplied here. A 32 GB or larger
high-endurance microSD is a practical starting point. Use the Pi's separate 5 V/3 A
USB-C supply; the pump supply is a different circuit.

The application is a layer on OS Lite, not a custom OS. For a reproducible image
later, automate this same installation with pi-gen after target validation. OTA
images, A/B boot, and OS flashing are outside version 0.1.

## Install the application

On the Pi, from a checkout of this repository:

```bash
python3 --version
sudo bash scripts/install-pi.sh
sudo -u kaa /opt/kaa/.venv/bin/kaa --config /etc/kaa/config.yaml setup
sudo systemctl enable --now kaa-controller kaa-web
sudo systemctl status kaa-controller kaa-web
```

The script installs Python dependencies, the `kaa` system user, files under
`/opt/kaa`, `/etc/kaa`, and `/var/lib/kaa`, and the two service definitions. It does
not start services, flash storage, enable GPIO actuation, or overwrite an existing
configuration. The services start in **simulation** after you explicitly start them.

Check `/healthz` and the dashboard through an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 YOUR_PI_USER@YOUR_PI_HOST
```

Open http://127.0.0.1:8080 locally. Log in with the password you chose during setup.
The web process has no access to device nodes. Only the controller has GPIO/I2C
permissions. The application does not run as root.

## Explicit LAN access from a phone

On your trusted home network, edit `/etc/kaa/config.yaml` as an administrator:

```yaml
host: 0.0.0.0
allowed_hosts:
  - localhost
  - 127.0.0.1
  - kaa.local
  - 192.168.1.50  # Replace with the actual reserved address of your Pi.
```

Restart `kaa-web` and open `http://kaa.local:8080` or the configured IP. The DHCP
reservation, hostname resolution, and firewall are network installation steps,
not features the app silently configures. HTTP on a shared LAN does not encrypt
the login; use the SSH tunnel or configure HTTPS for a stronger deployment.
Never forward port 8080 to the public Internet.

If you add a separately managed HTTPS reverse proxy, keep the app on loopback,
include the exact hostname in `allowed_hosts`, set `secure_cookie: true`, and set
`public_origin: https://YOUR_HOSTNAME` without a trailing slash. The app does not
trust arbitrary forwarded headers. It requires same-origin writes and CSRF tokens.
TLS certificate provisioning is not included in this installer.

## Enable real hardware only after bench verification

1. Keep pump power disconnected. Verify [the wiring](HARDWARE.md), driver polarity,
   normally-closed safety loops, fuses, independent cutoff, and containment.
2. Enable I2C with `sudo raspi-config` → Interface Options → I2C, then reboot if
   requested. Check `/dev/i2c-1`, `/dev/gpiochip0`, and `i2cdetect -y 1`.
3. Stop both services. Change `mode: raspberry` and `hardware_enabled: true` in
   `/etc/kaa/config.yaml`; set `KAA_ENABLE_HARDWARE=YES` in `/etc/kaa/environment`.
   These are separate opt-ins. Do not put the opt-in into generic developer shells.
4. Start the controller with pump power still disconnected. Correct any sensor or
   safety-loop error before continuing. An open/disconnected safety loop is unsafe.
5. Start the web service. Switching from simulation invalidates every stored sensor
   and flow confirmation, disables automatic watering, and removes simulated readings.
6. Calibrate probes in the actual substrate and measure pump flow into a graduated
   container on an independently switched water-only bench. Do not energize a motor
   from a GPIO pin to obtain this measurement. Keep any manual bench supply bounded
   by an independent timer and accessible disconnect.
7. Set the measured dry/drained-wet millivolt readings and flow for each plant.
   Confirm them in the UI. Set event volume, daily budget, interval, and schedule
   from observed needs; the initial values are deliberately unconfirmed test values.
8. With trays in place, reconnect pump power and request one small supervised dose.
   Verify delivered volume, distribution, drainage, and stopping behavior.
9. Test leak detection, tank-empty detection, network loss, service stop/restart, and
   physical cutoff. A controller restart always disarms; someone must explicitly
   enable it again. A lost/incomplete dose is not resumed.
10. Automatic mode is a separate per-plant switch. It needs three low readings,
    valid calibration, allowed hours, and all global/plant safety checks. Do not
    enable unattended operation before completing the physical acceptance record.

Software checks emergency-stop state approximately every 100 ms while executing a
dose, subject to OS scheduling and blocking I/O. This is **not a real-time safety
guarantee**. A stuck process, failed GPIO transistor, or physical siphon can bypass
software. Use independent hardware protection and supervised commissioning.

## Daily operation and recovery

```bash
sudo journalctl -u kaa-controller -u kaa-web -n 100 --no-pager
sudo -u kaa /opt/kaa/.venv/bin/kaa --config /etc/kaa/config.yaml doctor
sudo systemctl stop kaa-controller
```

Stop pump power physically before servicing wiring. After a fault, correct it,
observe fresh safe readings, release the dashboard stop, then explicitly enable
watering. Releasing the stop never enables watering automatically.

Profiles, sessions, readings, command IDs, water reservations, and the telemetry
outbox live in `/var/lib/kaa/kaa.sqlite3`. Do not replace the live database with a
demo database. An interrupted dose retains its full reserved volume in the daily
budget because actual delivery is uncertain. The UI labels it reserved, not measured.

For a consistent local maintenance copy, stop the controller and web service before
copying the SQLite database and any WAL/SHM files, or use SQLite's online backup API.

For application updates, stop both services and disconnect pump power, retain the
prior source revision, rerun the installer from a reviewed revision, and recheck
simulation/real configuration before restarting. Version 0.1 has no automated OTA
or downgrade mechanism; database migrations require separate review.
