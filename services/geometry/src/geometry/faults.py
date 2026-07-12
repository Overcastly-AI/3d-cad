"""Belt-and-braces fault mapping for the stateless query endpoints.

The stateless query endpoints (measure, overlay) promise — in their module +
kernel docstrings — that a kernel failure "surfaces as a 422, never a 500".
The named kernel errors (``EdgeIndexError``, ``MeasureError``) already map to
clean envelopes, but a RAW OCCT/std raise from deep in the kernel (e.g. the
``BRepExtrema_DistShapeShape`` constructor on a degenerate recomputed edge, or
a ``PointOnShape1(1)`` when ``NbSolution() == 0``) would otherwise escape
uncaught and become a 500.

:func:`unexpected_query_failure` is the shared trailing ``except Exception``
mapping (CLAUDE.md DRY rule — measure AND overlay use it): it sanitizes the
kernel/OCCT detail down to the exception CLASS NAME, the same posture as the
feature dispatcher's belt-and-braces (:func:`geometry.features.evaluate._dispatch`),
so no OCCT internals ever leak into a client envelope.
"""

from py_kit.errors import ValidationApiError


def unexpected_query_failure(
    exc: Exception, *, code: str, action: str
) -> ValidationApiError:
    """A clean 422 for an *unexpected* kernel raise (never a 500).

    *action* is the verb the message uses ("measurement", "overlay"); *code*
    is the endpoint's failure code (``measure_failed``, ``overlay_failed``).
    The message carries only the exception class name — kernel/OCCT internals
    are sanitized out, exactly like the dispatcher's belt-and-braces.
    """
    return ValidationApiError(
        f"The {action} could not be completed (unexpected "
        f"{type(exc).__name__} in the geometry kernel).",
        code=code,
    )
