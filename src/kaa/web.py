"""Authenticated local administration API. This process never imports GPIO drivers."""

import hashlib
import hmac
import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import load_settings
from .domain import Refused
from .store import Store


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Login(StrictModel):
    password: str = Field(min_length=1, max_length=256)


class Water(StrictModel):
    volume_ml: float = Field(gt=0, le=1000)
    request_id: str


class ProfilePatch(StrictModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=60)
    dry_raw: float | None = Field(default=None, ge=0, le=3300)
    wet_raw: float | None = Field(default=None, ge=0, le=3300)
    calibration_confirmed: bool | None = None
    flow_ml_min: float | None = Field(default=None, gt=0, le=1000)
    flow_confirmed: bool | None = None
    automatic: bool | None = None
    dry_threshold: float | None = Field(default=None, ge=0, le=100)
    wet_cutoff: float | None = Field(default=None, ge=0, le=100)
    dose_ml: float | None = Field(default=None, gt=0, le=1000)
    daily_limit_ml: float | None = Field(default=None, gt=0, le=10000)
    minimum_interval_seconds: int | None = Field(default=None, ge=60, le=86400)
    start_hour: int | None = Field(default=None, ge=0, le=23)
    end_hour: int | None = Field(default=None, ge=1, le=24)


class SimulationPatch(StrictModel):
    tank_ok: bool = True
    leak: bool = False
    raw: dict[str, float] | None = None


def csrf_token(session):
    return hmac.new(session.encode(), b"ka-a-csrf", hashlib.sha256).hexdigest()


def create_app(settings=None):
    settings = settings or load_settings()
    store = Store(settings)
    app = FastAPI(
        title="ka-a", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    static = Path(__file__).parent / "static"

    @app.exception_handler(Refused)
    async def refused(request, exc):
        codes = {
            "invalid_credentials": 401,
            "login_rate_limit": 429,
            "setup_required": 503,
            "plant_not_found": 404,
            "simulation_only": 403,
        }
        return JSONResponse({"error": exc.code}, status_code=codes.get(exc.code, 409))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Do not echo passwords, malformed numeric inputs, or user payloads.
        fields = [{"path": list(error["loc"]), "type": error["type"]} for error in exc.errors()]
        return JSONResponse({"error": "invalid_request", "fields": fields}, status_code=422)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def authenticated(request: Request):
        token = request.cookies.get("kaa_session", "")
        if not token or not store.session_valid(token):
            raise HTTPException(401, "authentication_required")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected = settings.public_origin or str(request.base_url).rstrip("/")
            if origin and origin != expected:
                raise HTTPException(403, "origin_mismatch")
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_token(token)):
                raise HTTPException(403, "csrf_required")
        return token

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        origin = request.headers.get("origin")
        expected = settings.public_origin or str(request.base_url).rstrip("/")
        if origin and origin != expected:
            raise HTTPException(403, "origin_mismatch")
        token = store.login(body.password)
        response.set_cookie(
            "kaa_session",
            token,
            httponly=True,
            samesite="strict",
            secure=settings.secure_cookie,
            max_age=43200,
            path="/",
        )
        return {"csrf": csrf_token(token)}

    @app.get("/api/session")
    def session(token: Annotated[str, Depends(authenticated)]):
        return {"csrf": csrf_token(token)}

    @app.post("/api/logout")
    def logout(response: Response, token: Annotated[str, Depends(authenticated)]):
        store.logout(token)
        response.delete_cookie("kaa_session", path="/")
        return {"ok": True}

    @app.get("/api/status", dependencies=[Depends(authenticated)])
    def status():
        return store.snapshot()

    @app.get("/api/export", dependencies=[Depends(authenticated)])
    def export():
        return Response(
            json.dumps(store.snapshot(), ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="ka-a-status.json"'},
        )

    @app.patch("/api/plants/{plant_id}", dependencies=[Depends(authenticated)])
    def profile(plant_id: str, body: ProfilePatch):
        changes = body.model_dump(exclude_unset=True, exclude={"revision"})
        if any(
            value is None for key, value in changes.items() if key not in ("dry_raw", "wet_raw")
        ):
            raise HTTPException(422, "null_field")
        return store.update_profile(plant_id, changes, body.revision)

    @app.post(
        "/api/plants/{plant_id}/water", dependencies=[Depends(authenticated)], status_code=202
    )
    def water(plant_id: str, body: Water):
        try:
            UUID(body.request_id)
        except ValueError as exc:
            raise HTTPException(422, "request_id_must_be_uuid") from exc
        return store.enqueue(plant_id, body.volume_ml, body.request_id)

    @app.post("/api/control/{action}", dependencies=[Depends(authenticated)])
    def control(action: str):
        if action == "arm":
            store.arm()
        elif action == "disarm":
            store.stop("operator_disarmed", latch=False)
        elif action == "stop":
            store.stop("operator_emergency_stop")
        elif action == "reset":
            store.reset_stop()
        else:
            raise HTTPException(404, "action_not_found")
        return store.state()

    @app.put("/api/simulation", dependencies=[Depends(authenticated)])
    def simulation(body: SimulationPatch):
        if body.raw is not None:
            if set(body.raw) != {"juniper-10", "juniper-7"} or any(
                not 0 <= v <= 3300 for v in body.raw.values()
            ):
                raise HTTPException(422, "invalid_simulated_readings")
        store.set_simulation(body.model_dump(exclude_none=True))
        return {"ok": True}

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
