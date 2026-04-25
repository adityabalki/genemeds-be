from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="genemeds-auth", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    db_secret_name: str = Field(default="dev/genmeds/dbsecrets", alias="DB_SECRET_NAME")
    api_secret_name: str = Field(default="dev/genmeds/api", alias="API_SECRET_NAME")
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiry_minutes: int = Field(default=60, alias="JWT_EXPIRY_MINUTES")
    allowed_origins_raw: str = Field(default="http://localhost:5173", alias="ALLOWED_ORIGINS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins_raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
