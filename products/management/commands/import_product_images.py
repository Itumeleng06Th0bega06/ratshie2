"""Import product images from a CSV or JSON file of image URLs.

Usage:
    python manage.py import_product_images path/to/images.csv [--match sku] [--dry-run] [--keep-existing]

Input (CSV):
    sku,image_url,alt_text,source_url
    BOSCH-OIL-001,https://example.com/i.jpg,Bosch Oil Filter,https://example.com/p/1

Input (JSON):
    [{"sku": "...", "image_url": "...", "alt_text": "...", "source_url": "..."}]

Behaviour
    * Matches the image to a product by SKU (default) or slug/name (--match).
    * Downloads the image locally into media/products/gallery/ (never hotlinked).
    * Validates the download is a real image (rejects broken URLs, HTML/login
      responses, and unsupported formats).
    * Optimises to WebP for fast, small delivery.
    * Preserves the original source URL and generates a safe filename.
    * Marks the imported image as PENDING until reviewed in Django Admin.
    * By default, replaces a product's non-VERIFIED placeholder images and never
      overwrites an existing VERIFIED image (use --keep-existing to disable the
      placeholder cleanup, or --dry-run to preview).
"""

import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from PIL import Image, UnidentifiedImageError

from products.models import Product, ProductImage

USER_AGENT = "ratshie-demo-catalog/1.0 (image import; contact site admin)"
MAX_SIDE = 1200
WEBP_QUALITY = 82
MAX_DOWNLOAD = 20 * 1024 * 1024  # 20 MB safety cap

_REQUIRED = ("image_url",)
_SAFE_NAME = re.compile(r"[^a-z0-9]+")


def _fetch(url):
    """Download bytes; return (bytes, final_url, content_type) or raise ValueError."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urllib.request.urlopen(req, timeout=45)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise ValueError(f"download failed: {exc}") from exc

    final_url = resp.geturl()
    content_type = (resp.headers.get("Content-Type") or "").lower()
    size = resp.headers.get("Content-Length")
    if size and int(size) > MAX_DOWNLOAD:
        raise ValueError(f"file too large ({int(size)//1024} KB)")

    if "text/html" in content_type or "text/plain" in content_type:
        # Could be a login / error page; peek to confirm.
        head = resp.read(1024)
        low = head.lower()
        if b"<!doctype" in low or b"<html" in low or b"login" in low or b"sign" in low:
            raise ValueError("response is HTML (likely a login/error page), not an image")
        # Not obviously HTML but also not an image -> reject.
        raise ValueError(f"unsupported content type: {content_type}")
    if "login" in final_url.lower() or "signin" in final_url.lower():
        raise ValueError("redirected to a login page")

    data = resp.read()
    if not data:
        raise ValueError("empty response")
    if len(data) > MAX_DOWNLOAD:
        raise ValueError(f"file too large ({len(data)//1024} KB)")
    return data, final_url, content_type


def _validate_image(raw):
    """Decode raw bytes as an image; returns a PIL Image, raising on failure."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"not a valid image ({exc})") from exc
    return img


def _to_webp_bytes(img):
    """Resize + convert an opened image to optimised WebP bytes."""
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buf.getvalue()


def _safe_path(sku, index):
    base = _SAFE_NAME.sub("-", slugify(sku or f"product-{index}")).strip("-")[:60] or f"product-{index}"
    fname = f"products/gallery/{base}-{index}.webp"
    existing = default_storage.exists(fname)
    n = index
    while existing:
        n += 1
        fname = f"products/gallery/{base}-{n}.webp"
        existing = default_storage.exists(fname)
    return fname


def _resolve(product_qs, match, identifier):
    if match == "slug":
        return product_qs.filter(slug=identifier).first()
    if match == "name":
        return product_qs.filter(name__iexact=identifier).first()
    return product_qs.filter(sku=identifier).first()


class Command(BaseCommand):
    help = "Import product images from a CSV/JSON file of image URLs (matched by SKU)."

    def add_arguments(self, parser):
        parser.add_argument("input_file", help="Path to a .csv or .json file of image rows")
        parser.add_argument(
            "--match",
            choices=("sku", "slug", "name"),
            default="sku",
            help="Which product field to match identifiers against (default: sku)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Validate/plan without downloading or saving")
        parser.add_argument(
            "--keep-existing",
            action="store_true",
            help="Do not remove a product's non-VERIFIED placeholder images before importing (default removes them)",
        )

    def handle(self, *args, **options):
        path = options["input_file"]
        if not os.path.exists(path):
            raise CommandError(f"File not found: {path}")

        rows = self._load_rows(path)
        if not rows:
            self.stdout.write("No rows found in file.")
            return

        match = options["match"]
        dry = options["dry_run"]
        keep = options["keep_existing"]
        products = {p.id: p for p in Product.objects.filter(is_active=True)}

        created = 0
        errors = []

        for idx, row in enumerate(rows, start=1):
            ident = (row.get("sku") or row.get("slug") or row.get("name") or "").strip()
            url = (row.get("image_url") or "").strip()
            if not ident:
                errors.append(f"row {idx}: no identifier (need sku/slug/name)")
                continue
            if not url:
                errors.append(f"row {idx} ({ident}): no image_url")
                continue
            if not url.lower().startswith(("http://", "https://")):
                errors.append(f"row {idx} ({ident}): unsupported URL scheme: {url}")
                continue

            product = _resolve(Product.objects.filter(is_active=True), match, ident)
            if product is None:
                errors.append(f"row {idx}: no product matched for '{ident}' ({match})")
                continue

            if dry:
                self.stdout.write(f"[dry] would import {url} -> {product.name}")
                continue

            alt_text = (row.get("alt_text") or product.name).strip()[:160]
            source_url = (row.get("source_url") or url).strip()
            image_source = f"Imported file: {os.path.basename(url.split('?')[0])}"

            try:
                raw, _, _ = _fetch(url)
                img = _validate_image(raw)
                webp = _to_webp_bytes(img)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"row {idx} ({ident}): {exc}")
                continue

            final_path = _safe_path(product.sku or product.slug, created + 1)
            default_storage.save(final_path, io.BytesIO(webp))

            if not keep:
                # Remove non-VERIFIED (placeholder / pending / rejected) images so
                # they get replaced by this verified-review candidate. Never touch VERIFIED.
                for old in set(product.images.exclude(status=ProductImage.Status.VERIFIED)):
                    try:
                        if old.image and old.image.name and default_storage.exists(old.image.name):
                            default_storage.delete(old.image.name)
                    except Exception:  # noqa: BLE001
                        pass
                    old.delete()

            ProductImage.objects.create(
                product=product,
                image=final_path,
                alt_text=alt_text,
                image_source=image_source,
                source_url=source_url,
                status=ProductImage.Status.PENDING,
                sort_order=0,
                is_primary=not product.images.filter(is_primary=True).exists()
                or not product.verified_primary_image,
            )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"V {product.name}: imported PENDING -> {final_path}"))

        self.stdout.write(f"\n{created} image(s) imported as PENDING, {len(errors)} row(s) had errors.")
        for e in errors:
            self.stdout.write(self.style.ERROR(f"  ! {e}"))

    def _load_rows(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data = data.get("products", data.get("images", []))
            return [dict(r) for r in data]
        if ext in (".csv", ".txt"):
            rows = []
            with open(path, "r", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    rows.append({k: (v or "") for k, v in row.items()})
            return rows
        raise CommandError(f"Unsupported file type: {ext} (use .csv or .json)")
