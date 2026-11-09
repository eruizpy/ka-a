"""Actuator adapters. Import Pi libraries only after all hardware enable gates pass."""

import math
import os
import platform


class SimulatedHardware:
    def __init__(self, store):
        self.store = store
        self.running = set()
        self.started_count = 0

    def read(self):
        state = self.store.simulation()
        return {
            plant_id: {
                "raw": raw,
                "temperature": 26.0,
                "humidity": 58.0,
                "tank_ok": state["tank_ok"],
                "leak": state["leak"],
            }
            for plant_id, raw in state["raw"].items()
        }

    def on(self, plant_id):
        self.running.add(plant_id)
        self.started_count += 1

    def off_all(self):
        self.running.clear()

    def delivered(self, plant_id, volume):
        state = self.store.simulation()
        # This deliberately simple simulator is not a soil/plant growth model.
        state["raw"][plant_id] = max(500, state["raw"][plant_id] - volume * 4)
        self.store.set_simulation(state)

    def close(self):
        self.off_all()


def check_hardware_opt_in(settings):
    if not settings.hardware_enabled or os.getenv("KAA_ENABLE_HARDWARE") != "YES":
        raise RuntimeError("Hardware requires hardware_enabled=true and KAA_ENABLE_HARDWARE=YES")
    if platform.system() != "Linux" or platform.machine() not in ("aarch64", "armv7l"):
        raise RuntimeError("Hardware mode requires a Raspberry Pi Linux host")
    try:
        from pathlib import Path

        model = Path("/proc/device-tree/model").read_text().strip("\x00")
    except OSError as exc:
        raise RuntimeError("Cannot verify Raspberry Pi model") from exc
    if "Raspberry Pi 4" not in model:
        raise RuntimeError("This wiring profile targets Raspberry Pi 4 only")


class RaspberryHardware:
    def __init__(self, settings):
        check_hardware_opt_in(settings)
        import adafruit_sht31d
        import board
        import busio
        from adafruit_ads1x15 import ADS1115, AnalogIn, ads1x15
        from gpiozero import DigitalInputDevice, OutputDevice
        from gpiozero.pins.lgpio import LGPIOFactory

        self.pumps = {}
        self.inputs = []
        self.i2c = None
        self.factory = LGPIOFactory(chip=settings.gpio_chip)
        try:
            for plant_id, pin in zip(("juniper-10", "juniper-7"), settings.pump_pins, strict=True):
                self.pumps[plant_id] = OutputDevice(
                    pin, active_high=True, initial_value=False, pin_factory=self.factory
                )
            self.tank = DigitalInputDevice(
                settings.tank_ok_pin, pull_up=True, pin_factory=self.factory
            )
            self.inputs.append(self.tank)
            self.leak_clear = DigitalInputDevice(
                settings.leak_clear_pin, pull_up=True, pin_factory=self.factory
            )
            self.inputs.append(self.leak_clear)
            self.i2c = busio.I2C(board.SCL, board.SDA)
            adc = ADS1115(self.i2c, address=settings.adc_address, gain=1)
            self.channels = {
                "juniper-10": AnalogIn(adc, ads1x15.Pin.A0),
                "juniper-7": AnalogIn(adc, ads1x15.Pin.A1),
            }
            self.environment = adafruit_sht31d.SHT31D(self.i2c, address=settings.sht31_address)
        except BaseException:
            self.close()
            raise

    def read(self):
        temperature = float(self.environment.temperature)
        humidity = float(self.environment.relative_humidity)
        result = {}
        for plant_id, channel in self.channels.items():
            raw = float(channel.voltage) * 1000
            if not all(math.isfinite(v) for v in (raw, temperature, humidity)):
                raise OSError("Non-finite sensor reading")
            if not 0 <= raw <= 3300 or not -30 <= temperature <= 70 or not 0 <= humidity <= 100:
                raise OSError("Sensor reading out of bounds")
            # Normally-closed, voltage-free safety loops: opening either is unsafe.
            result[plant_id] = {
                "raw": raw,
                "temperature": temperature,
                "humidity": humidity,
                "tank_ok": self.tank.is_active,
                "leak": not self.leak_clear.is_active,
            }
        return result

    def on(self, plant_id):
        self.pumps[plant_id].on()

    def off_all(self):
        failures = []
        for pump in self.pumps.values():
            try:
                pump.off()
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise OSError("Cannot confirm pump shutdown") from failures[0]

    def delivered(self, plant_id, volume):
        pass

    def close(self):
        try:
            self.off_all()
        finally:
            for device in [*self.pumps.values(), *self.inputs]:
                device.close()
            if self.i2c is not None:
                self.i2c.deinit()
            self.factory.close()


def build_hardware(settings, store):
    if settings.mode == "simulation":
        return SimulatedHardware(store)
    return RaspberryHardware(settings)
