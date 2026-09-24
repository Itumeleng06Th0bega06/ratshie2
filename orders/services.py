"""Shipping-method resolution for the shop.

Shipping prices are always computed server-side from the admin-configurable
:class:`orders.models.ShippingSettings`. The browser only ever submits the
shipping-method *code*; the fee is never taken from the request, so a tampered
or stale price in the checkout form can never affect the order total or the
amount sent to PayFast.
"""
from decimal import Decimal

from .models import Order, ShippingSettings


def shipping_methods(subtotal):
    """Return the shipping methods currently available for ``subtotal``.

    ``subtotal`` is the order total *before* shipping (after discounts). Each
    entry is a dict keyed by ``code``, ``label``, ``fee`` (Decimal),
    ``needs_address`` (bool) and optional ``note`` / ``location`` text used by
    the checkout template.
    """
    settings = ShippingSettings.load()
    methods = []
    if settings.standard_enabled:
        methods.append(
            {
                "code": Order.ShippingMethod.STANDARD,
                "label": Order.ShippingMethod.STANDARD.label,
                "fee": settings.standard_fee,
                "needs_address": True,
                "note": "Delivered to your address.",
            }
        )
    if settings.free_enabled and subtotal >= settings.free_minimum:
        methods.append(
            {
                "code": Order.ShippingMethod.FREE,
                "label": Order.ShippingMethod.FREE.label,
                "fee": Decimal("0.00"),
                "needs_address": True,
                "note": f"Free on orders of R {settings.free_minimum:,.2f} or more.",
            }
        )
    if settings.pickup_enabled:
        methods.append(
            {
                "code": Order.ShippingMethod.PICKUP,
                "label": Order.ShippingMethod.PICKUP.label,
                "fee": Decimal("0.00"),
                "needs_address": False,
                "location": settings.pickup_location,
            }
        )
    return methods


def resolve_shipping_method(code, subtotal, default="pickup"):
    """Return the method dict for ``code``, or fall back safely.

    ``default`` is used when ``code`` is missing or no longer available for the
    given ``subtotal`` (e.g. free delivery no longer qualifying). When nothing
    is available at all, ``None`` is returned and the caller decides how to
    proceed. Any price in a submitted payload is ignored - the fee comes from
    :class:`ShippingSettings`.
    """
    methods = shipping_methods(subtotal)
    by_code = {m["code"]: m for m in methods}
    if code in by_code:
        return by_code[code]
    if default in by_code:
        return by_code[default]
    return methods[0] if methods else None