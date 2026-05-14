from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_tiktokshop_oauth_callback_accepts_auth_code():
    from backend.domains.platform.routers import tiktokshop_oauth

    app = FastAPI()
    app.include_router(tiktokshop_oauth.router)
    client = TestClient(app)

    resp = client.get("/tiktokshop/callback", params={"auth_code": "abc123", "state": "s1"})
    assert resp.status_code == 200
    assert "abc123" in resp.text


def test_tiktokshop_oauth_callback_returns_400_when_missing_code():
    from backend.domains.platform.routers import tiktokshop_oauth

    app = FastAPI()
    app.include_router(tiktokshop_oauth.router)
    client = TestClient(app)

    resp = client.get("/tiktokshop/callback")
    assert resp.status_code == 400
