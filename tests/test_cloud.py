from types import SimpleNamespace

import pytest

from kaa.cloud import Telemetry, build_cloud


class FakeClient:
    connected = False

    def is_connected(self):
        return self.connected

    def publish(self, *args, **kwargs):
        self.last_publish = (args, kwargs)
        return SimpleNamespace(rc=0, mid=12)


def test_cloud_disabled_by_default(rig):
    settings, store, _, _ = rig
    assert build_cloud(settings, store) is None
    assert store.state()["cloud"] == "disabled"


def test_offline_outbox_survives_until_puback(rig):
    settings, store, _, _ = rig
    client = FakeClient()
    cloud = Telemetry(settings, store, client)
    cloud.enqueue(store.snapshot())
    cloud.flush()
    assert store.snapshot()["outbox_pending"] == 1
    client.connected = True
    cloud.flush()
    assert client.last_publish[1] == {"qos": 1, "retain": False}
    assert store.snapshot()["outbox_pending"] == 1
    cloud._published(client, None, 12, SimpleNamespace(is_failure=False), None)
    assert store.snapshot()["outbox_pending"] == 0


def test_telemetry_is_bounded_and_contains_no_admin_secrets(rig):
    settings, store, _, _ = rig
    store.set_password("synthetic-test-password")
    cloud = Telemetry(settings, store, FakeClient())
    for _ in range(1003):
        cloud.enqueue(
            {"server_time": 123, "mode": "simulation", "armed": False, "fault": None, "plants": []}
        )
    assert store.snapshot()["outbox_pending"] == 1000
    with store.db() as db:
        payload = db.execute("SELECT payload FROM outbox LIMIT 1").fetchone()[0]
    assert "password" not in payload and "sessions" not in payload


def test_cloud_endpoint_rejects_arbitrary_hosts(rig):
    settings, store, _, _ = rig
    with pytest.raises(ValueError, match="AWS IoT"):
        build_cloud(settings.model_copy(update={"mqtt_endpoint": "evil.example"}), store)
