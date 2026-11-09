# ka-a

A local-first irrigation station for two bonsai trees, built in Python for a
Raspberry Pi 4. A responsive Spanish dashboard handles administration, individual
plant calibration, bounded watering requests, history, and emergency stop.

**Use Raspberry Pi OS Lite 64-bit.** The dashboard opens in a browser on your
computer or phone; the Pi needs no desktop environment. A custom OS image adds
maintenance without improving this first version. The project supplies application
services and an installer instead of a new Linux distribution.

## What is included

- FastAPI administration server, SQLite storage, and a separate single-owner
  actuator process. No Node.js, Redis, Docker, or external database is required.
- Two individual juniper profiles, with calibration and automatic watering disabled
  initially. A configurable daily water budget, dose/runtime limits, fresh sensor
  checks, cooldown, and permitted hours protect each plant.
- Persistent command deduplication, conservative water reservations, safe restart
  behavior, normally-off GPIO outputs, latched emergency stop, and session/CSRF
  protection. A lost browser connection does not own the pump runtime.
- Real ADS1115 analog-soil, SHT31 environmental, GPIO motor, and normally-closed
  safety-loop adapters, behind two explicit hardware opt-ins.
- Clearly labeled simulation, including calibration examples and leak injection.
- Optional AWS IoT Core certificate-authenticated telemetry with a bounded durable
  outbox. AWS is disabled by default; it has no remote actuation permissions.
- Raspberry Pi systemd units, wiring/commissioning documentation, and browser tests.

**Current validation is local simulation on macOS.** The GPIO adapter, Pi OS
installer, actual water delivery, and live AWS still need target-device verification.
Software shutdown limits do not replace an independent electrical timeout or a
physical pump-power switch. See [validation](docs/VALIDATION.md).

## Try the dashboard locally

Requires Python 3.11 or newer on macOS or Linux.

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt -e '.[dev,aws]'
.venv/bin/kaa setup
.venv/bin/kaa demo
```

Open **http://127.0.0.1:8080** and use the password you chose. The simulator starts
disarmed, with unconfirmed calibration. In **Estación → Probar la estación**, the
example-calibration button enables safe experimentation. Return to **Mi jardín**,
enable watering, and request a dose. **Parada de emergencia** remains latched until
explicitly released. Demo values are test fixtures, not horticultural instructions.

The `data/` directory is private and gitignored. To keep multiple environments
separate, set `KAA_DATA_DIR` to another directory. `kaa demo` refuses hardware mode.

For explicit configuration:

```bash
cp config.example.yaml config.local.yaml
.venv/bin/kaa --config config.local.yaml setup
.venv/bin/kaa --config config.local.yaml demo
```

## Install on the Raspberry Pi

Follow [the Raspberry Pi guide](docs/RASPBERRY_PI.md). Install OS Lite with the
official Raspberry Pi Imager, configure SSH/Wi-Fi, and install the application.
The installer defaults to simulation and does not start services or energize pumps.

```bash
sudo bash scripts/install-pi.sh
sudo -u kaa /opt/kaa/.venv/bin/kaa --config /etc/kaa/config.yaml setup
sudo systemctl enable --now kaa-controller kaa-web
```

The default server binds to loopback. Use an SSH tunnel first:

```bash
ssh -L 8080:127.0.0.1:8080 YOUR_PI_USER@YOUR_PI_HOST
```

Then open http://127.0.0.1:8080 on your computer. The Pi guide documents explicit
trusted-LAN access for phones and the separate real-hardware commissioning steps.

## Project map

| Path | Responsibility |
| --- | --- |
| `src/kaa/domain.py` | Safety decisions and relative moisture calibration |
| `src/kaa/store.py` | SQLite commands, profiles, sessions, readings, audit |
| `src/kaa/controller.py` | Exclusive actuator ownership and control loop |
| `src/kaa/hardware.py` | Simulator and real Pi adapter |
| `src/kaa/web.py`, `static/` | API, authentication, responsive dashboard |
| `src/kaa/cloud.py` | Optional outbound-only AWS telemetry |
| `deploy/`, `scripts/` | Target-device installation and systemd services |
| `tests/`, `qa/` | Domain/integration and real-browser verification |
| `specs/` | Outcomes, guardrails, acceptance criteria |

## Validate changes

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests qa
.venv/bin/ruff format --check src tests qa
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest qa/test_browser.py -q
```

Browser tests create disposable simulation servers and local data. Screenshots go
to ignored `artifacts/`. Never aim tests at a deployed station or real pumps.
`constraints.txt` records the validated Python environment; platform-specific
hardware dependencies remain subject to the Pi installation check.

## Confirmed scope and open installation decisions

The station is intended for two junipers, approximately 10 and 7 years old, on an
outdoor sheltered balcony with no direct sunlight. Each pot footprint is about
30 x 30 cm and total weight about 10-15 kg. The 80 x 40 cm shelf is sourced locally;
anchors and supports require on-site load verification. The Raspberry Pi already
exists. Hardware budget is USD 150-300; structure, software, and cloud costs are
outside that hardware budget. [Hardware notes](docs/HARDWARE.md) preserve the BOM.

Substrate depth, probe fit, species/cultivar, actual flow, daily water needs, and
light adequacy still need measurement. Being outdoors does not prove that this
shaded corner provides enough light. Grow-light electrical control, automatic
foliar misting, cameras, remote cloud commands, and unattended plant operation are
not implemented in this version. Never connect a mains lamp directly to GPIO.

No AWS resources are provisioned. [AWS setup](docs/AWS.md) is optional future work.
