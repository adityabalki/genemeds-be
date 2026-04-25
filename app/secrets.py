from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from typing import Any

import boto3

from app.config import get_settings


class SecretProvider:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = boto3.client("secretsmanager", region_name=settings.aws_region)
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._ttl_seconds = int(os.environ.get("SECRET_CACHE_TTL_SECONDS", "300"))

    def get_secret(self, secret_name: str) -> dict[str, Any]:
        now = time.time()
        cached = self._cache.get(secret_name)
        if cached and (now - cached[1]) < self._ttl_seconds:
            return cached[0]

        response = self._client.get_secret_value(SecretId=secret_name)
        secret_string = response.get("SecretString")
        if not secret_string:
            raise RuntimeError(f"Secret '{secret_name}' is empty.")
        parsed = json.loads(secret_string)
        self._cache[secret_name] = (parsed, now)
        return parsed


@lru_cache(maxsize=1)
def get_secret_provider() -> SecretProvider:
    return SecretProvider()
