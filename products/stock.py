"""Inventory deduction for confirmed orders.

Stock is reduced exactly **once**, when an order reaches the confirmed payment
stage (the verified PayFast ITN). That is deliberately later than the cart and
checkout, so simply adding items to a cart never commits inventory.

The single entry point is :func:`deduct_stock_for_order`, which is:

* **Idempotent** - an atomic compare-and-swap flips ``Order.stock_deducted``
  from ``False`` to ``True``; a duplicate ITN (or a repeated processing request)
  therefore finds the flag already set and does nothing.
* **Concurrency-safe** - the conditional decrement
  (``filter(stock__gte=qty).update(stock=F("stock") - qty)``) is evaluated by the
  database, so two buyers racing for the last unit cannot both succeed.
* **Non-negative** - if stock ran out between checkout and payment the clamp
  keeps the quantity at ``0`` and logs the shortfall instead of going negative.

Nothing here restores stock. Because deduction only ever happens after a
successful payment, a failed or cancelled payment never removed stock in the
first place, so there is nothing to restore and no way to double-restock.
"""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def _sync_availability(product_pk):
    """Keep the legacy ``availability`` column consistent with real stock."""
    from .models import Product

    stock = (
        Product.objects.filter(pk=product_pk)
        .values_list("stock", flat=True)
        .first()
    )
    if stock is None:
        return
    if stock <= 0:
        availability = "out_of_stock"
    elif stock < Product.STOCK_LIMITED_MIN:
        availability = "limited"
    else:
        availability = "in_stock"
    Product.objects.filter(pk=product_pk).update(availability=availability)


def deduct_stock_for_order(order):
    """Reduce stock for a confirmed order exactly once.

    Returns ``True`` when this call applied the deduction, ``False`` when it had
    already been applied (so the caller can tell the two apart in tests/logs).
    """
    from .models import Product

    with transaction.atomic():
        # Compare-and-swap the guard flag. The database only lets one contender
        # flip it, which makes a duplicate ITN a no-op even if the requests
        # arrive at the same instant.
        claimed = type(order).objects.filter(
            pk=order.pk, stock_deducted=False
        ).update(stock_deducted=True, stock_deducted_at=timezone.now())
        if not claimed:
            return False

        for item in order.items.select_related("product"):
            product = item.product
            qty = int(item.quantity or 0)
            if product is None or qty <= 0:
                continue

            updated = Product.objects.filter(
                pk=product.pk, stock__gte=qty
            ).update(stock=F("stock") - qty)
            if not updated:
                # The last units were bought by someone else between checkout
                # and confirmation. Never drive stock negative: clamp to zero
                # and record the shortfall for the shop owner to resolve.
                remaining = (
                    Product.objects.filter(pk=product.pk)
                    .values_list("stock", flat=True)
                    .first()
                ) or 0
                if remaining > 0:
                    Product.objects.filter(pk=product.pk).update(stock=0)
                logger.warning(
                    "Stock shortfall on order %s: product %s (%s) needed %s, "
                    "only %s left; clamped to 0.",
                    getattr(order, "reference", order.pk),
                    product.pk,
                    getattr(product, "name", ""),
                    qty,
                    remaining,
                )

            _sync_availability(product.pk)

        return True
