"""Shipping-method resolution for the shop.

Shipping prices are always computed server-side from the admin-configurable
:class:`orders.models.ShippingSettings`. The browser only ever submits the
shipping-method *code*; the fee is never taken from the request, so a tampered
or stale price in the checkout form can never affect the order total or the
amount sent to PayFast.
"""
from decimal import Decimal

from .models import Order, ShippingSettings


def free_delivery_status(subtotal, has_big_item=False):
    """Describe the small-items free-delivery threshold for ``subtotal``.

    Free delivery is NOT a separate shipping choice the customer picks: it is an
    automatic discount applied to Standard Delivery once the order total reaches
    the configured minimum. This helper exists so the checkout page can warn the
    customer how close they are, and so the fee calculation and that warning can
    never disagree (both read the same ``ShippingSettings`` row).

    ``has_big_item`` opts a large-item order out of the promotion. A big item
    needs separate handling and real freight cost, so an order total above the
    threshold must not silently erase that charge. Only the small-item part of
    such an order can qualify.

    Returns a dict with:
      ``qualifies``    - bool, whether Standard Delivery is now free
      ``minimum``      - the configured threshold
      ``shortfall``    - Decimal still needed (0.00 when qualifying/disabled)
      ``enabled``      - whether the promotion is active at all
      ``excluded``     - bool, why it does not apply (large item in the order)
    """
    settings = ShippingSettings.load()
    minimum = settings.free_minimum
    if not settings.free_enabled:
        return {
            "qualifies": False,
            "enabled": False,
            "minimum": minimum,
            "shortfall": Decimal("0.00"),
            "excluded": False,
        }
    qualifies = subtotal >= minimum and not has_big_item
    if qualifies:
        shortfall = Decimal("0.00")
    elif has_big_item:
        # This order can never qualify on value, so never invite the customer to
        # "spend more to qualify". The flag still explains why at checkout.
        shortfall = Decimal("0.00")
    else:
        shortfall = minimum - subtotal
    return {
        "qualifies": qualifies,
        "enabled": True,
        "minimum": minimum,
        "shortfall": shortfall,
        # Only meaningful once the order is over the minimum; below it the
        # customer is charged the full fee either way.
        "excluded": has_big_item and subtotal >= minimum,
    }


def product_delivery(product):
    """Return the delivery charge for ONE product. The single source of truth.

    Rules (no zones, no weights, no courier API):
      standard -> global standard fee
      free     -> R0.00
      custom   -> that product's own ``delivery_fee``
      big_item -> global big-item fee

    The big-item *threshold* is deliberately NOT consulted here. It is a
    reference value for the admin, and classifying by price would silently
    upgrade an expensive-but-light product to a bulky shipment. Only an explicit
    ``delivery_type`` of ``big_item`` triggers the big-item fee.

    Returns a dict with ``fee`` (Decimal), ``type`` and ``label`` so templates
    can render the same number checkout charges.
    """
    settings = ShippingSettings.load()
    kind = getattr(product, "delivery_type", "standard") or "standard"

    if kind == "free":
        fee = Decimal("0.00")
    elif kind == "custom":
        # Null-safe: a custom product with no fee saved falls back to the
        # standard fee rather than shipping for free by accident.
        fee = product.delivery_fee
        if fee is None or fee < 0:
            fee = settings.standard_fee
    elif kind == "big_item":
        fee = settings.big_item_fee
    else:
        fee = settings.standard_fee

    labels = {
        "standard": "Standard delivery",
        "free": "Free delivery",
        "custom": "Delivery",
        "big_item": "Large item delivery",
    }
    return {
        "fee": fee,
        "type": kind,
        "label": labels.get(kind, "Standard delivery"),
        "is_free": fee == Decimal("0.00"),
    }


def cart_delivery(items):
    """Return the delivery charge for a whole cart, as one predictable number.

    ``items`` is any iterable this project already produces: the cart-session
    ``cart_items()`` dicts (``{"product": ..., "qty": ...}``), bare
    ``Product`` objects, or ``(product, quantity)`` pairs. The rule is
    deliberately simple and additive per delivery class rather than per line, so
    buying three normal parts does not triple-charge delivery:

      * free products       -> R0
      * standard products   -> the global standard fee, charged ONCE
      * custom products     -> each product's own fee, summed (a product can
                               legitimately cost more to move than another)
      * big item products   -> the big-item fee, charged ONCE

    A cart of only free products delivers free. A cart with no delivered
    products at all returns None so the caller can fall back to the
    customer's chosen collection/pickup method.
    """
    settings = ShippingSettings.load()
    standard_fee = Decimal("0.00")
    big_item_fee = Decimal("0.00")
    custom_total = Decimal("0.00")
    has_standard = False
    has_big_item = False
    has_delivery = False

    for item in items:
        if item is None:
            continue
        # Accept the cart-session dicts, bare products and (product, qty) pairs
        # so callers never have to reshape their data for this function.
        if isinstance(item, dict):
            product = item.get("product")
        elif isinstance(item, (tuple, list)):
            product = item[0] if item else None
        else:
            product = getattr(item, "product", item)
        if product is None:
            continue
        info = product_delivery(product)
        kind = info["type"]
        if kind == "free":
            # A free product still counts as a delivery line; it just costs
            # nothing. It does not cancel a fee another product requires.
            has_delivery = True
            continue
        has_delivery = True
        if kind == "custom":
            custom_total += info["fee"]
        elif kind == "big_item":
            has_big_item = True
        else:
            has_standard = True

    if not has_delivery:
        return None

    if has_standard:
        standard_fee = settings.standard_fee
    if has_big_item:
        big_item_fee = settings.big_item_fee

    total = standard_fee + custom_total + big_item_fee
    return {
        "fee": total,
        "standard_fee": standard_fee,
        "custom_total": custom_total,
        "big_item_fee": big_item_fee,
        "has_big_item": has_big_item,
        "has_standard": has_standard,
        "is_free": total == Decimal("0.00"),
    }


def shipping_methods(subtotal, cart_items=None):
    """Return the shipping methods currently available for ``subtotal``.

    ``subtotal`` is the order total *before* shipping (after discounts). Each
    entry is a dict keyed by ``code``, ``label``, ``fee`` (Decimal),
    ``needs_address`` (bool) and optional ``note`` / ``location`` text used by
    the checkout template.

    Free delivery is deliberately NOT offered as its own entry. The customer
    chooses between Standard Delivery and Local Pickup; if the order total
    reaches the free-delivery minimum, Standard Delivery's fee becomes R0.00
    automatically and the checkout shows that as a warning/discount.

    When ``cart_items`` is supplied, the Standard Delivery fee starts from the
    per-product delivery configuration (:func:`cart_delivery`) instead of the
    flat global fee, so products marked Free, Custom or Big item are charged
    correctly. The automatic small-items threshold still applies on top, but
    only to the small-item part of the order: a big item fee survives it.
    """
    settings = ShippingSettings.load()
    # Per-product delivery configuration, resolved once. None means the caller
    # did not pass a cart, so the flat global standard fee is used.
    cart_info = cart_delivery(cart_items) if cart_items else None
    free = free_delivery_status(subtotal, has_big_item=bool(cart_info and cart_info["has_big_item"]))
    base_standard_fee = cart_info["fee"] if cart_info else settings.standard_fee
    methods = []
    if settings.standard_enabled:
        # One choice, one fee. The threshold discount is applied here rather than
        # offered as a separate option so the customer can never end up with two
        # delivery radios that both mean "delivery".
        if free["qualifies"]:
            fee = Decimal("0.00")
        elif free["excluded"]:
            # Order is over the small-items minimum but contains a big item:
            # waive only the small-item standard portion. The large item fee (and
            # any custom per-product fee) is real freight cost and must survive
            # the order-value threshold.
            fee = base_standard_fee - (cart_info["standard_fee"] if cart_info else Decimal("0.00"))
        else:
            fee = base_standard_fee
        if free["qualifies"] and base_standard_fee > 0:
            note = (
                f"Delivered to your address. Free delivery applied - you saved "
                f"R {base_standard_fee:,.2f}."
            )
        elif free["excluded"]:
            note = (
                "Delivered to your address. Large item delivery is charged at its "
                "own fee and is not covered by the small-item free delivery offer."
            )
        elif free["enabled"] and base_standard_fee > 0:
            note = (
                f"Delivered to your address. Add R {free['shortfall']:,.2f} to your "
                f"cart for free delivery."
            )
        else:
            note = "Delivered to your address."
        methods.append(
            {
                "code": Order.ShippingMethod.STANDARD,
                "label": Order.ShippingMethod.STANDARD.label,
                "fee": fee,
                "standard_fee": settings.standard_fee,
                "base_fee": base_standard_fee,
                "delivery_info": cart_info,
                "free_applied": free["qualifies"],
                "needs_address": True,
                "note": note,
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
                "note": settings.pickup_instructions,
            }
        )
    return methods


def resolve_shipping_method(code, subtotal, default="pickup", cart_items=None):
    """Return the method dict for ``code``, or fall back safely.

    ``default`` is used when ``code`` is missing or no longer available for the
    given ``subtotal``. When nothing is available at all, ``None`` is returned and
    the caller decides how to proceed. Any price in a submitted payload is
    ignored - the fee comes from the product delivery configuration and
    :class:`ShippingSettings`, both server-side.

    Free delivery used to be a distinct method code. It is now an automatic
    discount on Standard Delivery, so a stale page or a tampered POST that still
    submits the old ``free`` code is folded into Standard Delivery and re-priced
    from the server-side threshold. That way an old bookmark cannot buy free
    delivery below the minimum, and an order that does qualify still ends up
    free - both through the same code path as a fresh submission.
    """
    if code == Order.ShippingMethod.FREE:
        code = Order.ShippingMethod.STANDARD
    methods = shipping_methods(subtotal, cart_items)
    by_code = {m["code"]: m for m in methods}
    if code in by_code:
        return by_code[code]
    if default in by_code:
        return by_code[default]
    return methods[0] if methods else None