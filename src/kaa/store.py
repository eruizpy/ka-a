"""SQLite persistence and transactional safety reservations."""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .domain import Refused, check_safety, day_start, moisture, validate_profile


class Store:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = settings.data_dir / "kaa.sqlite3"
        with self.db(True) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS readings(
                    id INTEGER PRIMARY KEY, plant_id TEXT NOT NULL, recorded_at REAL NOT NULL,
                    raw REAL NOT NULL, temperature REAL NOT NULL, humidity REAL NOT NULL,
                    tank_ok INTEGER NOT NULL, leak INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reading_time ON readings(plant_id, recorded_at);
                CREATE TABLE IF NOT EXISTS commands(
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    plant_id TEXT NOT NULL, volume_ml REAL NOT NULL,
                    source TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    status TEXT NOT NULL, reason TEXT, finished_at REAL
                );
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY, recorded_at REAL NOT NULL,
                    kind TEXT NOT NULL, detail TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, expires_at REAL);
                CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            """)
            for key, value in {
                "state": {
                    "armed": False,
                    "estop": False,
                    "fault": None,
                    "heartbeat": 0,
                    "mode": settings.mode,
                    "cloud": "disabled",
                },
                "simulation": {
                    "tank_ok": True,
                    "leak": False,
                    "raw": {"juniper-10": 2100, "juniper-7": 1900},
                },
                "login_attempts": [],
            }.items():
                db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", (key, json.dumps(value)))
            for age in (10, 7):
                profile = {
                    "id": f"juniper-{age}",
                    "name": f"Junípero · {age} años",
                    "species": "Juniperus · variedad por identificar",
                    "age_years": age,
                    "location": "Balcón · repisa elevada",
                    "revision": 1,
                    "dry_raw": None,
                    "wet_raw": None,
                    "calibration_confirmed": False,
                    "flow_ml_min": 60,
                    "flow_confirmed": False,
                    "automatic": False,
                    "dry_threshold": 30,
                    "wet_cutoff": 80,
                    "dose_ml": 20,
                    "daily_limit_ml": 200,
                    "minimum_interval_seconds": 1800,
                    "start_hour": 6,
                    "end_hour": 18,
                }
                db.execute(
                    "INSERT OR IGNORE INTO profiles VALUES (?,?)",
                    (profile["id"], json.dumps(profile)),
                )
        self.path.chmod(0o600)

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _meta(db, key):
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _put(db, key, value):
        db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))

    @staticmethod
    def _event(db, kind, detail):
        db.execute(
            "INSERT INTO events(recorded_at,kind,detail) VALUES (?,?,?)",
            (time.time(), kind, json.dumps(detail, ensure_ascii=False)),
        )

    @staticmethod
    def _profile(db, plant_id):
        row = db.execute("SELECT value FROM profiles WHERE id=?", (plant_id,)).fetchone()
        if not row:
            raise Refused("plant_not_found")
        return json.loads(row[0])

    @staticmethod
    def _reading(db, plant_id):
        row = db.execute(
            "SELECT * FROM readings WHERE plant_id=? ORDER BY id DESC LIMIT 1", (plant_id,)
        ).fetchone()
        return dict(row) if row else None

    def state(self):
        with self.db() as db:
            return self._meta(db, "state")

    def profiles(self):
        with self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT value FROM profiles ORDER BY id")]

    def profile(self, plant_id):
        with self.db() as db:
            return self._profile(db, plant_id)

    def update_profile(self, plant_id, changes, revision):
        with self.db(True) as db:
            p = self._profile(db, plant_id)
            if p["revision"] != revision:
                raise Refused("profile_conflict")
            if any(k in changes and changes[k] != p[k] for k in ("dry_raw", "wet_raw")):
                p["calibration_confirmed"] = bool(changes.get("calibration_confirmed", False))
            if "flow_ml_min" in changes and changes["flow_ml_min"] != p["flow_ml_min"]:
                p["flow_confirmed"] = bool(changes.get("flow_confirmed", False))
            p.update(changes)
            validate_profile(p, self.settings)
            if db.execute(
                "SELECT 1 FROM commands WHERE plant_id=? AND status='running'", (plant_id,)
            ).fetchone():
                raise Refused("plant_busy")
            p["revision"] += 1
            db.execute("UPDATE profiles SET value=? WHERE id=?", (json.dumps(p), plant_id))
            self._event(db, "profile_updated", {"plant_id": plant_id})
            return p

    def recover(self):
        with self.db(True) as db:
            state = self._meta(db, "state")
            if state["mode"] != self.settings.mode:
                for row in db.execute("SELECT id,value FROM profiles").fetchall():
                    profile = json.loads(row["value"])
                    profile.update(
                        calibration_confirmed=False, flow_confirmed=False, automatic=False
                    )
                    profile["revision"] += 1
                    db.execute(
                        "UPDATE profiles SET value=? WHERE id=?", (json.dumps(profile), row["id"])
                    )
                db.execute("DELETE FROM readings")
                self._event(db, "mode_changed", {"mode": self.settings.mode})
            state.update(armed=False, heartbeat=time.time(), mode=self.settings.mode)
            running = db.execute("SELECT COUNT(*) FROM commands WHERE status='running'").fetchone()[
                0
            ]
            db.execute(
                "UPDATE commands SET status='interrupted',reason='controller_restart',"
                "finished_at=? WHERE status='running'",
                (time.time(),),
            )
            db.execute(
                "UPDATE commands SET status='cancelled',reason='controller_restart',"
                "finished_at=? WHERE status='queued'",
                (time.time(),),
            )
            if running:
                state.update(estop=True, fault="interrupted_dose")
            self._put(db, "state", state)
            self._event(db, "controller_started", {"mode": self.settings.mode})

    def heartbeat(self):
        with self.db(True) as db:
            state = self._meta(db, "state")
            state["heartbeat"] = time.time()
            self._put(db, "state", state)

    def mark_offline(self):
        with self.db(True) as db:
            state = self._meta(db, "state")
            state.update(heartbeat=0, armed=False)
            self._put(db, "state", state)

    def arm(self):
        with self.db(True) as db:
            state = self._meta(db, "state")
            if state["estop"]:
                raise Refused("emergency_stop")
            if state["fault"]:
                raise Refused(state["fault"])
            self._check_inputs(db, state)
            state["armed"] = True
            self._put(db, "state", state)
            self._event(db, "armed", {})

    def _check_inputs(self, db, state):
        now = time.time()
        if (
            state["mode"] != self.settings.mode
            or now - state["heartbeat"] > self.settings.stale_seconds
        ):
            raise Refused("controller_offline")
        for row in db.execute("SELECT id FROM profiles"):
            reading = self._reading(db, row[0])
            if not reading or now - reading["recorded_at"] > self.settings.stale_seconds:
                raise Refused("sensor_stale")
            if not reading["tank_ok"]:
                raise Refused("tank_empty")
            if reading["leak"]:
                raise Refused("leak_detected")

    def stop(self, reason="operator", fault=None, latch=True):
        with self.db(True) as db:
            state = self._meta(db, "state")
            changed = state["armed"] or (latch and not state["estop"]) or fault != state["fault"]
            state["armed"] = False
            if latch:
                state["estop"] = True
            if fault:
                state["fault"] = fault
            self._put(db, "state", state)
            db.execute(
                "UPDATE commands SET status='cancelled',reason=?,finished_at=? "
                "WHERE status='queued'",
                (reason, time.time()),
            )
            if changed:
                self._event(db, "stop" if latch else "disarmed", {"reason": reason})

    def reset_stop(self):
        with self.db(True) as db:
            state = self._meta(db, "state")
            self._check_inputs(db, state)
            if db.execute("SELECT 1 FROM commands WHERE status='running'").fetchone():
                raise Refused("controller_busy")
            state.update(estop=False, fault=None, armed=False)
            self._put(db, "state", state)
            self._event(db, "stop_reset", {})

    def record(self, samples):
        with self.db(True) as db:
            now = time.time()
            db.executemany(
                "INSERT INTO readings(plant_id,recorded_at,raw,temperature,humidity,"
                "tank_ok,leak) VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        plant_id,
                        now,
                        reading["raw"],
                        reading["temperature"],
                        reading["humidity"],
                        reading["tank_ok"],
                        reading["leak"],
                    )
                    for plant_id, reading in samples.items()
                ],
            )
            state = self._meta(db, "state")
            state["heartbeat"] = now
            self._put(db, "state", state)

    def _validate_command(self, db, p, volume, source, exclude=None):
        now = time.time()
        rows = db.execute(
            "SELECT * FROM commands WHERE plant_id=? AND id!=? AND status IN "
            "('queued','running','completed','interrupted')",
            (p["id"], exclude or ""),
        ).fetchall()
        start = day_start(now, self.settings.timezone)
        used = sum(
            r["volume_ml"]
            for r in rows
            if r["status"] in ("queued", "running")
            or max(r["created_at"], r["finished_at"] or r["created_at"]) >= start
        )
        last_at = max((r["finished_at"] or r["created_at"] for r in rows), default=None)
        check_safety(
            self._meta(db, "state"),
            p,
            self._reading(db, p["id"]),
            volume,
            self.settings,
            now,
            used,
            last_at,
            source,
        )

    def enqueue(self, plant_id, volume, request_id, source="manual"):
        uuid.UUID(request_id)
        with self.db(True) as db:
            existing = db.execute(
                "SELECT * FROM commands WHERE request_id=?", (request_id,)
            ).fetchone()
            if existing:
                if (existing["plant_id"], existing["volume_ml"], existing["source"]) != (
                    plant_id,
                    volume,
                    source,
                ):
                    raise Refused("idempotency_conflict")
                return dict(existing)
            p = self._profile(db, plant_id)
            self._validate_command(db, p, volume, source)
            command_id, now = str(uuid.uuid4()), time.time()
            db.execute(
                "INSERT INTO commands VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    command_id,
                    request_id,
                    plant_id,
                    volume,
                    source,
                    now,
                    now + 60,
                    "queued",
                    None,
                    None,
                ),
            )
            self._event(db, "dose_queued", {"plant_id": plant_id, "volume_ml": volume})
            return dict(db.execute("SELECT * FROM commands WHERE id=?", (command_id,)).fetchone())

    def claim(self):
        with self.db(True) as db:
            row = db.execute(
                "SELECT * FROM commands WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            command = dict(row)
            try:
                if command["expires_at"] <= time.time():
                    raise Refused("command_expired")
                p = self._profile(db, command["plant_id"])
                self._validate_command(
                    db, p, command["volume_ml"], command["source"], command["id"]
                )
            except Refused as exc:
                db.execute(
                    "UPDATE commands SET status='cancelled',reason=?,finished_at=? WHERE id=?",
                    (exc.code, time.time(), command["id"]),
                )
                return None
            db.execute("UPDATE commands SET status='running' WHERE id=?", (command["id"],))
            command["status"] = "running"
            command["profile"] = p
            return command

    def finish(self, command_id, status, reason=None):
        with self.db(True) as db:
            db.execute(
                "UPDATE commands SET status=?,reason=?,finished_at=? WHERE id=?",
                (status, reason, time.time(), command_id),
            )
            self._event(db, "dose_" + status, {"command_id": command_id, "reason": reason})

    def command(self, command_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM commands WHERE id=?", (command_id,)).fetchone()
            return dict(row) if row else None

    def simulation(self):
        with self.db() as db:
            return self._meta(db, "simulation")

    def set_simulation(self, changes):
        if self.settings.mode != "simulation":
            raise Refused("simulation_only")
        with self.db(True) as db:
            values = self._meta(db, "simulation")
            values.update(changes)
            self._put(db, "simulation", values)

    def snapshot(self):
        now = time.time()
        with self.db() as db:
            state = self._meta(db, "state")
            plants = []
            for row in db.execute("SELECT value FROM profiles ORDER BY id"):
                p = json.loads(row[0])
                reading = self._reading(db, p["id"])
                p["reading"] = reading
                p["moisture"] = moisture(reading["raw"], p) if reading else None
                p["stale"] = (
                    not reading or now - reading["recorded_at"] > self.settings.stale_seconds
                )
                p["used_today_ml"] = db.execute(
                    "SELECT COALESCE(SUM(volume_ml),0) FROM commands WHERE plant_id=? "
                    "AND status IN ('queued','running','completed','interrupted') "
                    "AND (status IN ('queued','running') "
                    "OR MAX(created_at,COALESCE(finished_at,created_at))>=?)",
                    (p["id"], day_start(now, self.settings.timezone)),
                ).fetchone()[0]
                p["history"] = [
                    dict(r)
                    for r in db.execute(
                        "SELECT recorded_at,raw FROM readings "
                        "WHERE plant_id=? ORDER BY id DESC LIMIT 60",
                        (p["id"],),
                    )
                ][::-1]
                plants.append(p)
            events = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")]
            commands = [
                dict(r)
                for r in db.execute("SELECT * FROM commands ORDER BY created_at DESC LIMIT 30")
            ]
            return {
                **state,
                "controller_online": now - state["heartbeat"] <= self.settings.stale_seconds,
                "server_time": now,
                "timezone": self.settings.timezone,
                "plants": plants,
                "events": events,
                "commands": commands,
                "outbox_pending": db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],
                "safety": {
                    "max_event_ml": self.settings.max_event_ml,
                    "max_daily_ml": self.settings.max_daily_ml,
                    "max_runtime_seconds": self.settings.max_runtime_seconds,
                },
            }

    def prune(self):
        with self.db(True) as db:
            cutoff = time.time() - self.settings.retention_days * 86400
            db.execute("DELETE FROM readings WHERE recorded_at < ?", (cutoff,))
            db.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY id DESC LIMIT 5000)"
            )
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
            # Command IDs and conservative water accounting remain durable for the device lifetime.

    def set_password(self, password):
        if len(password) < 12:
            raise ValueError("Use at least 12 characters")
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=67108864)
        with self.db(True) as db:
            self._put(db, "password", {"salt": salt.hex(), "digest": digest.hex()})
            db.execute("DELETE FROM sessions")

    def login(self, password):
        with self.db(True) as db:
            credential = self._meta(db, "password")
            attempts = [t for t in self._meta(db, "login_attempts") if t > time.time() - 60]
            if not credential:
                raise Refused("setup_required")
            if len(attempts) >= 5:
                raise Refused("login_rate_limit")
            digest = hashlib.scrypt(
                password.encode(),
                salt=bytes.fromhex(credential["salt"]),
                n=16384,
                r=8,
                p=1,
                maxmem=67108864,
            ).hex()
            valid = hmac.compare_digest(digest, credential["digest"])
            self._put(db, "login_attempts", [] if valid else [*attempts, time.time()])
            if valid:
                token = secrets.token_urlsafe(32)
                db.execute(
                    "INSERT INTO sessions VALUES (?,?)",
                    (self.token_hash(token), time.time() + 43200),
                )
                return token
        raise Refused("invalid_credentials")

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def session_valid(self, token):
        with self.db() as db:
            return (
                db.execute(
                    "SELECT 1 FROM sessions WHERE token_hash=? AND expires_at>?",
                    (self.token_hash(token), time.time()),
                ).fetchone()
                is not None
            )

    def logout(self, token):
        with self.db(True) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (self.token_hash(token),))

    def cloud_state(self, value):
        with self.db(True) as db:
            state = self._meta(db, "state")
            state["cloud"] = value
            self._put(db, "state", state)
