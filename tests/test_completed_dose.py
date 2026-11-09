from test_controller import dose


def test_completed_dose_is_accounted_and_changes_only_its_simulated_pot(rig):
    _, store, hardware, controller = rig
    before = store.simulation()["raw"].copy()
    store.arm()
    command = dose(store)
    controller.run_once()
    assert store.command(command["id"])["status"] == "completed"
    assert hardware.started_count == 1 and not hardware.running
    after = store.simulation()["raw"]
    assert after["juniper-10"] < before["juniper-10"]
    assert after["juniper-7"] == before["juniper-7"]
    assert store.snapshot()["plants"][0]["used_today_ml"] == 1
