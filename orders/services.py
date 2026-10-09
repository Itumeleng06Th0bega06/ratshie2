"""Delivery pricing for the shop.

Every online order is delivered to the customer's address and is charged one
flat fee, configured by the admin in :class:`orders.models.ShippingSettings`.
The fee is always resolved server-side; the browser never submits a price, so a
tampered or stale amount in the checkout form can never affect the order total
or the amount sent to PayFast.
"""
from decimal import Decimal

from .models import ShippingSettings


def delivery_fee():
    """Return the single, admin-configured flat delivery fee."""
    return ShippingSettings.load().standard_fee


def cart_has_items(items):
    """Return True when ``items`` contains at least one product.

    Accepts the several shapes this project already produces: the cart-session
    ``cart_items()`` dicts (``{"product": ..., "qty": ...}``), bare ``Product``
    objects, or ``(product, quantity)`` pairs.
    """
    for item in items:
        if item is None:
            continue
        if isinstance(item, dict):
            product = item.get("product")
        elif isinstance(item, (tuple, list)):
            product = item[0] if item else None
        else:
            product = getattr(item, "product", item)
        if product is not None:
            return True
    return False


def cart_delivery(items):
    """Return the delivery charge for a cart, or ``None`` when it is empty.

    Kept as a single helper so the checkout page and the order-creation code
    read the same number. A ``None`` result means "nothing to deliver" and lets
    the caller fall back safely; a dict is always the flat :func:`delivery_fee`.
    """
    if not cart_has_items(items):
        return None
    fee = delivery_fee()
    return {
        "fee": fee,
        "is_free": fee == Decimal("0.00"),
    }
