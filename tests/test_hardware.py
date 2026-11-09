import sys
from types import ModuleType, SimpleNamespace

import pytest

from kaa.config import Settings
from kaa.hardware import RaspberryHardware


def test_concrete_adapter_uses_v3_adc_and_normally_closed_safety_loops(monkeypatch):
    monkeypatch.setattr("kaa.hardware.check_hardware_opt_in", lambda settings: None)
    outputs, inputs = [], []

    class Output:
        def __init__(self, pin, **kwargs):
            assert kwargs["active_high"] is True
            assert kwargs["initial_value"] is False
            self.value = False
            self.closed = False
            outputs.append(self)

        def on(self):
            self.value = True

        def off(self):
            self.value = False

        def close(self):
            self.closed = True

    class Input:
        def __init__(self, pin, **kwargs):
            assert kwargs["pull_up"] is True
            self.is_active = True
            inputs.append(self)

        def close(self):
            pass

    class Factory:
        def __init__(self, **kwargs):
            pass

        def close(self):
            pass

    def module(name, **attrs):
        value = ModuleType(name)
        for key, attr in attrs.items():
            setattr(value, key, attr)
        monkeypatch.setitem(sys.modules, name, value)

    module("board", SCL=1, SDA=2)
    module("busio", I2C=lambda *args: SimpleNamespace(deinit=lambda: None))
    module(
        "adafruit_ads1x15",
        ADS1115=lambda *args, **kwargs: object(),
        AnalogIn=lambda adc, channel: SimpleNamespace(voltage=2.1 if channel == 0 else 1.9),
        ads1x15=SimpleNamespace(Pin=SimpleNamespace(A0=0, A1=1)),
    )
    module(
        "adafruit_sht31d",
        SHT31D=lambda *args, **kwargs: SimpleNamespace(temperature=25.0, relative_humidity=60.0),
    )
    module("gpiozero", DigitalInputDevice=Input, OutputDevice=Output)
    module("gpiozero.pins")
    module("gpiozero.pins.lgpio", LGPIOFactory=Factory)
    hardware = RaspberryHardware(Settings())
    assert hardware.read()["juniper-10"]["raw"] == 2100
    assert hardware.read()["juniper-10"]["tank_ok"] is True
    assert hardware.read()["juniper-10"]["leak"] is False
    inputs[1].is_active = False
    assert hardware.read()["juniper-10"]["leak"] is True
    hardware.on("juniper-10")
    assert outputs[0].value is True
    hardware.close()
    assert all(p.closed and not p.value for p in outputs)


def test_invalid_pin_assignments_refused():
    with pytest.raises(ValueError):
        Settings(pump_pins=[17, 17])
    with pytest.raises(ValueError):
        Settings(pump_pins=[2, 3])
