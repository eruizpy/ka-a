"""Real browser flows against a disposable simulation, never operational equipment."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yaml
from playwright.sync_api import expect, sync_playwright

from kaa.config import Settings
from kaa.store import Store

PASSWORD = "synthetic-browser-test-password"


@pytest.fixture
def station(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    data_dir = tmp_path / "data"
    Store(Settings(data_dir=data_dir)).set_password(PASSWORD)
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"data_dir": str(data_dir), "sample_seconds": 0.1}))
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "kaa", "--config", str(config), "demo", "--port", str(port)],
            stdout=log,
            stderr=log,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    if httpx.get(url + "/healthz").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                if process.poll() is not None:
                    pytest.fail((tmp_path / "server.log").read_text())
                time.sleep(0.1)
            else:
                pytest.fail("Simulation server did not become ready")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=7)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.fixture
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


def log_in(page, url):
    page.goto(url)
    page.get_by_label("Contraseña de administración").fill(PASSWORD)
    page.get_by_role("button", name="Entrar al jardín").click()
    expect(page.get_by_role("heading", name="Cuidar también es observar.")).to_be_visible()
    expect(page.get_by_text("Controlador conectado", exact=True)).to_be_visible()


def calibrate(page):
    page.get_by_role("button", name="Estación", exact=False).click()
    page.get_by_role("button", name="Preparar calibración de ejemplo").click()
    expect(page.get_by_text("Calibración de ejemplo aplicada sólo a la simulación")).to_be_visible()
    page.get_by_role("button", name="Mi jardín", exact=False).click()


def test_login_profile_edit_and_persistence(station, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    log_in(page, station)
    page.get_by_role("button", name="Configurar Junípero · 10 años").first.click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Nombre", exact=True).fill("Junípero del balcón")
    dialog.get_by_role("button", name="Guardar perfil").click()
    expect(page.get_by_role("heading", name="Junípero del balcón").first).to_be_visible()
    page.reload()
    expect(page.get_by_role("heading", name="Junípero del balcón").first).to_be_visible()
    page.get_by_role("button", name="Cerrar sesión").click()
    expect(page.get_by_label("Contraseña de administración")).to_be_visible()
    assert page.request.get(station + "/api/status").status == 401
    assert not errors
    page.close()


def test_watering_with_http_uuid_fallback_and_emergency_stop(station, browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    page.add_init_script("Object.defineProperty(window.crypto, 'randomUUID', {value: undefined})")
    log_in(page, station)
    expect(page.get_by_role("button", name="Solicitar riego").first).to_be_disabled()
    calibrate(page)
    page.get_by_role("button", name="Habilitar riego", exact=True).click()
    page.get_by_role("button", name="Solicitar riego").first.click()
    page.get_by_label("Volumen solicitado (ml)").fill("1")
    page.get_by_role("button", name="Confirmar dosis").click()
    expect(page.get_by_text("Dosis registrada.", exact=False)).to_be_visible()
    page.get_by_role("button", name="Parada de emergencia").click()
    expect(page.get_by_text("PARADA BLOQUEADA", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Habilitar riego", exact=True)).to_be_disabled()
    page.get_by_role("button", name="Liberar parada").click()
    expect(page.get_by_text("DESHABILITADO", exact=True)).to_be_visible()
    page.get_by_role("button", name="Actividad", exact=False).click()
    expect(page.get_by_role("cell", name="1 ml", exact=True)).to_be_visible()
    page.close()


def test_simulated_leak_latches_until_explicit_reset(station, browser):
    page = browser.new_page()
    log_in(page, station)
    page.get_by_role("button", name="Estación", exact=False).click()
    page.get_by_role("button", name="Simular fuga", exact=True).click()
    expect(page.locator("#fault-banner")).to_contain_text("fuga", timeout=10000)
    page.get_by_role("button", name="Restaurar sensores simulados").click()
    page.wait_for_timeout(300)
    page.get_by_role("button", name="Mi jardín", exact=False).click()
    page.get_by_role("button", name="Liberar parada").click()
    expect(page.get_by_text("DESHABILITADO", exact=True)).to_be_visible()
    page.close()


def test_responsive_dashboard_and_screenshots(station, browser):
    artifacts = Path(os.getenv("KAA_ARTIFACTS", "artifacts"))
    artifacts.mkdir(exist_ok=True, parents=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    log_in(page, station)
    calibrate(page)
    page.locator("#toast").wait_for(state="hidden")
    page.screenshot(path=str(artifacts / "dashboard-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("heading", name="Cuidar también es observar.")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(artifacts / "dashboard-mobile.png"), full_page=True)
    page.get_by_role("button", name="Configurar Junípero · 10 años").first.click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.screenshot(path=str(artifacts / "profile-mobile.png"), full_page=True)
    page.get_by_role("button", name="Cancelar", exact=True).click()
    page.get_by_role("button", name="Cerrar sesión", exact=False).click()
    expect(page.get_by_label("Contraseña de administración")).to_be_visible()
    page.close()
