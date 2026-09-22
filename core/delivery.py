"""Delivery-date calculation service.

All delivery estimates are calculated in BUSINESS DAYS (Mon-Fri) and are
configurable through the database (SiteConfig.standard_delivery_days) rather
than hard-coded, so administrators can change the standard without a code
change.

Public holidays are supported through the optional PublicHoliday model; when
no holidays exist the calculation degrades gracefully to weekends only.
"""
from datetime import date, timedelta

from django.utils import timezone


def _holiday_dates(start, end):
    """Return a set of configured public-holiday dates in [start, end]."""
    try:
        from .models import PublicHoliday

        return set(
            PublicHoliday.objects.filter(date__gte=start, date__lte=end).values_list("date", flat=True)
        )
    except Exception:
        return set()


def add_business_days(start, days):
    """Add ``days`` business days (Mon-Fri) to ``start``.

    Weekends and configured public holidays are skipped. ``start`` itself is
    never counted as one of the business days.
    """
    days = int(days or 0)
    if days <= 0:
        return start
    end_search = start + timedelta(days=days * 3 + 14)
    holidays = _holiday_dates(start, end_search)
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() >= 5:
            continue
        if current in holidays:
            continue
        added += 1
    return current


def standard_delivery_days():
    """Return the admin-configured standard delivery period in business days."""
    try:
        from .models import SiteConfig

        return int(SiteConfig.load().standard_delivery_days or 7)
    except Exception:
        return 7


def product_delivery_window(product, order_date=None):
    """Return (from_date, to_date) for a product, or (None, None).

    ``order_date`` is the date the estimate is calculated from. Product-specific
    dates are absolute and ignore ``order_date``.
    """
    mode = getattr(product, "delivery_mode", "standard")
    if mode == "specific" and product.delivery_date_from:
        return product.delivery_date_from, product.delivery_date_from
    if mode == "range" and product.delivery_date_from and product.delivery_date_to:
        return product.delivery_date_from, product.delivery_date_to
    if mode == "standard":
        start = order_date or timezone.localdate()
        end = add_business_days(start, standard_delivery_days())
        return start, end
    return None, None


def order_delivery_window(order, order_date=None):
    """Return the order window using the latest product window.

    If the order contains multiple products, the latest delivery date range
    applies. Falls back to the global standard when no product windows are found.
    """
    base = order_date or (order.created_at.date() if order.created_at else timezone.localdate())
    windows = []
    for item in order.items.all():
        if item.product_id and item.product:
            windows.append(product_delivery_window(item.product, base))
    windows = [w for w in windows if w[0] and w[1]]
    if not windows:
        end = add_business_days(base, standard_delivery_days())
        return base, end
    latest_from = max(w[0] for w in windows)
    latest_to = max(w[1] for w in windows)
    if latest_to < latest_from:
        latest_to = latest_from
    return latest_from, latest_to


def format_delivery_estimate(from_date, to_date=None):
    """Human-friendly delivery estimate display string.

    Returns e.g. ``"18 September 2026"`` or ``"18–22 September 2026"``.
    Day numbers use ``.day`` (no platform-dependent ``%-d``).
    """
    if not from_date:
        return ""
    if not to_date or to_date == from_date:
        return f"{from_date.day} {from_date.strftime('%B %Y')}"
    if from_date.year == to_date.year and from_date.month == to_date.month:
        return f"{from_date.day}–{to_date.day} {from_date.strftime('%B %Y')}"
    return (
        f"{from_date.day} {from_date.strftime('%B %Y')}–"
        f"{to_date.day} {to_date.strftime('%B %Y')}"
    )