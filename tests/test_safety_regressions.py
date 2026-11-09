import threading

import pytest
from test_controller import dose

from kaa.config import Settings
from kaa.controller import Controller
from kaa.domain import Refused
from kaa.hardware import check_hardware_opt_in
from kaa.store import Store


def test_expired_command_is_cancelled_without_pumping(rig):
    _, store, hardware, controller = rig
    store.arm()
    command = dose(store)
    with store.db(True) as db:
        db.execute("UPDATE commands SET expires_at=0 WHERE id=?", (command["id"],))
    controller.run_once()
    assert hardware.started_count == 0
    assert store.command(command["id"])["reason"] == "command_expired"


def test_clean_shutdown_immediately_reports_offline(rig):
    _, store, _, controller = rig
    controller.close()
    assert store.snapshot()["controller_online"] is False


def test_shutdown_signal_interrupts_an_active_dose(rig):
    _, store, hardware, controller = rig
    store.arm()
    command = dose(store)
    stopped = threading.Event()
    controller.stopped = stopped
    controller.sleep = lambda _: stopped.set()
    controller.run_once()
    assert not hardware.running
    assert store.command(command["id"])["status"] == "interrupted"


def test_unconfirmed_sensor_change_clears_previous_confirmation(rig):
    _, store, _, _ = rig
    p = store.profile("juniper-10")
    p = store.update_profile(p["id"], {"dry_raw": 2600}, p["revision"])
    assert p["calibration_confirmed"] is False


def test_boot_interrupted_dose_stays_in_water_budget(rig):
    settings, store, _, controller = rig
    store.arm()
    command = dose(store)
    store.claim()
    controller.close()
    store.recover()
    assert store.command(command["id"])["status"] == "interrupted"
    assert store.snapshot()["plants"][0]["used_today_ml"] == 1
    assert store.state()["estop"] is True


def test_automatic_mode_requires_three_low_readings_and_respects_reservations(rig):
    _, store, hardware, controller = rig
    p = store.profile("juniper-10")
    store.update_profile(
        p["id"],
        {"automatic": True, "dry_threshold": 40, "dose_ml": 1, "start_hour": 0, "end_hour": 24},
        p["revision"],
    )
    store.arm()
    readings = hardware.read()
    controller.automate(readings)
    controller.automate(readings)
    assert not store.snapshot()["commands"]
    controller.automate(readings)
    assert len(store.snapshot()["commands"]) == 1
    for _ in range(3):
        controller.automate(readings)
    assert len(store.snapshot()["commands"]) == 1


def test_hardware_opt_in_refuses_default_settings():
    with pytest.raises(RuntimeError, match="Hardware requires"):
        check_hardware_opt_in(Settings())


def test_mode_switch_discards_simulation_calibration(rig):
    settings, store, _, controller = rig
    controller.close()
    real_settings = settings.model_copy(update={"mode": "raspberry"})
    real_store = Store(real_settings)
    real_store.recover()
    assert not real_store.profile("juniper-10")["calibration_confirmed"]
    assert not real_store.profile("juniper-10")["flow_confirmed"]
    assert real_store.snapshot()["plants"][0]["reading"] is None


def test_worker_takes_lock_before_constructing_hardware(rig, monkeypatch):
    settings, store, _, _ = rig
    called = []
    monkeypatch.setattr("kaa.controller.build_hardware", lambda *args: called.append(True))
    other = Controller(settings, store)
    with pytest.raises(RuntimeError, match="already running"):
        other.start()
    assert called == []


def test_password_rotation_revokes_sessions_and_failures_are_rate_limited(tmp_path):
    store = Store(Settings(data_dir=tmp_path))
    store.set_password("test-password-one")
    token = store.login("test-password-one")
    assert store.session_valid(token)
    store.set_password("test-password-two")
    assert not store.session_valid(token)
    for _ in range(5):
        with pytest.raises(Refused, match="invalid_credentials"):
            store.login("wrong")
    with pytest.raises(Refused, match="login_rate_limit"):
        store.login("wrong")
