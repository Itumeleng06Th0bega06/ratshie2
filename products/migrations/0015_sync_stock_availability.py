"""Make the stored ``availability`` agree with the real stock quantity.

The storefront badge and buyability are now derived from ``Product.stock``.
``availability`` is kept only as a legacy label, so this migration brings
existing rows in line with the automatic rule:

    * ``stock >= 10`` -> ``in_stock``   (no customer badge)
    * ``1 <= stock <= 9`` -> ``limited`` (Limited Stock)
    * ``stock == 0`` -> ``out_of_stock`` (Out of Stock)

It is deliberately conservative about *inventory*: it never changes any
``stock`` value and never invents a starting quantity. Existing quantities are
preserved exactly. Rows whose quantity was already 0 but which had been marked
available are reported (but left at 0) so the shop owner can decide whether to
restock them with real numbers.
"""
from django.db import migrations


def sync_availability(apps, schema_editor):
    Product = apps.get_model("products", "Product")

    available_values = ("in_stock", "limited", "backorder")

    # Products that will change from "available" to "out of stock" because the
    # quantity is 0. We report these loudly rather than guessing a quantity.
    stranded = Product.objects.filter(stock=0, availability__in=available_values)
    stranded_count = stranded.count()
    if stranded_count:
        print(
            f"\n  WARNING: {stranded_count} product(s) have stock=0 but were "
            "marked available. They are now Out of Stock (quantity is the "
            "source of truth). Set a real quantity in the admin, or run "
            "`manage.py backfill_stock --stock <N> --only-zero` to seed them."
        )
        for name in stranded.values_list("name", flat=True)[:20]:
            print(f"    - {name}")

    # In Stock: 10 or more.
    Product.objects.filter(stock__gte=10).update(availability="in_stock")
    # Limited Stock: 1-9.
    Product.objects.filter(stock__gte=1, stock__lte=9).update(availability="limited")
    # Out of Stock: 0.
    Product.objects.filter(stock__lte=0).update(availability="out_of_stock")


def noop_reverse(apps, schema_editor):
    """No reverse: the derived availability is safe to leave in place."""


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0014_product_delivery_fee_product_delivery_type'),
    ]

    operations = [
        migrations.RunPython(sync_availability, noop_reverse),
    ]
