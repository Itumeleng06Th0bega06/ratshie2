"""Attach curated, visually verified product images to Products.

This is the counterpart to `import_product_images`, which fetches unverified
images from URLs and leaves them PENDING. Every image handled here has already
been downloaded and reviewed by eye against the product it will be shown for,
so it is written as VERIFIED (the only status the public storefront renders).

It deliberately does NOT scrape or hotlink anything. The manifest is a fixed,
reviewed set of freely licensed files from Wikimedia Commons, and the licence
plus the source page are recorded on the ProductImage row so attribution can be
given.

Usage:
    python manage.py attach_verified_product_images manifest.json [--dry-run]
    python manage.py attach_verified_product_images manifest.json --report

Manifest (JSON list):
    [
      {
        "sku": "RSH-...",                 # required, matched exactly
        "file": "path/to/downloaded.jpg", # required, local file
        "alt_text": "...",
        "source": "Wikimedia Commons",
        "source_url": "https://commons.wikimedia.org/wiki/File:...",
        "licence": "CC BY-SA 4.0",
        "notes": "why this file is correct for this product"
      }
    ]

Behaviour
    * Matches by SKU only, and aborts if a SKU does not exist or if the same
      SKU appears twice in the manifest.
    * Optimises to WebP (max 1200px, quality 82) preserving aspect ratio.
    * Writes into media/products/gallery/<sku-slug>.webp via the default storage,
      so it follows whatever MEDIA_ROOT the deployment uses.
    * Re-running updates the existing VERIFIED image for that product rather
      than creating a second one.
    * Never touches product fields: the database stays the source of truth, the
      image is fitted to the product, never the other way round.
"""

import io
import json
import os
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from PIL import Image

from products.models import Product, ProductImage

# Reuse the exact optimisation and naming rules the URL importer uses, so both
# paths produce identically sized WebP assets.
from products.management.commands.import_product_images import (  # noqa: E402
    MAX_SIDE,
    WEBP_QUALITY,
    _safe_path,
    _to_webp_bytes,
    _validate_image,
)

# Product cards render at roughly 280px and the detail page at roughly 700px, so
# anything past ~900px is wasted bandwidth. High-detail photos (steel parts on
# concrete) blow past the WebP budget at 1200px/q82, so step those down rather
# than shipping 400KB+ thumbnails.
BUDGET_BYTES = 150 * 1024
SMALL_SIDE = 900
SMALL_QUALITY = 78


def _fit_to_budget(raw):
    """Return WebP bytes trimmed to a sane transfer size.

    Aspect ratio is always preserved and nothing is cropped or stretched; the
    product stays whole inside the frame. High-detail photos (steel parts shot
    on concrete) blow past the budget at full size, so step the dimensions and
    then the quality down until the file fits.
    """
    webp = _to_webp_bytes(_validate_image(raw))
    if len(webp) <= BUDGET_BYTES:
        return webp

    base = _validate_image(raw)
    if base.mode not in ("RGB", "RGBA"):
        base = base.convert("RGBA" if "A" in base.getbands() else "RGB")

    smallest = webp
    for side in (SMALL_SIDE, 800, 640):
        img = base.copy()
        img.thumbnail((side, side), Image.LANCZOS)
        for quality in (SMALL_QUALITY, 68, 58):
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=quality, method=6)
            candidate = buf.getvalue()
            if len(candidate) < len(smallest):
                smallest = candidate
            if len(candidate) <= BUDGET_BYTES:
                return candidate
    return smallest


class Command(BaseCommand):
    help = "Attach reviewed, freely licensed product images to Products by SKU."

    def add_arguments(self, parser):
        parser.add_argument("manifest", help="Path to the JSON manifest")
        parser.add_argument("--dry-run", action="store_true", help="Report without writing")
        parser.add_argument("--report", action="store_true", help="List products with no image afterwards")

    def handle(self, *args, **options):
        path = Path(options["manifest"])
        if not path.is_file():
            raise CommandError(f"manifest not found: {path}")

        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            raise CommandError("manifest must be a non-empty JSON list")

        seen = set()
        for row in rows:
            for key in ("sku", "file"):
                if not row.get(key):
                    raise CommandError(f"row missing {key!r}: {row}")
            if row["sku"] in seen:
                raise CommandError(f"duplicate SKU in manifest: {row['sku']}")
            seen.add(row["sku"])

        unknown = sorted(s for s in seen if not Product.objects.filter(sku=s).exists())
        if unknown:
            raise CommandError("no Product matches SKU(s): " + ", ".join(unknown))

        created = updated = skipped = 0
        missing_files = []

        for row in rows:
            product = Product.objects.get(sku=row["sku"])
            src = Path(row["file"])
            if not src.is_file():
                missing_files.append(row["file"])
                skipped += 1
                continue

            raw = src.read_bytes()
            try:
                webp = _fit_to_budget(raw)
            except ValueError as exc:
                self.stderr.write(f"  !! {row['sku']}: {exc}")
                skipped += 1
                continue

            if options["dry_run"]:
                verb = "would attach"
                created += 1
                note = f"{row['file']} -> {len(webp)//1024}KB"
            else:
                existing = (
                    product.images.filter(is_primary=True).first()
                    or product.images.filter(status=ProductImage.Status.VERIFIED).first()
                )
                # Reuse the filename already on disk for this product so
                # re-running overwrites in place. `_safe_path` always invents a
                # *new* name, which would orphan the previous file on every run.
                current = existing.image.name if existing and existing.image else ""
                if current and default_storage.exists(current):
                    target = current
                else:
                    target = _safe_path(product.sku, 1)
                if default_storage.exists(target):
                    default_storage.delete(target)
                target = default_storage.save(target, ContentFile(webp))
                note = f"{target} ({len(webp)//1024}KB)"

                licence = row.get("licence", "")
                notes = row.get("notes", "")
                attribution = f"Source: {row.get('source', '')} ({licence})".strip()
                if licence:
                    attribution += f". {row.get('source_url', '')}".rstrip()

                with transaction.atomic():
                    image = existing or ProductImage(product=product)
                    image.image = target
                    image.alt_text = row.get("alt_text") or product.name
                    image.image_source = attribution
                    image.source_url = row.get("source_url", "")
                    image.verification_notes = "\n".join(x for x in (licence, notes) if x)
                    image.status = ProductImage.Status.VERIFIED
                    image.is_primary = True
                    image.sort_order = 0
                    image.save()
                verb = "attached"
                created += 1

            self.stdout.write(f"  {verb} {row['sku']:<40} {note}")

        self.stdout.write(self.style.SUCCESS(
            f"\n{created} processed, {updated} updated, {skipped} skipped"
        ))
        if missing_files:
            self.stderr.write("source files not found:\n  " + "\n  ".join(missing_files))

        if options["report"]:
            with_image = Product.objects.filter(
                images__status=ProductImage.Status.VERIFIED
            ).distinct().count()
            total = Product.objects.count()
            self.stdout.write(f"\nproducts with a verified image: {with_image}/{total}")
            for p in Product.objects.exclude(
                images__status=ProductImage.Status.VERIFIED
            ).select_related("product_group").order_by("product_group__sort_order", "name"):
                self.stdout.write(f"  no image  {p.sku:<40} {p.name}")