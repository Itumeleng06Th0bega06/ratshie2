"""Central purchase-authorization rules for the shop.

Every cart / checkout / order / payment entry point must consult
:func:`can_purchase_product` (or :func:`restricted_cart_items` for a whole
cart) before letting a visitor add or buy goods. This is the single source of
truth so sale/member restrictions are never duplicated (and never diverged)
across views.

Rule (per product):
    * A product that is unavailable cannot be bought.
    * A product that is ``is_member_only`` (which on-sale products normally are)
      can only be bought by a registered, authenticated member.
    * Anonymous visitors may still view on-sale products and their prices, but
      cannot add them to a cart or complete checkout.
"""
from decimal import Decimal


def can_purchase_product(user, product):
    """Return ``(allowed: bool, reason: str|None)`` for a single product.

    ``reason`` is a short, stable machine key (``"unavailable"`` /
    ``"member_only"`` / ``"out_of_stock"``) used to decide the UI/messaging.
    """
    if not getattr(product, "is_available", True):
        return False, "unavailable"
    if not product.in_stock:
        return False, "out_of_stock"
    if product.is_member_only:
        authed = bool(user is not None and user.is_authenticated)
        if not authed:
            return False, "member_only"
    return True, None


def restricted_cart_items(user, product_pks):
    """Filter a list of product pks to those an anonymous user may not buy.

    Returns a list of the restricted product objects. Used server-side to
    reject/remove on-sale member-only items before checkout.
    """
    from products.models import Product

    products = Product.objects.filter(pk__in=product_pks)
    restricted = []
    for p in products:
        allowed, _ = can_purchase_product(user, p)
        if not allowed:
            restricted.append(p)
    return restricted


def cart_restriction_errors(user, product_lines):
    """Return a list of human messages for restricted lines in a cart.

    ``product_lines`` may be the output of ``core.utils.cart_items`` (dicts with
    a ``product`` key) or a list of ``Product`` objects.
    """
    errors = []
    for line in product_lines:
        p = line.get("product") if isinstance(line, dict) else line
        if p is None:
            continue
        allowed, reason = can_purchase_product(user, p)
        if not allowed and reason == "member_only":
            errors.append(
                f"“{p.name}” is a members-only sale product. Please sign in or register "
                "a free account to purchase it."
            )
    return errors


def line_totals(price, original_price, qty):
    """Compute line subtotal + discount used consistently in cart/checkout."""
    price = Decimal(str(price or 0))
    qty = int(qty or 0)
    line_total = price * qty
    original = original_price if original_price and original_price > price else None
    original_line = original * qty if original is not None else line_total
    discount = original_line - line_total
    return line_total, original_line, discount
