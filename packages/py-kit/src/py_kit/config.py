"""Service configuration — 12-factor, env-driven (CLAUDE.md conventions).

Every Loft service subclasses :class:`BaseServiceSettings` and adds its own
fields. All values come from the environment; there is no file-based config.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["json", "console"]


class BaseServiceSettings(BaseSettings):
    """Base settings shared by all Loft services.

    Env vars map 1:1 to field names (``SERVICE_NAME``, ``LOG_LEVEL``,
    ``LOG_FORMAT``, ``PORT``, ``REDIS_URL``, ``POSTGRES_URL``, ``S3_URL``).
    The infrastructure URLs are optional — a service opts in by setting the
    variable; py-kit itself never requires them.
    """

    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "loft-service"
    log_level: str = "INFO"
    log_format: LogFormat = "json"
    port: int = 8000

    # Infrastructure endpoints — optional, opt-in per service.
    redis_url: str | None = None
    postgres_url: str | None = None
    s3_url: str | None = None
