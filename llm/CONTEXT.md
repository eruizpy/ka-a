# ka-a project context

This is a navigation/context record. Implementation truth is in the linked source;
operational instructions and validation truth are in their respective documents.
Verify those sources before changing or asserting behavior.

## Owner decisions

- ka-a is independent of VISEP CRM and any sibling repositories.
- Python is the main stack. The base is Raspberry Pi OS Lite 64-bit on Raspberry
  Pi 4, with a browser dashboard rather than a custom OS/desktop image.
- Two junipers, approximately 10 and 7 years old. Pot footprints about 30 x 30 cm,
  total weights about 10-15 kg each; heights of 45 cm and 30 cm include the trees.
  Actual substrate depth and cultivar are not confirmed.
- Final location: sheltered outdoor balcony, no direct sunlight/rain, little wind.
  Foliage is to be elevated above the mureta. This does not prove adequate light;
  supplemental lighting remains conditional.
- Shelf: approximately 80 x 40 cm usable area, fully inside the balcony, fixed to
  concrete with locally selected, load-verified supports. Its fabrication and
  installation costs are local and excluded from the hardware shopping budget.
- Raspberry Pi 4 and 3D printer already exist. Hardware target: USD 150-300 through
  Amazon.com. Software and AWS costs are excluded for now.
- Start with individual substrate irrigation and monitoring. Automated foliar
  misting, lamp switching, cameras, and cloud actuator commands are not delivered.

## Implementation map

| Question                                    | Canonical source                                                                                  |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Stack, diagram, shopping, local start       | [README](../README.md)                                                                            |
| Dependencies, extras, CLI                   | [pyproject.toml](../pyproject.toml), [constraints.txt](../constraints.txt)                        |
| Routes, authentication, CSRF                | [web.py](../src/kaa/web.py)                                                                       |
| Calibration and safety rules                | [domain.py](../src/kaa/domain.py)                                                                 |
| Persistent commands, reservations, sessions | [store.py](../src/kaa/store.py)                                                                   |
| Actuator ownership and control loop         | [controller.py](../src/kaa/controller.py)                                                         |
| Simulator and GPIO/I2C adapter              | [hardware.py](../src/kaa/hardware.py)                                                             |
| CLI and simulator launch                    | [cli.py](../src/kaa/cli.py)                                                                       |
| Outbound MQTT and acknowledgements          | [cloud.py](../src/kaa/cloud.py), [AWS guide](../docs/AWS.md)                                      |
| Target-device setup                         | [Pi guide](../docs/RASPBERRY_PI.md), [installer](../scripts/install-pi.sh), [deploy/](../deploy/) |
| Wiring and compatibility                    | [hardware contract](../docs/HARDWARE.md)                                                          |
| Original feature acceptance                 | [spec 001](../specs/001-raspberry-controller.md)                                                  |
| Recorded checks and limits                  | [validation record](../docs/VALIDATION.md)                                                        |

## Boundaries to preserve

- Simulation, disarmed control, unconfirmed calibration, and disabled automatic
  watering are defaults. GPIO needs two local opt-ins and a verified Pi 4 host.
  Simulation confirmations do not transfer to hardware.
- The web process never owns pumps. The controller acquires a process lock and
  claims durable, bounded commands from SQLite.
- Emergency stop is latched; releasing it does not arm. Restarts do not resume
  doses. Interrupted water reservations remain conservative.
- Defaults are test values, not a watering recipe. Substrate response, flow, probe
  fit, water needs, independent cutoff, drainage, light, and support strength still
  require on-site acceptance.
- AWS is optional outbound telemetry only. No cloud resources are provisioned.
- The 2026-11-09 product record reports 39 Python tests and 4 browser flows on
  macOS. It does not certify real equipment or live AWS and must not be presented
  as a newly executed result in a later consultation.
