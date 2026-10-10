"""Delivery pricing for the shop.

Delivery is mandatory for every online order (there is no pickup option). Each
product stores how it is charged for delivery:

* ``standard`` - use the global standard fee configured by the admin in
  :class:`orders.models.ShippingSettings`.
* ``custom``   - use the product's own fee (which may be R0.00 for free
  delivery on that product).

The fee is always resolved server-side; the browser never submits a price, so a
tampered or stale amount in the checkout form can never affect the order total
or the amount sent to PayFast.

Cart rule
---------
The global standard fee is charged **once per order** when at least one product
set to the standard option is in the cart. Each **distinct** custom product then
adds its own fee (R0.00 allowed for free delivery on that product). Quantity
does **not** multiply a fee: buying three of one product is charged once, not
three times.
"""
from decimal import Decimal

from .models import ShippingSettings


def delivery_fee():
    """Return the single, admin-configured flat standard delivery fee."""
    return ShippingSettings.load().standard_fee


def product_delivery(product):
    """Return the delivery charge for ONE product - the single source of truth.

    Rules:
      standard -> the global standard fee
      custom   -> that product's own ``delivery_fee`` (R0.00 means free)

    A custom product with no fee saved falls back to the standard fee rather
    than shipping for free by accident.

    Returns a dict with ``fee`` (Decimal), ``type``, ``label`` and ``is_free``
    so templates can render the same number checkout charges.
    """
    settings = ShippingSettings.load()
    kind = getattr(product, "delivery_type", "standard") or "standard"

    if kind == "custom":
        fee = product.delivery_fee
        if fee is None or fee < 0:
            fee = settings.standard_fee
    else:
        kind = "standard"
        fee = settings.standard_fee

    labels = {
        "standard": "Standard delivery",
        "custom": "Delivery",
    }
    return {
        "fee": fee,
        "type": kind,
        "label": labels.get(kind, "Standard delivery"),
        "is_free": fee == Decimal("0.00"),
    }


def _iter_products(items):
    """Yield the product from each item, accepting every shape this project uses.

    Items may be the cart-session ``cart_items()`` dicts
    (``{"product": ..., "qty": ...}``), bare ``Product`` objects, or
    ``(product, quantity)`` pairs.
    """
    for item in items or []:
        if item is None:
            continue
        if isinstance(item, dict):
            product = item.get("product")
        elif isinstance(item, (tuple, list)):
            product = item[0] if item else None
        else:
            product = getattr(item, "product", item)
        if product is not None:
            yield product


def cart_has_items(items):
    """Return True when ``items`` contains at least one product."""
    return any(True for _ in _iter_products(items))


def cart_delivery(items):
    """Return the delivery charge for a cart, or ``None`` when it is empty.

    The standard fee is charged **once per order** if any standard product is
    present. Each **distinct** custom product adds its own fee. Repeated
    quantities of the same product are charged once.
    """
    settings = ShippingSettings.load()
    lines = []
    custom_total = Decimal("0.00")
    has_standard = False
    seen = set()
    for product in _iter_products(items):
        key = product.pk if product.pk is not None else id(product)
        if key in seen:
            continue
        seen.add(key)
        info = product_delivery(product)
        if info["type"] == "standard":
            # Any number of standard products still adds the standard fee once.
            has_standard = True
            continue
        custom_total += info["fee"]
        lines.append(
            {
                "product": product,
                "name": getattr(product, "name", ""),
                "fee": info["fee"],
                "type": info["type"],
                "label": info["label"],
                "is_free": info["is_free"],
            }
        )

    if not seen:
        return None

    total = custom_total
    if has_standard:
        standard_fee = settings.standard_fee
        total += standard_fee
        # A single standard line represents the whole order; it carries no
        # product so per-product rows do not each look like a separate charge.
        lines.insert(
            0,
            {
                "product": None,
                "name": "",
                "fee": standard_fee,
                "type": "standard",
                "label": "Standard delivery",
                "is_free": standard_fee == Decimal("0.00"),
            },
        )

    return {
        "fee": total,
        "lines": lines,
        "is_free": total == Decimal("0.00"),
    }
