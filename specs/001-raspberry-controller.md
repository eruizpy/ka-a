# Raspberry Pi controller and administration dashboard

## Outcome and baseline

Build ka-a for two outdoor junipers (approximately 10 and 7 years old) on a sheltered
balcony with no direct sun. The Raspberry Pi 4 already exists; the repository starts
with a license only. OS selection is Raspberry Pi OS Lite 64-bit, with a Python
application and a browser dashboard. Do not create or flash a custom OS image.

Each pot is approximately 30 x 30 cm, 10-15 kg including its tree. Reported heights
45 cm and 30 cm include the trees, not substrate depth. A proposed 80 x 40 cm shelf
is procured locally. Sensor fit, true substrate depth, calibrated water quantities,
light adequacy, and bracket/anchor load verification remain installation decisions.
No amount or humidity threshold in a demo is a horticultural prescription.

## Success signals

- A documented install on OS Lite runs the API/dashboard and controller as separate
  systemd services; the dashboard needs no desktop environment or Node runtime.
- The operator can log in, inspect both plants and actual controller status,
  calibrate profiles, arm/disarm control, request bounded watering, view history,
  and latch an emergency stop from a responsive Spanish interface.
- A simulated end-to-end flow demonstrates these operations without GPIO access.
- Hardware mode has a concrete ADS1115/SHT31/GPIO implementation, explicit enable
  gates, and a wiring/commissioning procedure; real-device verification is separate.
- Optional AWS IoT Core telemetry uses certificate authentication and durable
  delivery; loss of Internet never blocks the local controller.

## Guardrails and acceptance criteria

1. Default to simulation, disarmed control, unconfirmed calibration, and disabled
   automatic watering. Hardware requires explicit local configuration and an
   independent environment opt-in on a supported Pi host.
2. Only the single controller process owns actuators. The web app writes commands
   to SQLite. A process lock prevents two controllers for the same database.
3. Persist commands and their water reservation before operating a pump. Validate
   positive volume, calibration, current readings, controller heartbeat, daily
   budget, minimum interval, tank state, leak state, and maximum runtime at enqueue
   and again before execution. In-flight reservations count against budgets.
4. Idempotency keys survive restart. Reusing a key with another payload is refused.
   Expired or interrupted commands never replay; reboot disarms the controller and
   conservatively accounts for water that might have been delivered.
5. Emergency stop is latched, disarms control, cancels queued work, and is checked
   throughout pumping. Stop release requires explicit operator action with safe
   sensors. Sensor/read errors force outputs off and require operator recovery.
6. Session cookies are HttpOnly/SameSite, passwords use scrypt, write requests have
   CSRF and same-origin checks, and all operational routes require authentication.
   Bind to loopback by default; LAN access is explicit. No public Internet exposure.
7. Persisted telemetry is bounded. UI labels distinguish simulation, missing data,
   unconfirmed calibration, faults, stale readings, and unverified AWS connectivity.
8. Nothing in development connects to real equipment, provisions AWS, publishes a
   package, modifies VISEP, or claims Pi/electrical/plant commissioning is complete.

## Test plan (RED -> GREEN -> REFACTOR)

Write tests before implementation for authentication/CSRF, profile validation,
watering boundaries and concurrent budgets, persistent deduplication, stale
sensors, boot recovery, emergency stop during pumping, driver failure, and offline
cloud behavior. Run pytest with temporary SQLite databases and simulated/fake
drivers. Run Playwright against a disposable local instance for login, profile
editing, watering, emergency stop, re-login, and mobile layout. Record initial
RED failure and final commands/results in docs/VALIDATION.md. Exercise shell syntax
and package builds; record that systemd, GPIO/I2C, physical delivery, actual species
needs, and live AWS cannot be certified on the development Mac.

## Risks and recovery

Software limits are not an independent electrical cutoff. Require normally-off
drivers, appropriate motor protection, fuses, an accessible pump-power switch,
proper 3.3 V inputs, leak containment, and supervised water-only commissioning.
Use an external runtime cutoff for unattended physical use. A raised shelf and a
nearby socket do not prove installation safety. A shaded outdoor balcony does not
prove sufficient plant light; assess at foliage height before selecting a grow light.
Disarm before changing hardware or configuration. A restart must not resume a dose.
