"""Optional certificate-authenticated telemetry. It never accepts actuator commands."""

import json
import logging
import re
import ssl
import threading
import uuid

log = logging.getLogger(__name__)


class Telemetry:
    def __init__(self, settings, store, client=None):
        self.settings, self.store = settings, store
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", settings.mqtt_client_id):
            raise ValueError("Use a simple MQTT client ID")
        self.topic = f"kaa/{settings.mqtt_client_id}/telemetry"
        self.client = client
        self.pending = {}
        self.early_acks = set()
        self.lock = threading.RLock()

    def start(self):
        if self.client is None:
            import paho.mqtt.client as mqtt

            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2, client_id=self.settings.mqtt_client_id
            )
            self.client.tls_set(
                ca_certs=self.settings.mqtt_ca,
                certfile=self.settings.mqtt_cert,
                keyfile=self.settings.mqtt_key,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
        self.client.on_connect = self._connected
        self.client.on_disconnect = self._disconnected
        self.client.on_publish = self._published
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)
        self.client.max_queued_messages_set(20)
        self.client.connect_async(self.settings.mqtt_endpoint, 8883, keepalive=60)
        self.client.loop_start()
        self.store.cloud_state("connecting")

    def _connected(self, client, userdata, flags, reason_code, properties):
        self.store.cloud_state("offline" if reason_code.is_failure else "connected")

    def _disconnected(self, *args):
        with self.lock:
            self.pending.clear()
            self.early_acks.clear()
        self.store.cloud_state("offline")

    def _published(self, client, userdata, mid, reason_code, properties):
        if reason_code.is_failure:
            return
        with self.lock:
            row_id = self.pending.pop(mid, None)
            if row_id is None:
                self.early_acks.add(mid)
                return
        with self.store.db(True) as db:
            db.execute("DELETE FROM outbox WHERE id=?", (row_id,))

    def enqueue(self, snapshot):
        payload = {
            "event_id": str(uuid.uuid4()),
            "device": self.settings.mqtt_client_id,
            "recorded_at": snapshot["server_time"],
            "mode": snapshot["mode"],
            "armed": snapshot["armed"],
            "fault": snapshot["fault"],
            "plants": [
                {
                    "id": p["id"],
                    "reading": p["reading"],
                    "relative_moisture": p["moisture"],
                    "stale": p["stale"],
                }
                for p in snapshot["plants"]
            ],
        }
        with self.store.db(True) as db:
            db.execute("INSERT INTO outbox(payload) VALUES (?)", (json.dumps(payload),))
            db.execute(
                "DELETE FROM outbox WHERE id NOT IN "
                "(SELECT id FROM outbox ORDER BY id DESC LIMIT 1000)"
            )

    def flush(self):
        if self.client is None or not self.client.is_connected():
            return
        with self.lock:
            if self.pending:
                return
            with self.store.db() as db:
                row = db.execute("SELECT * FROM outbox ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return
            info = self.client.publish(self.topic, row["payload"], qos=1, retain=False)
            if info.rc == 0:
                if info.mid in self.early_acks:
                    self.early_acks.remove(info.mid)
                    with self.store.db(True) as db:
                        db.execute("DELETE FROM outbox WHERE id=?", (row["id"],))
                else:
                    self.pending[info.mid] = row["id"]

    def close(self):
        if self.client is not None:
            self.client.disconnect()
            self.client.loop_stop()
        self.store.cloud_state("offline")


def build_cloud(settings, store):
    if not settings.mqtt_endpoint:
        store.cloud_state("disabled")
        return None
    if not re.fullmatch(
        r"[a-zA-Z0-9.-]+\.iot\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?", settings.mqtt_endpoint
    ):
        raise ValueError("Use the AWS IoT ATS hostname without a URL scheme")
    return Telemetry(settings, store)
