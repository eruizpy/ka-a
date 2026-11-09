import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from kaa.controller import Controller
from kaa.domain import Refused
from kaa.hardware import SimulatedHardware


def dose(store, plant="juniper-10", volume=1, key=None):
    return store.enqueue(plant, volume, key or str(uuid.uuid4()))


def test_requires_explicit_arming(rig):
    _, store, _, _ = rig
    with pytest.raises(Refused, match="disarmed"):
        dose(store)


def test_persistent_idempotency_and_payload_conflict(rig):
    settings, store, _, _ = rig
    store.arm()
    key = str(uuid.uuid4())
    first = dose(store, key=key)
    assert dose(store, key=key)["id"] == first["id"]
    with pytest.raises(Refused, match="idempotency_conflict"):
        dose(store, volume=2, key=key)
    from kaa.store import Store

    assert dose(Store(settings), key=key)["id"] == first["id"]


def test_unconfirmed_calibration_refuses_watering(rig):
    _, store, _, _ = rig
    p = store.profile("juniper-10")
    store.update_profile(p["id"], {"calibration_confirmed": False}, p["revision"])
    store.arm()
    with pytest.raises(Refused, match="calibration_required"):
        dose(store)


def test_event_runtime_and_daily_limits(rig):
    _, store, _, _ = rig
    store.arm()
    with pytest.raises(Refused, match="volume_limit"):
        dose(store, volume=999)
    p = store.profile("juniper-10")
    store.update_profile(p["id"], {"flow_ml_min": 1, "flow_confirmed": True}, p["revision"])
    with pytest.raises(Refused, match="runtime_limit"):
        dose(store, volume=10)
    p = store.profile("juniper-10")
    store.update_profile(
        p["id"],
        {"flow_ml_min": 60, "flow_confirmed": True, "dose_ml": 1, "daily_limit_ml": 1},
        p["revision"],
    )
    dose(store)
    with pytest.raises(Refused):
        dose(store)


def test_concurrent_requests_cannot_double_reserve(rig):
    _, store, _, _ = rig
    store.arm()

    def request(_):
        try:
            return dose(store)["id"]
        except Refused:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(request, range(8)))
    assert sum(value is not None for value in results) == 1


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"tank_ok": False}, "tank_empty"),
        ({"leak": True}, "leak_detected"),
    ],
)
def test_unsafe_sensor_blocks_and_latches_stop(rig, changes, code):
    _, store, _, controller = rig
    store.arm()
    store.set_simulation(changes)
    controller.sample()
    assert store.state()["fault"] == code
    assert store.state()["armed"] is False
    with pytest.raises(Refused):
        dose(store)


def test_emergency_stop_during_dose_turns_off_and_never_replays(rig):
    _, store, hardware, controller = rig
    store.arm()
    command = dose(store)

    def sleep(_):
        store.stop("operator")

    controller.sleep = sleep
    controller.run_once()
    assert not hardware.running
    assert store.command(command["id"])["status"] == "interrupted"
    assert store.state()["estop"] is True
    with pytest.raises(Refused):
        store.arm()
    controller.run_once()
    assert hardware.started_count == 1


def test_rechecks_safety_after_queue_and_before_actuation(rig):
    _, store, hardware, controller = rig
    store.arm()
    command = dose(store)
    store.set_simulation({"leak": True})
    controller.run_once()
    assert hardware.started_count == 0
    assert store.command(command["id"])["status"] != "completed"


def test_restart_cancels_queue_and_disarms(rig):
    settings, store, _, controller = rig
    store.arm()
    command = dose(store)
    controller.close()
    replacement = Controller(settings, store, SimulatedHardware(store))
    replacement.start()
    try:
        assert store.state()["armed"] is False
        assert store.command(command["id"])["status"] == "cancelled"
    finally:
        replacement.close()


def test_second_controller_is_rejected(rig):
    settings, store, _, _ = rig
    other = Controller(settings, store, SimulatedHardware(store))
    with pytest.raises(RuntimeError, match="already running"):
        other.start()


def test_stale_reading_and_worker_heartbeat_refuse(rig):
    _, store, _, _ = rig
    store.arm()
    with store.db(True) as db:
        db.execute("UPDATE readings SET recorded_at=0")
    with pytest.raises(Refused, match="sensor_stale"):
        dose(store)


def test_profile_revision_and_calibration_boundaries(rig):
    _, store, _, _ = rig
    p = store.profile("juniper-10")
    with pytest.raises(Refused, match="invalid_calibration"):
        store.update_profile(
            p["id"], {"wet_raw": 2500, "calibration_confirmed": True}, p["revision"]
        )
    store.update_profile(p["id"], {"name": "New name"}, p["revision"])
    with pytest.raises(Refused, match="profile_conflict"):
        store.update_profile(p["id"], {"name": "Stale"}, p["revision"])


def test_reset_stop_requires_safe_fresh_measurements(rig):
    _, store, _, controller = rig
    store.set_simulation({"leak": True})
    controller.sample()
    with pytest.raises(Refused, match="leak_detected"):
        store.reset_stop()
    store.set_simulation({"leak": False})
    controller.sample()
    store.reset_stop()
    assert store.state()["estop"] is False
    assert store.state()["armed"] is False


def test_hardware_fault_forces_off_and_records_failure(rig):
    _, store, hardware, controller = rig
    store.arm()
    command = dose(store)

    def fail(_):
        raise OSError("disconnected")

    hardware.on = fail
    controller.run_once()
    assert not hardware.running
    assert store.state()["fault"] == "hardware_error"
    assert store.command(command["id"])["status"] == "interrupted"
