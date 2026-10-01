from fastapi.testclient import TestClient

from src.api import app


def test_api_health_returns_ok_and_llm_mode():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_mode"] in ("recorded", "live")


def test_settings_default_utc_offset_is_read_from_the_environment(monkeypatch):
    from datetime import timedelta

    from src.settings import load_settings

    monkeypatch.setenv("DEFAULT_UTC_OFFSET", "-05:30")
    assert load_settings().default_utc_offset.utcoffset(None) == -timedelta(hours=5, minutes=30)
    monkeypatch.delenv("DEFAULT_UTC_OFFSET")
    assert load_settings().default_utc_offset.utcoffset(None) == timedelta(hours=8)
