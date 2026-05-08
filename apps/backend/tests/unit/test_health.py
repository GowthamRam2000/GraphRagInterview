from fastapi.testclient import TestClient

from app.main import app


def test_healthz_is_public() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_secured_route_requires_api_key() -> None:
    client = TestClient(app)
    response = client.get("/v1/chat/ready")
    assert response.status_code == 401


def test_openapi_shows_api_key_security_lock() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "x-api-key"
    assert schema["paths"]["/v1/chat"]["post"]["security"] == [{"APIKeyHeader": []}]
    assert "security" not in schema["paths"]["/healthz"]["get"]


def test_secured_route_accepts_api_key() -> None:
    client = TestClient(app)
    response = client.get("/v1/chat/ready", headers={"x-api-key": "dev-local-auth-key"})
    assert response.status_code == 200
    assert response.json() == {"status": "chat-api-ready"}
