# Hardware, placement, and wiring contract

## Confirmed project context

- Two junipers, approximately 10 and 7 years old.
- Pot footprints about 30 x 30 cm; total tree + pot weights about 10-15 kg each.
- Reported heights 45 cm and 30 cm include the plants, not substrate depth.
- Sheltered outdoor balcony, no direct rain, little wind, and no direct sunlight.
- Proposed shelf: **80 cm wide x 40 cm usable depth**, fully inside the balcony.
  Elevate foliage into the open sky view. Brackets, concrete anchors, substrate
  capacity, drainage, and fall restraint are sourced and verified locally.
- Pi 4 and 3D printer already exist. Structure, software, and AWS costs are excluded
  from the requested USD 150-300 hardware budget.

Being outdoors does not establish adequate juniper illumination. Assess light at
foliage height before selecting supplemental full-spectrum LEDs. No UV lamp is
required by this project. The first version does not switch a mains lamp or spray
foliage automatically. See [juniper care](https://www.bonsaiempire.com/tree-species/juniper).

## Procurement baseline (not a confirmed Amazon cart)

| Quantity | Component / specification | Implementation |
| --- | --- | --- |
| 2 | Protected capacitive analog probes, reference DFRobot SEN0308 | ADS1115 channels A0/A1, readings in mV |
| 1 | ADS1115, 3.3 V I2C breakout | Default address `0x48` |
| 1 | SHT31 outdoor-compatible breakout/probe, 3.3 V logic | Default address `0x44` |
| 2 | 12 V peristaltic pumps, replaceable silicone pump tubing | One independent normally-off channel per pot |
| 2 | Motor-rated, active-high 3.3 V logic MOSFET drivers | Flyback protection, correct current rating, off-state pull-down |
| 1 | Regulated 12 V supply, capacity chosen for motor startup current | Separate from the Pi USB-C supply; locally appropriate mains rating |
| 1 | Tank float with a voltage-free closed contact while water is sufficient | Opening/disconnection blocks watering |
| 1 | Leak detector with a fail-safe voltage-free contact loop, closed only when safe | Opening/disconnection stops watering |
| 1 set | Silicone tubing, fittings, open outlets, and tube retention | Match actual pump tube dimensions; avoid pressure-compensated emitters |
| 1 | Opaque covered reservoir, starting capacity about 5 L | Below outlet height; verify absence of siphoning |
| 1 set | Drain trays, enclosure, cable glands, terminals, fuses, pump-power switch | Keep water separate from electronics |
| 1 per pump | Independent electrical maximum-runtime cutoff | Required before unattended physical operation; not a software timer |

The SEN0308 is 175 x 30 mm. **Check usable substrate depth and roots before buying**;
do not force it into a shallow bonsai pot. If an appropriate protected analog probe
does not fit or its response is unstable in coarse substrate, select another sensor
and adapt the driver before deployment. Weight sensing is a possible later addition,
not implemented. Calibration is a relative index, not certified volumetric water content.

Do not substitute a generic exposed leak PCB with an unknown 5 V analog/digital
output into the safety input. Select/condition its interface to satisfy the
normally-closed dry-contact contract below. The detector's relay must fail open
when it loses power; verify the actual product behavior on the bench.

Reference documentation: [SEN0308](https://wiki.dfrobot.com/sen0308),
[current ADS1x15 API](https://docs.circuitpython.org/projects/ads1x15/en/latest/examples.html),
[GPIO Zero outputs](https://gpiozero.readthedocs.io/en/stable/api_output.html), and
[Raspberry Pi GPIO](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).

## Low-voltage pin map (BCM numbering)

| Function | BCM | Physical header pin |
| --- | --- | --- |
| I2C SDA | GPIO2 | 3 |
| I2C SCL | GPIO3 | 5 |
| 3.3 V sensor/logic supply | — | 1 |
| Ground reference | — | 6 (or another verified GND pin) |
| Pump 1 driver input | GPIO17 | 11 |
| Pump 2 driver input | GPIO27 | 13 |
| Tank-good contact input | GPIO22 | 15 |
| Leak-clear contact input | GPIO23 | 16 |

Power ADS1115, its I2C pull-ups, and compatible sensors at 3.3 V. SEN0308 nominal
output is 0-2.9 V; connect each signal to its own ADC channel and common signal
ground. The adapter expects the ADS1x15 v3 `Pin.A0`/`Pin.A1` API. Keep I2C wiring
short and route motor power separately from sensor wiring.

Each safety loop connects its GPIO input to GND when safe. GPIO Zero enables a
pull-up and interprets a closed loop as active. Tank-good is therefore `is_active`;
leak alarm is `not leak_clear.is_active`. Open wire, unplugged connector, low water,
or an alarm must produce the unsafe state. Verify both loops before pump power.

The two motor-driver inputs are active-high and created with `initial_value=False`.
Use drivers with a physical pull-down/default-off state through boot, loss of Pi
power, and loss of the GPIO connection. Pumps run from their fused 12 V supply;
GPIO carries control only. Wire the reference ground as required by the selected
driver, or follow its isolation specification. Do not use active-low relay boards
with this profile. Never connect 12 V, 5 V logic, or mains to a GPIO pin.

The 3D printer can make sensor clips, tube holders, a ventilated sensor shield,
and low-load mounting accessories. Do not use an unverified print as the primary
support for the two heavy pots or assume an enclosure print is watertight.
