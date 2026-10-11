"""Seed a real stock quantity for products whose quantity is unknown.

The stock badge and buyability are derived from ``Product.stock``. This command
exists for the one-time case where a catalogue was created before quantities
were tracked (so rows sit at the default ``0`` and would otherwise read as Out
of Stock). It never runs on its own: an operator must pass the real starting
quantity, because inventing inventory silently is exactly what we must avoid.

Examples
--------
    # Set every product currently at 0 to 10 units.
    python manage.py backfill_stock --stock 10

    # Preview what would change, without writing.
    python manage.py backfill_stock --stock 10 --dry-run

    # Push every product to a known quantity (use with care).
    python manage.py backfill_stock --stock 25 --all
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.models import Product


class Command(BaseCommand):
    help = (
        "Set a real starting stock quantity for products with unknown stock "
        "(default: only products currently at 0)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stock",
            type=int,
            required=True,
            help="The real starting quantity to assign. Must be 1 or more.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Apply to every product, not just those currently at 0.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        stock = options["stock"]
        if stock <= 0:
            raise CommandError(
                "--stock must be 1 or more. Use the admin to mark a product "
                "Out of Stock (set 0) deliberately."
            )

        qs = Product.objects.all() if options["all"] else Product.objects.filter(stock=0)
        targets = list(qs.order_by("pk"))
        if not targets:
            self.stdout.write(self.style.SUCCESS("Nothing to do: no matching products."))
            return

        label = "every product" if options["all"] else "products with stock=0"
        self.stdout.write(f"Would set {len(targets)} {label} to stock={stock}.")

        if options["dry_run"]:
            for p in targets[:50]:
                self.stdout.write(f"  - {p.name} (currently {p.stock})")
            self.stdout.write(self.style.WARNING("Dry run: nothing written."))
            return

        with transaction.atomic():
            for product in targets:
                product.stock = stock
                product.save(update_fields=["stock", "availability", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(f"Updated {len(targets)} product(s) to stock={stock}.")
        )
