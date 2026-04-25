import pytest
from fastapi import HTTPException

from app import service


def test_authenticate_user_returns_token(monkeypatch):
    monkeypatch.setattr(
        service,
        "fetch_user_by_email",
        lambda role_key, email: {"id": 10, "email": email, "password_hash": "hashed"},
    )
    monkeypatch.setattr(service, "verify_password", lambda password, password_hash: True)
    monkeypatch.setattr(service, "create_access_token", lambda subject, role: "jwt-token")

    response = service.authenticate_user("admin", "admin@example.com", "Secret123")

    assert response["access_token"] == "jwt-token"
    assert response["role"] == "Admin"
    assert response["redirect_to"] == "/login-success"


def test_authenticate_user_rejects_invalid_credentials(monkeypatch):
    monkeypatch.setattr(service, "fetch_user_by_email", lambda role_key, email: None)

    with pytest.raises(HTTPException) as exc_info:
        service.authenticate_user("admin", "missing@example.com", "badpass")

    assert exc_info.value.status_code == 401


def test_register_user_hashes_password(monkeypatch):
    captured = {}

    monkeypatch.setattr(service, "hash_password", lambda password: "hashed-password")

    def fake_insert(role_key, payload):
        captured["role_key"] = role_key
        captured["payload"] = payload
        return 77

    monkeypatch.setattr(service, "insert_user", fake_insert)

    response = service.register_user(
        "receptionist",
        {
            "full_name": "Jane",
            "email": "JANE@EXAMPLE.COM",
            "mobile": "9876543210",
            "password": "Secret123",
            "clinic": "Clinic",
            "clinic_code": "CLN01",
        },
    )

    assert captured["role_key"] == "receptionist"
    assert captured["payload"]["email"] == "jane@example.com"
    assert captured["payload"]["password_hash"] == "hashed-password"
    assert "password" not in captured["payload"]
    assert response["redirect_to"] == "/registration-success"
