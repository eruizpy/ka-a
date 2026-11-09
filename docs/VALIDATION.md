# Local validation record

Date: 2026-11-09 (America/Asuncion). Version: 0.1.0.
Environment: macOS arm64, Python 3.11.15. All databases and browser stations used
temporary local data; no real plant, sensor, pump, Raspberry Pi, or AWS connection
was used. VISEP CRM was inspected for context and was not modified.

## Outcome delivered

Python controller/API, responsive Spanish dashboard, individual plant profiles,
relative sensor/flow calibration, manual/automatic dose scheduling, persistent
commands and conservative water reservations, latched stops, authentication/CSRF,
simulated hardware, guarded real-driver implementation, optional outbound AWS
telemetry, OS Lite installation script, and separate systemd service definitions.

## RED evidence and fixes

- Initial full collection failed because `kaa.web` did not yet exist; API contracts
  were written before the API implementation.
- The safety regression batch produced **4 failed, 5 passed**: clean shutdown still
  appeared online; a shutdown request did not interrupt a running dose; changing
  sensor calibration retained its confirmation; hardware construction was not
  guarded by the controller lock. Each behavior was corrected and rerun.
- The mode-transition regression failed because simulation calibration survived a
  switch to real mode. Switching modes now clears confirmations/automatic mode and
  removes simulated readings before operation.
- The day-boundary regression failed because a dose finishing after midnight was
  omitted from the new day's water budget. Queued/running reservations and doses
  finishing on the current day now count conservatively; cooldown starts at finish.
- The mobile browser regression failed because logout was hidden in the collapsed
  navigation. Logout is now accessible on phones and is exercised in the browser.
- Input-boundary tests exposed non-finite JSON causing a validation-response error
  and password validation echoing its input. The custom validation handler reports
  field/type metadata only, never user input.
- Early environment bootstrap selected system Python 3.9 and failed the Python
  requirement. The task-local environment was recreated explicitly with Python
  3.11; no global Python environment was changed. These were environment failures,
  not evidence of a passing product test.

## Passing checks

| Command / check | Recorded result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | 39 passed; one upstream Starlette/httpx deprecation warning |
| `make browser` | 4 Playwright/Chromium flows passed |
| `make check` | Ruff checks and format checks passed |
| `npx --yes prettier@3.6.2 --check src/kaa/static/app.css src/kaa/static/app.js src/kaa/static/index.html` | HTML/CSS/JS formatting passed |
| `.venv/bin/python -m pip check` | No broken requirements |
| `bash -n scripts/install-pi.sh` | Shell syntax passed |
| `.venv/bin/python -m pip wheel --no-deps --wheel-dir /private/tmp/ka-a-package-check .` | Wheel built; dashboard asset inclusion inspected |
| `.venv/bin/kaa doctor` | Simulation, hardware disabled, hardware opt-in false, cloud disabled |

Unit/integration coverage includes authentication/session revocation, origin and
CSRF checks, strict input validation without secret echo, profile revisions,
unconfirmed calibration, event/runtime/day limits, concurrent reservations,
persistent deduplication, expired commands, stale readings, leak/tank faults,
mid-dose stop/shutdown, restart accounting, controller exclusivity, mode changes,
automatic low-reading gating, concrete adapter contract with mocked devices, and
offline MQTT delivery/PUBACK with a bounded outbox.

Browser flows cover login/logout and profile persistence; calibration, a bounded
watering request, emergency stop and release; simulated leak and explicit recovery;
and responsive desktop/mobile layout plus the mobile profile dialog/logout. The HTTP
UUID fallback is exercised without `crypto.randomUUID` to support trusted-LAN HTTP.

Desktop/mobile screenshots were rendered and visually inspected. Local artifacts
are gitignored under `artifacts/`; plant illustrations are decorative SVGs and
simulated values are explicitly labeled. No stock photo represents either real tree.

## Verification limits and remaining acceptance

- Raspberry Pi OS installation, systemd execution, ARM dependency installation,
  GPIO/I2C electrical behavior, actual flow, sensor response, independent cutoff,
  siphoning, drainage, safe anchoring, and unattended operation remain unverified.
- Hardware unit tests use fake devices; they do not certify real equipment.
- AWS tests use a fake MQTT client. TLS against a live IoT endpoint, certificate
  provisioning, and AWS policies/resources have not been exercised or deployed.
- A shelf above the mureta does not prove adequate juniper light. Assess light,
  actual cultivar, substrate depth, probe fit, and plant water needs on site.
- Defaults are conservative test bounds. They are not a watering recipe for the
  two trees, and no operational calibration is supplied.
- LED switching, foliar misting, a custom OS image, remote cloud commands, and OTA
  updates are outside this version. No software or service has been installed on
  the user's Pi and no remote changes are part of this local delivery.
