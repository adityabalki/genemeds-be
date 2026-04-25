from __future__ import annotations
from fastapi import HTTPException, status
from app.repository import DuplicateResourceError, ROLE_CONFIGS, fetch_user_by_email, insert_user
from app.security import create_access_token, hash_password, verify_password


def authenticate_user(role_key: str, email: str, password: str) -> dict[str, str | int]:
    user = fetch_user_by_email(role_key, email)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    role = ROLE_CONFIGS[role_key].role
    token = create_access_token(subject=str(user["id"]), role=role)
    return {
        "access_token": token,
        "message": "Login successful.",
        "role": role,
        "redirect_to": "/login-success",
        "user_id": int(user["id"]),
    }


def register_user(role_key: str, payload: dict[str, str]) -> dict[str, str | int]:
    record = dict(payload)
    record["email"] = record["email"].lower()
    record["password_hash"] = hash_password(record.pop("password"))

    try:
        user_id = insert_user(role_key, record)
    except DuplicateResourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    role = ROLE_CONFIGS[role_key].role
    return {
        "message": "Registration successful.",
        "status": "success",
        "role": role,
        "redirect_to": "/registration-success",
        "user_id": user_id,
    }
