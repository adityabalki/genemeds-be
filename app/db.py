from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
import logging
from typing import Generator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.secrets import get_secret_provider

_logger = logging.getLogger(__name__)
_did_log_connection_info = False


@dataclass(frozen=True)
class DatabaseCredentials:
    host: str
    port: int
    dbname: str
    user: str
    password: str

    @classmethod
    def from_secret(cls, secret: dict[str, str]) -> "DatabaseCredentials":
        return cls(
            host=secret["DB_HOST"],
            port=int(secret["PORT"]),
            dbname=secret["DB_NAME"],
            user=secret["DB_USER"],
            password=secret["DB_PASSWORD"],
        )

    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password} sslmode=require"
        )


@lru_cache(maxsize=1)
def get_db_credentials() -> DatabaseCredentials:
    settings = get_settings()
    secret = get_secret_provider().get_secret(settings.db_secret_name)
    return DatabaseCredentials.from_secret(secret)


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    credentials = get_db_credentials()
    return ConnectionPool(
        conninfo=credentials.dsn(),
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=4,
        open=False,
        timeout=10,
    )


@contextmanager
def get_connection() -> Generator[Connection, None, None]:
    global _did_log_connection_info
    pool = get_pool()
    if pool.closed:
        pool.open(wait=True)
    with pool.connection() as connection:
        if not _did_log_connection_info:
            _did_log_connection_info = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "select current_database() as db, current_user as usr, "
                        "inet_server_addr() as ip, inet_server_port() as port, "
                        "to_regclass('core.hcps') as core_hcps"
                    )
                    row = cursor.fetchone()
                _logger.info("db_connection_info", extra={"db": row})
            except Exception:
                _logger.exception("db_connection_info_failed")
        yield connection
