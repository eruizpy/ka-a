import uuid

from fastapi.testclient import TestClient

from kaa.web import create_app


def client_for(rig):
    settings, store, _, _ = rig
    store.set_password("test-only-long-password")
    return TestClient(create_app(settings)), store


def login(client):
    response = client.post("/api/login", json={"password": "test-only-long-password"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf"]}


def test_requires_login_and_hides_sensor_data(rig):
    client, _ = client_for(rig)
    assert client.get("/api/status").status_code == 401
    assert client.get("/").status_code == 200
    assert client.post("/api/login", json={"password": "incorrect"}).status_code == 401


def test_csrf_origin_and_session_expiry(rig):
    client, _ = client_for(rig)
    headers = login(client)
    assert client.post("/api/control/arm").status_code == 403
    assert (
        client.post(
            "/api/control/arm", headers={**headers, "Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert client.post("/api/control/arm", headers=headers).status_code == 200
    assert client.post("/api/logout", headers=headers).status_code == 200
    assert client.get("/api/status").status_code == 401


def test_profile_water_and_stop_flow(rig):
    client, store = client_for(rig)
    headers = login(client)
    status = client.get("/api/status").json()
    assert status["mode"] == "simulation"
    assert len(status["plants"]) == 2
    p = status["plants"][0]
    assert (
        client.patch(
            f"/api/plants/{p['id']}",
            headers=headers,
            json={
                "revision": p["revision"],
                "name": "Balcony juniper",
            },
        ).status_code
        == 200
    )
    assert client.post("/api/control/arm", headers=headers).status_code == 200
    response = client.post(
        f"/api/plants/{p['id']}/water",
        headers=headers,
        json={
            "volume_ml": 1,
            "request_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert client.post("/api/control/stop", headers=headers).status_code == 200
    assert store.state()["estop"] is True
    assert store.command(response.json()["id"])["status"] == "cancelled"


def test_strict_input_validation(rig):
    client, _ = client_for(rig)
    headers = login(client)
    for volume in [-1, 0, "2", float("inf")]:
        if volume == float("inf"):
            continue
        response = client.post(
            "/api/plants/juniper-10/water",
            headers=headers,
            json={
                "volume_ml": volume,
                "request_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 422
    assert (
        client.patch(
            "/api/plants/juniper-10",
            headers=headers,
            json={
                "revision": 1,
                "pump_pin": 5,
            },
        ).status_code
        == 422
    )
