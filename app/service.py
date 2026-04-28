from __future__ import annotations
from fastapi import HTTPException, status
from app.db import get_connection
from app.repository import DuplicateResourceError, ROLE_CONFIGS, fetch_user_by_email, insert_user
from app.security import create_access_token, hash_password, verify_password

# table → (display_id_column, prefix, sequence_name)
_ROLE_ID_MAP: dict[str, tuple[str, str, str]] = {
    "hcp":          ("hcp_id",          "HCP", "hcp_id_seq"),
    "receptionist": ("receptionist_id", "REC", "receptionist_id_seq"),
    "lab":          ("lab_id",          "LAB", "lab_id_seq"),
    "admin":        ("admin_id",        "ADM", "admin_id_seq"),
    "patient":      ("patient_auth_id", "PAT", "patient_auth_id_seq"),
}


def _assign_display_id(role_key: str, table: str, user_id: int) -> None:
    cfg = _ROLE_ID_MAP.get(role_key)
    if not cfg:
        return
    col, prefix, seq = cfg
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE core.{table} "
                f"SET {col} = %(prefix)s || '-' || LPAD(nextval('core.{seq}')::text, 5, '0') "
                f"WHERE id = %(id)s",
                {"prefix": prefix, "id": user_id},
            )
        connection.commit()


def authenticate_user(role_key: str, email: str, password: str) -> dict[str, str | int]:
    user = fetch_user_by_email(role_key, email)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    config = ROLE_CONFIGS[role_key]
    role = config.role
    token = create_access_token(subject=str(user["id"]), role=role)
    result: dict[str, str | int | None] = {
        "access_token": token,
        "message": "Login successful.",
        "role": role,
        "redirect_to": "/login-success",
        "user_id": int(user["id"]),
    }
    for col in config.extra_cols:
        result[col] = user.get(col)
    return result


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

    config = ROLE_CONFIGS[role_key]
    _assign_display_id(role_key, config.table, user_id)

    role = config.role
    return {
        "message": "Registration successful.",
        "status": "success",
        "role": role,
        "redirect_to": "/registration-success",
        "user_id": user_id,
    }
