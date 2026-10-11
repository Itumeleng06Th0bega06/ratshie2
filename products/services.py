"""Central purchase-authorization rules for the shop.

Every cart / checkout / order / payment entry point must consult
:func:`can_purchase_product` before letting a visitor add or buy goods. This is
the single source of truth so sale/member restrictions are never duplicated
(and never diverged) across views.

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


def available_quantity(product):
    """Return the largest quantity of ``product`` that can be bought right now."""
    if product is None or not getattr(product, "is_available", True):
        return 0
    try:
        return max(0, int(getattr(product, "stock", 0) or 0))
    except (TypeError, ValueError):
        return 0


def clamp_quantity(product, desired):
    """Clamp ``desired`` so it never exceeds the units actually available."""
    try:
        desired = int(desired)
    except (TypeError, ValueError):
        desired = 0
    return max(0, min(desired, available_quantity(product)))


def cart_stock_errors(product_lines):
    """Return messages for cart lines whose quantity exceeds available stock.

    ``can_purchase_product`` already blocks a sold-out line; this catches the
    subtler case where a line's quantity is larger than the remaining stock, so
    the order cannot be submitted for more units than are on the shelf.
    """
    errors = []
    for line in product_lines or []:
        if isinstance(line, dict):
            p = line.get("product")
            qty = int(line.get("qty", 0) or 0)
        else:
            p = line
            qty = 1
        if p is None:
            continue
        stock = available_quantity(p)
        if qty > stock:
            if stock <= 0:
                errors.append(
                    f"“{p.name}” is out of stock. Please remove it from your cart."
                )
            elif stock == 1:
                errors.append(
                    f"Only 1 of “{p.name}” is available. Please reduce the quantity."
                )
            else:
                errors.append(
                    f"Only {stock} of “{p.name}” are available. Please reduce the quantity."
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
