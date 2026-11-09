import pytest

from kaa.config import Settings
from kaa.controller import Controller
from kaa.hardware import SimulatedHardware
from kaa.store import Store


@pytest.fixture
def rig(tmp_path):
    settings = Settings(data_dir=tmp_path, sample_seconds=0.05)
    store = Store(settings)
    hardware = SimulatedHardware(store)
    controller = Controller(settings, store, hardware)
    controller.start()
    controller.sample()
    for plant in store.profiles():
        store.update_profile(
            plant["id"],
            {
                "dry_raw": 2500,
                "wet_raw": 1000,
                "calibration_confirmed": True,
                "flow_ml_min": 60,
                "flow_confirmed": True,
            },
            plant["revision"],
        )
    controller.sample()
    yield settings, store, hardware, controller
    controller.close()
