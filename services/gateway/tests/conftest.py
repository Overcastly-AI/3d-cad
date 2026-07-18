"""Suite-wide ambient env for the gateway tests.

``gateway.main`` builds a module-level ``app`` at import time, and the
fail-closed secret posture (no ``LOFT_ENV`` default) refuses to construct it
without either an explicit ``LOFT_ENV=dev`` or a real ``JWT_SECRET`` — by
design (see :mod:`gateway.auth.security`). Tests import that module, so the
suite opts into dev explicitly here, exactly like a developer shell would.
Fail-fast tests are unaffected: they pass ``loft_env=`` kwargs, which take
priority over the environment in pydantic-settings.
"""

import os

os.environ.setdefault("LOFT_ENV", "dev")
