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

    # Rate limiting (py_kit.ratelimit) — env-driven, sane defaults. A service
    # opts in by installing the limiter; the fields live here (the py-kit
    # settings pattern) so every service configures it the same way.
    # ``RATE_LIMIT_REQUESTS`` per ``RATE_LIMIT_WINDOW_S`` seconds per identity.
    # Default 120/60s ≈ 2 req/s sustained per authenticated user: generous for
    # interactive modeling (viewport tessellations are client-debounced, well
    # under this) yet low enough to stop a hammering loop on the OCCT-CPU
    # routes. Redis-backed, so the bound holds across workers/replicas.
    rate_limit_enabled: bool = True  # env: RATE_LIMIT_ENABLED
    rate_limit_requests: int = 120  # env: RATE_LIMIT_REQUESTS
    rate_limit_window_s: int = 60  # env: RATE_LIMIT_WINDOW_S
