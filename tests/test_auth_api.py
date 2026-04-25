from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthcheck():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_hcp_register_success(monkeypatch):
    def fake_register(role_key, payload):
        assert role_key == "hcp"
        assert payload["email"] == "doctor@example.com"
        return {
            "message": "Registration successful.",
            "status": "success",
            "role": "HCP",
            "redirect_to": "/registration-success",
            "user_id": 101,
        }

    monkeypatch.setattr("app.routers.auth.register_user", fake_register)

    response = client.post(
        "/auth/hcp/register",
        json={
            "full_name": "Dr Test",
            "email": "doctor@example.com",
            "password": "Secret123",
            "mobile": "9876543210",
            "degree": "MBBS",
            "specialisation": "Cardiology",
            "experience": "7",
            "hospital": "Genemeds",
            "registration_number": "REG001",
            "council": "KMC",
            "registration_year": "2020",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "success"


def test_lab_register_validation_error():
    response = client.post(
        "/auth/lab/register",
        json={
            "lab_name": "Central Lab",
            "contact_person": "Alex",
            "email": "lab@example.com",
            "mobile": "123",
            "password": "Secret123",
            "license_id": "LIC001",
            "address": "Street",
            "city": "Bengaluru",
            "state": "KA",
            "pincode": "560001",
        },
    )

    assert response.status_code == 422


def test_patient_login_success(monkeypatch):
    def fake_authenticate(role_key, email, password):
        assert role_key == "patient"
        assert email == "patient@example.com"
        assert password == "Secret123"
        return {
            "access_token": "signed-token",
            "token_type": "bearer",
            "message": "Login successful.",
            "role": "Patient",
            "redirect_to": "/login-success",
            "user_id": 4,
        }

    monkeypatch.setattr("app.routers.auth.authenticate_user", fake_authenticate)

    response = client.post(
        "/auth/patient/login",
        json={"email": "patient@example.com", "password": "Secret123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "signed-token"
    assert response.json()["redirect_to"] == "/login-success"
