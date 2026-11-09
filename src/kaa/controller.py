"""Single-owner control loop, separate from HTTP request processing."""

import fcntl
import logging
import time
import uuid

from .domain import Refused, moisture
from .hardware import build_hardware

log = logging.getLogger(__name__)


class Controller:
    def __init__(self, settings, store, hardware=None, cloud=None):
        self.settings, self.store, self.hardware, self.cloud = settings, store, hardware, cloud
        self.sleep = time.sleep
        self.lock = None
        self.low_counts = {}
        self.last_cloud = 0
        self.last_prune = 0
        self.stopped = None

    def start(self):
        self.lock = open(self.settings.data_dir / "controller.lock", "a+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock.close()
            self.lock = None
            raise RuntimeError("A controller is already running for this database") from exc
        try:
            if self.hardware is None:
                self.hardware = build_hardware(self.settings, self.store)
            self.hardware.off_all()
            self.store.recover()
            if self.cloud:
                self.cloud.start()
        except BaseException:
            self.close()
            raise

    def sample(self):
        try:
            readings = self.hardware.read()
            if set(readings) != {"juniper-10", "juniper-7"}:
                raise OSError("Incomplete readings")
            self.store.record(readings)
            reason = next(
                (
                    "leak_detected" if r["leak"] else "tank_empty"
                    for r in readings.values()
                    if r["leak"] or not r["tank_ok"]
                ),
                None,
            )
            if reason:
                self.hardware.off_all()
                self.store.stop(reason, fault=reason)
            return readings
        except Exception:
            try:
                self.hardware.off_all()
            finally:
                self.store.stop("sensor_error", fault="sensor_error")
            raise

    def automate(self, readings):
        state = self.store.state()
        if not state["armed"] or state["estop"] or state["fault"]:
            return
        for p in self.store.profiles():
            level = moisture(readings[p["id"]]["raw"], p)
            low = level is not None and level <= p["dry_threshold"] and p["automatic"]
            self.low_counts[p["id"]] = self.low_counts.get(p["id"], 0) + 1 if low else 0
            if self.low_counts[p["id"]] >= 3:
                try:
                    self.store.enqueue(p["id"], p["dose_ml"], str(uuid.uuid4()), "automatic")
                except Refused:
                    pass
                self.low_counts[p["id"]] = 0

    def run_once(self):
        readings = self.sample()
        self.automate(readings)
        command = self.store.claim()
        if command:
            self._execute(command)
        now = time.time()
        if now - self.last_cloud >= self.settings.telemetry_interval_seconds:
            self.last_cloud = now
            if self.cloud:
                self.cloud.enqueue(self.store.snapshot())
        if self.cloud:
            self.cloud.flush()
        if now - self.last_prune >= 3600:
            self.store.prune()
            self.last_prune = now

    def _execute(self, command):
        p = command["profile"]
        duration = command["volume_ml"] / p["flow_ml_min"] * 60
        deadline = time.monotonic() + min(duration, self.settings.max_runtime_seconds)
        status, reason = "completed", None
        try:
            state = self.store.state()
            if state["estop"] or not state["armed"] or state["fault"]:
                raise Refused("control_stopped")
            self.hardware.on(p["id"])
            next_sample = 0
            while time.monotonic() < deadline:
                if self.stopped is not None and self.stopped.is_set():
                    raise Refused("controller_shutdown")
                state = self.store.state()
                if state["estop"] or not state["armed"] or state["fault"]:
                    raise Refused("control_stopped")
                if time.monotonic() >= next_sample:
                    readings = self.sample()
                    level = moisture(readings[p["id"]]["raw"], p)
                    if level is None or level >= p["wet_cutoff"]:
                        raise Refused("soil_too_wet")
                    next_sample = time.monotonic() + min(self.settings.sample_seconds, 1)
                self.sleep(min(0.1, max(0, deadline - time.monotonic())))
        except Refused as exc:
            status, reason = "interrupted", exc.code
        except Exception:
            log.exception("Actuator command failed")
            status, reason = "interrupted", "hardware_error"
            self.store.stop(reason, fault=reason)
        except BaseException:
            status, reason = "interrupted", "controller_shutdown"
            raise
        finally:
            try:
                self.hardware.off_all()
            except Exception:
                status, reason = "interrupted", "shutdown_unconfirmed"
                self.store.stop(reason, fault=reason)
                raise
            finally:
                self.store.finish(command["id"], status, reason)
        if status == "completed":
            self.hardware.delivered(p["id"], command["volume_ml"])

    def close(self):
        # A failed duplicate start must never close another controller's hardware.
        if self.lock is not None:
            try:
                if self.hardware is not None:
                    self.hardware.close()
                self.store.stop("controller_shutdown", latch=False)
                self.store.mark_offline()
                if self.cloud:
                    self.cloud.close()
            finally:
                fcntl.flock(self.lock, fcntl.LOCK_UN)
                self.lock.close()
                self.lock = None

    def run(self, stopped):
        self.stopped = stopped
        self.start()
        try:
            while not stopped.is_set():
                try:
                    self.run_once()
                except Exception:
                    log.exception("Controller fault; outputs are disabled")
                stopped.wait(self.settings.sample_seconds)
        finally:
            self.close()
