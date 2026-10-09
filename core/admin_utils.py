"""Admin resilience helpers.

``safe_display`` wraps an individual, non-critical admin display method so an
unexpected value or display-formatting mistake on one row cannot take down an
entire changelist or changeform. The failure is logged with the model, method
and object primary key and a neutral "—" is returned instead.

Only *display* methods are meant to use this. Genuine application errors are
never swallowed: database errors, permission denials and configuration errors
are re-raised so saving products, price calculations, payments and orders keep
failing loudly. Do not wrap business logic, form validation, admin actions or
model ``save()`` with this decorator.
"""
import functools
import logging

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import DatabaseError

logger = logging.getLogger(__name__)

# Errors that indicate a real application problem and must propagate rather
# than appear as a cosmetic "—" in an admin table.
_RE_RAISE = (DatabaseError, PermissionDenied, ImproperlyConfigured)


def fmt_money(value, empty="—"):
    """Return a display string for a numeric price.

    Numbers are formatted before any HTML markup is applied (never handed a
    ``SafeString`` into a numeric format spec). Absent or non-numeric values
    degrade to ``empty`` / their string form instead of raising.
    """
    if value is None:
        return empty
    try:
        return f"R {value:,.2f}"
    except (TypeError, ValueError):
        return str(value)


def safe_display():
    """Decorator guarding a single non-critical admin display method.

    Usage::

        @safe_display()
        @admin.display(description="Sale price")
        def sale_price_display(self, obj):
            ...

    On an unexpected display/formatting ``Exception`` the full traceback is
    logged (model, method, object pk) and ``"—"`` is returned. ``DatabaseError``,
    ``PermissionDenied`` and ``ImproperlyConfigured`` are re-raised untouched.
    """
    def decorator(method):
        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            self = args[0] if args else None
            obj = args[1] if len(args) > 1 else kwargs.get("obj")
            try:
                return method(*args, **kwargs)
            except _RE_RAISE:
                raise
            except Exception:
                model_name = type(obj).__name__ if obj is not None else "?"
                pk = getattr(obj, "pk", None)
                logger.exception(
                    "Admin display %s failed for %s (model=%s pk=%s); rendering fallback.",
                    method.__name__,
                    type(self).__name__ if self is not None else "?",
                    model_name,
                    pk,
                )
                return "—"

        return wrapper

    return decorator