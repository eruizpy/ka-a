"""Boot-time configuration; GPIO cannot be changed from the web interface."""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: Path = Path("data")
    mode: Literal["simulation", "raspberry"] = "simulation"
    hardware_enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1024, le=65535)
    secure_cookie: bool = False
    public_origin: str = ""
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    timezone: str = "America/Asuncion"
    sample_seconds: float = Field(default=2, ge=0.05, le=30)
    stale_seconds: float = Field(default=15, ge=5, le=120)
    max_event_ml: float = Field(default=120, gt=0, le=1000)
    max_daily_ml: float = Field(default=500, gt=0, le=10000)
    max_runtime_seconds: float = Field(default=60, gt=0, le=120)
    telemetry_interval_seconds: int = Field(default=300, ge=30)
    retention_days: int = Field(default=30, ge=1, le=365)
    pump_pins: list[int] = [17, 27]
    tank_ok_pin: int = 22
    leak_clear_pin: int = 23
    adc_address: int = 0x48
    sht31_address: int = 0x44
    gpio_chip: int = 0
    mqtt_endpoint: str = ""
    mqtt_client_id: str = "ka-a-balcony"
    mqtt_ca: str = ""
    mqtt_cert: str = ""
    mqtt_key: str = ""

    @model_validator(mode="after")
    def validate_configuration(self):
        from zoneinfo import ZoneInfo

        ZoneInfo(self.timezone)
        if self.public_origin:
            from urllib.parse import urlsplit

            origin = urlsplit(self.public_origin)
            if (
                origin.scheme != "https"
                or not origin.netloc
                or origin.path
                or origin.query
                or origin.fragment
            ):
                raise ValueError("public_origin must be an HTTPS origin without a path")
        pins = [*self.pump_pins, self.tank_ok_pin, self.leak_clear_pin]
        if len(self.pump_pins) != 2 or len(set(pins)) != len(pins):
            raise ValueError("Two distinct pumps and independent safety inputs are required")
        if any(p not in range(4, 28) for p in pins):
            raise ValueError("GPIO pins must be BCM 4..27; reserve I2C pins")
        return self


def load_settings(path: str | None = None) -> Settings:
    source = path or os.getenv("KAA_CONFIG")
    values = yaml.safe_load(Path(source).read_text()) if source else {}
    values = values or {}
    if os.getenv("KAA_DATA_DIR"):
        values["data_dir"] = os.environ["KAA_DATA_DIR"]
    return Settings(**values)
