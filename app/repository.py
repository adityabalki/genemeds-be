from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.errors import UniqueViolation

from app.db import get_connection


class DuplicateResourceError(Exception):
    pass


@dataclass(frozen=True)
class RoleConfig:
    schema: str
    table: str
    role: str
    id_column: str = "id"

    @property
    def qualified_table(self) -> str:
        return f"{self.schema}.{self.table}"


ROLE_CONFIGS: dict[str, RoleConfig] = {
    "admin": RoleConfig(schema="core", table="admins", role="Admin"),
    "hcp": RoleConfig(schema="core", table="hcps", role="HCP"),
    "receptionist": RoleConfig(schema="core", table="receptionists", role="Receptionist"),
    "lab": RoleConfig(schema="core", table="labs", role="Lab"),
    "patient": RoleConfig(schema="core", table="patients", role="Patient"),
}


def fetch_user_by_email(role_key: str, email: str) -> dict[str, Any] | None:
    config = ROLE_CONFIGS[role_key]
    query = (
        f"SELECT {config.id_column} AS id, email, password_hash "
        f"FROM {config.qualified_table} WHERE email = %(email)s"
    )
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, {"email": email.lower()})
            return cursor.fetchone()


def insert_user(role_key: str, payload: dict[str, Any]) -> int:
    config = ROLE_CONFIGS[role_key]
    columns = list(payload.keys())
    placeholders = ", ".join(f"%({column})s" for column in columns)
    sql = (
        f"INSERT INTO {config.qualified_table} ({', '.join(columns)}) "
        f"VALUES ({placeholders}) RETURNING {config.id_column}"
    )
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, payload)
                inserted = cursor.fetchone()
            connection.commit()
    except UniqueViolation as exc:
        raise DuplicateResourceError("A user with those details already exists.") from exc

    if not inserted:
        raise RuntimeError("Insert succeeded without returning a primary key.")
    return int(inserted["id"])
