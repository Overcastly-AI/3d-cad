"""Service configuration — 12-factor, env-driven (CLAUDE.md conventions).

Every Loft service subclasses :class:`BaseServiceSettings` and adds its own
fields. All values come from the environment; there is no file-based config.

Deployment posture (``LOFT_ENV``) lives HERE, not in any one service: it is
the single notion of "is this a throwaway localhost stack or a real deploy?"
that both the gateway's JWT check
(:func:`gateway.auth.security.resolve_auth_config`) and the datastore
credential guard below read. One variable, one policy, three services.

The datastore guard closes an asymmetry that was real until 2026-07-30: the
gateway refused to boot without a real ``JWT_SECRET``, while NOTHING refused
to boot on the compose default ``POSTGRES_PASSWORD``/``MINIO_ROOT_PASSWORD``
— both published in this public repository. Deliberately enforced in the
APPLICATION, not in compose interpolation (``${VAR:?}``): interpolation is
evaluated per file before overlay merge, so requiring it in the base file
breaks ``just dev`` and would still only cover the compose path. This guard
covers compose, Kubernetes and a bare ``uvicorn`` alike.
"""

from typing import ClassVar, Final, Literal
from urllib.parse import unquote, urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["json", "console"]

#: The ONE value of ``LOFT_ENV`` that opts a process into dev posture. It has
#: no default anywhere: unset, or anything else (``production``, ``staging``,
#: a typo…), is treated as a real deployment, so a misspelled environment
#: name can never weaken a deployment.
DEV_ENV: Final = "dev"

#: Credentials that must never protect a real datastore, compared
#: case-insensitively after stripping. The first two are this repo's own
#: compose defaults (docker-compose.yml, .env.example) and are therefore
#: known to every reader of a public repository; the rest are vendor/universal
#: defaults of the same character. Deliberately a short, defensible list — it
#: catches "the operator changed nothing", not "the operator chose badly"
#: (password strength is not something a startup check can judge).
KNOWN_DEV_CREDENTIALS: Final[frozenset[str]] = frozenset(
    {
        "loft-dev-only",  # docker-compose.yml POSTGRES_PASSWORD default
        "loft-minio-dev-only",  # docker-compose.yml MINIO_ROOT_PASSWORD default
        "minioadmin",  # MinIO's own published default
        "postgres",
        "password",
        "changeme",
    }
)

#: Datastore URL fields whose embedded userinfo password the guard inspects.
_DATASTORE_URL_FIELDS: Final = ("postgres_url", "redis_url", "s3_url")

#: Where an operator actually sets the offending value when running compose,
#: for fields whose env var is not itself the knob they edit. Keyed by field.
_COMPOSE_SOURCE: Final[dict[str, str]] = {
    "postgres_url": "POSTGRES_PASSWORD",
    "s3_secret_access_key": "MINIO_ROOT_PASSWORD",
}


def is_dev_env(loft_env: str | None) -> bool:
    """True iff *loft_env* is the exact, explicitly-set dev opt-in."""
    return loft_env == DEV_ENV


def url_credential(url: str) -> str | None:
    """The password embedded in *url*'s userinfo, or ``None`` if there is none.

    A URL with no password at all is not a defect: peer/IAM/trust auth and
    credentials supplied out of band are legitimate. Only a password that IS
    present gets judged. Percent-escapes are decoded, so an encoded blank
    (``:%20@``) is seen as the blank it is.
    """
    try:
        password = urlsplit(url).password
    except ValueError:  # unparseable netloc — nothing to vouch for either way
        return None
    return None if password is None else unquote(password)


def credential_defect(credential: str | None) -> str | None:
    """Describe why *credential* is unfit for a real deploy, else ``None``.

    ``None`` in means "not configured" (out in). An empty/whitespace-only
    value, by contrast, means the operator DID wire the variable and left it
    blank — a passwordless datastore — which is a defect.
    """
    if credential is None:
        return None
    value = credential.strip()
    if not value:
        return "an empty/whitespace-only password (a passwordless datastore)"
    if value.lower() in KNOWN_DEV_CREDENTIALS:
        return "a publicly-known default password"
    return None


class BaseServiceSettings(BaseSettings):
    """Base settings shared by all Loft services.

    Env vars map 1:1 to field names (``SERVICE_NAME``, ``LOG_LEVEL``,
    ``LOG_FORMAT``, ``PORT``, ``LOFT_ENV``, ``REDIS_URL``, ``POSTGRES_URL``,
    ``S3_URL``). The infrastructure URLs are optional — a service opts in by
    setting the variable; py-kit itself never requires them.

    Constructing settings whose datastore credentials are publicly-known
    defaults raises :class:`RuntimeError` unless ``LOFT_ENV=dev``; see
    :meth:`_reject_dev_datastore_credentials` and the module docstring.
    """

    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "loft-service"
    log_level: str = "INFO"
    log_format: LogFormat = "json"
    port: int = 8000

    # Deployment posture — NO default, fail-closed (env: LOFT_ENV). ONLY the
    # explicitly-set exact value ``dev`` opts into insecure local shortcuts:
    # the gateway's repo-public JWT fallback secret, and the publicly-known
    # datastore credentials the guard below otherwise refuses to boot on.
    # Unset, or anything else, is treated as a real deployment.
    loft_env: str | None = None

    # Infrastructure endpoints — optional, opt-in per service.
    redis_url: str | None = None
    postgres_url: str | None = None
    s3_url: str | None = None

    #: Credential-bearing fields BEYOND the datastore URLs that the
    #: dev-credential guard should also inspect — e.g. geometry's
    #: ``s3_secret_access_key``, which carries the MinIO root password outside
    #: any URL. Subclasses override with their own field names; the guard
    #: reports the env var (the field name, upper-cased).
    datastore_credential_fields: ClassVar[tuple[str, ...]] = ()

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

    # Prometheus exposition (py_kit.metrics) — wired by the app factory, so
    # every service exports the same metrics under the same names and posture.
    # ``METRICS_ENABLED=false`` removes the middleware AND the route: no
    # per-request cost at all, not merely an unread counter.
    metrics_enabled: bool = True  # env: METRICS_ENABLED
    # Bearer token guarding ``/metrics`` OUTSIDE dev. Same fail-closed shape as
    # ``JWT_SECRET`` and the datastore guard above, off the same ``LOFT_ENV``:
    # under ``LOFT_ENV=dev`` the endpoint is open (a localhost stack should just
    # work); anywhere else an unset token means ``/metrics`` answers 404, so a
    # real deployment never publishes its internals by accident. Deliberately a
    # SHARED SECRET rather than a loopback allowlist — behind the reverse proxy
    # a self-hoster terminates TLS with, every request arrives from 127.0.0.1,
    # so an IP check would look careful while serving the public internet.
    metrics_token: str | None = None  # env: METRICS_TOKEN

    def _datastore_credentials(self) -> list[tuple[str, str, str | None]]:
        """``(field, env var, credential)`` triples the guard inspects."""
        found: list[tuple[str, str, str | None]] = []
        for field in _DATASTORE_URL_FIELDS:
            url: object = getattr(self, field, None)
            if isinstance(url, str):
                found.append((field, field.upper(), url_credential(url)))
        for field in self.datastore_credential_fields:
            value: object = getattr(self, field, None)
            found.append(
                (field, field.upper(), value if isinstance(value, str) else None)
            )
        return found

    @model_validator(mode="after")
    def _reject_dev_datastore_credentials(self) -> "BaseServiceSettings":
        """Fail closed on publicly-known datastore credentials outside dev.

        Mirrors the gateway's JWT posture exactly, so the two read as one
        policy: under ``LOFT_ENV=dev`` the insecure value is allowed and a
        warning logged; anywhere else it raises :class:`RuntimeError` and the
        process does not boot. Raising from ``__init__`` means there is no
        way to construct settings that a service could then serve from.
        """
        # Local import: py_kit.logging imports this module, so a module-level
        # import would be circular.
        from py_kit.logging import get_logger

        for field, env_var, credential in self._datastore_credentials():
            defect = credential_defect(credential)
            if defect is None:
                continue
            source = _COMPOSE_SOURCE.get(field)
            hint = f" (in compose this value comes from {source})" if source else ""
            if is_dev_env(self.loft_env):
                get_logger("py_kit.config").warning(
                    "dev_datastore_credential_in_use",
                    variable=env_var,
                    defect=defect,
                    hint="anyone can read this credential; localhost ONLY",
                )
                continue
            raise RuntimeError(
                f"{env_var} carries {defect}, and LOFT_ENV={self.loft_env!r} "
                f"is not {DEV_ENV!r}. Either set a real credential{hint} "
                "(generate one with `openssl rand -hex 32`) or, for LOCAL DEV "
                f"ONLY, opt into the insecure default explicitly with "
                f"LOFT_ENV={DEV_ENV}."
            )
        return self
