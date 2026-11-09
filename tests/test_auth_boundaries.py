from test_api import client_for, login


def test_nonfinite_request_returns_validation_error_without_echoing_input(rig):
    client, _ = client_for(rig)
    headers = login(client)
    response = client.post(
        "/api/plants/juniper-10/water",
        headers={**headers, "Content-Type": "application/json"},
        content='{"volume_ml": NaN, "request_id": "invalid"}',
    )
    assert response.status_code == 422
    assert "NaN" not in response.text


def test_password_validation_does_not_echo_credentials_and_host_is_restricted(rig):
    client, _ = client_for(rig)
    secret = "synthetic-password-" * 40
    response = client.post("/api/login", json={"password": secret})
    assert response.status_code == 422
    assert secret not in response.text
    assert client.get("/", headers={"Host": "untrusted.example"}).status_code == 400
