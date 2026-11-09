"""Command-line entry points for local development and Raspberry Pi services."""

import argparse
import getpass
import json
import logging
import os
import platform
import signal
import threading

import uvicorn

from .config import load_settings
from .controller import Controller
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="ka-a · local plant care")
    parser.add_argument("--config", help="Path to a local YAML configuration")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="Create or rotate the admin password")
    setup.add_argument("--password-env", action="store_true", help="Read KAA_ADMIN_PASSWORD")
    for name in ("serve", "demo"):
        command = sub.add_parser(name)
        command.add_argument("--host")
        command.add_argument("--port", type=int)
    sub.add_parser("controller")
    sub.add_parser("doctor")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings(args.config)
    if getattr(args, "host", None):
        settings.host = args.host
    if getattr(args, "port", None):
        settings.port = args.port
    store = Store(settings)
    if args.command == "setup":
        if args.password_env:
            password = os.environ.pop("KAA_ADMIN_PASSWORD", "")
        else:
            password = getpass.getpass("New admin password (12+ characters): ")
            if password != getpass.getpass("Repeat password: "):
                parser.error("Passwords do not match")
        store.set_password(password)
        print("Admin password saved as a salted hash. Existing sessions were revoked.")
    elif args.command == "doctor":
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "mode": settings.mode,
                    "hardware_enabled": settings.hardware_enabled,
                    "hardware_env_opt_in": os.getenv("KAA_ENABLE_HARDWARE") == "YES",
                    "data_dir": str(settings.data_dir.resolve()),
                    "controller_online": store.snapshot()["controller_online"],
                    "cloud_configured": bool(settings.mqtt_endpoint),
                },
                indent=2,
            )
        )
    elif args.command == "controller":
        from .cloud import build_cloud

        stopped = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stopped.set())
        Controller(settings, store, cloud=build_cloud(settings, store)).run(stopped)
    elif args.command in ("serve", "demo"):
        from .web import create_app

        controller, stopped, worker = None, threading.Event(), None
        if args.command == "demo":
            if settings.mode != "simulation":
                parser.error(
                    "Demo requires simulation mode and a separate development data directory"
                )
            controller = Controller(settings, store)
            controller.start()
            controller.sample()

            def tick():
                try:
                    while not stopped.wait(settings.sample_seconds):
                        try:
                            controller.run_once()
                        except Exception:
                            logging.exception("Simulation controller fault")
                finally:
                    controller.close()

            worker = threading.Thread(target=tick, name="kaa-simulation", daemon=True)
            worker.start()
        try:
            uvicorn.run(
                create_app(settings),
                host=settings.host,
                port=settings.port,
                workers=1,
                access_log=False,
                proxy_headers=False,
            )
        finally:
            stopped.set()
            if worker:
                worker.join(timeout=5)
