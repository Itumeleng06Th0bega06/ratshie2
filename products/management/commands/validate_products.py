"""Validate product images across the catalogue.

Reports each active product with, in order of severity:
    VERIFIED  -> has a valid, optimised (WebP), VERIFIED primary image that is
                 actually shown to the public.
    PENDING   -> has an image but it is not yet VERIFIED (needs visual review).
    REJECTED  -> its only image(s) are rejected.
    MISSING   -> has no image at all.

Also flags images that exist but are not optimised to WebP, and exits non-zero
if any product cannot be published (missing / not verified / invalid file).

This does NOT judge whether an image shows the correct product — only a human
visual check in Django Admin (approve -> VERIFIED) can do that.
"""

from io import BytesIO

from django.core.management.base import BaseCommand

from PIL import Image, UnidentifiedImageError

from products.models import Product, ProductImage


class Command(BaseCommand):
    help = "Report image verification status for every active product."

    def handle(self, *args, **options):
        products = (
            Product.objects.filter(is_active=True)
            .order_by("name")
            .prefetch_related("images")
        )

        verified = pending = rejected = missing = unhealthy = 0
        self.stdout.write("PRODUCT IMAGE VALIDATION")
        self.stdout.write("=" * 60)

        for p in products:
            self._report(p)
            images = list(p.images.all())
            if not images:
                missing += 1
                continue
            verified_img = next((i for i in images if i.status == ProductImage.Status.VERIFIED), None)
            if verified_img:
                checked = self._inspect(verified_img)
                if checked["valid"] and checked["optimized"]:
                    verified += 1
                else:
                    unhealthy += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"! {p.name}: VERIFIED image is missing/not optimised ({verified_img.image.name})"
                        )
                    )
                continue
            statuses = {i.status for i in images}
            if ProductImage.Status.PENDING in statuses:
                pending += 1
            else:
                rejected += 1

        total = products.count()
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(
            f"VERIFIED (published)  : {verified}\n"
            f"PENDING (need review) : {pending}\n"
            f"REJECTED only         : {rejected}\n"
            f"MISSING image         : {missing}\n"
            f"Verified but unhealthy: {unhealthy}\n"
            f"TOTAL active products : {total}"
        )
        if (pending + rejected + missing + unhealthy) > 0:
            self.stdout.write(
                self.style.WARNING(
                    "\nNot every product is publishable yet. Review PENDING/REJECTED "
                    "images in Django Admin and approve; import real image URLs with "
                    "import_product_images before launch."
                )
            )
            raise SystemExit(1)

    def _report(self, p):
        images = list(p.images.all())
        line = f"{p.name}  [{p.sku or 'NO-SKU'}]"
        if not images:
            self.stdout.write(self.style.ERROR(f"X {line}\n    Missing image"))
            return
        primary = p.public_image or p.primary_image
        if primary is None:
            self.stdout.write(self.style.ERROR(f"X {line}\n    No image"))
            return
        if primary.status == ProductImage.Status.VERIFIED:
            check = self._inspect(primary)
            if check["valid"] and check["optimized"]:
                self.stdout.write(
                    self.style.SUCCESS(f"V {line}\n    Image: {primary.image.name}\n    Status: VERIFIED")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"X {line}\n    Image: {primary.image.name}\n    Status: VERIFIED but file unhealthy")
                )
        elif primary.status == ProductImage.Status.PENDING:
            self.stdout.write(
                self.style.WARNING(f"? {line}\n    Image: {primary.image.name}\n    Status: PENDING — visual verification required")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"X {line}\n    Image: {primary.image.name}\n    Status: REJECTED")
            )
        # Note non-optimised images
        for img in images:
            if img.image and not img.is_optimized:
                self.stdout.write(
                    self.style.NOTICE(f"      (not WebP optimised: {img.image.name})")
                )

    def _inspect(self, img):
        out = {"valid": False, "optimized": False}
        try:
            if not img.image or not img.image.storage.exists(img.image.name):
                return out
            with img.image.open("rb") as fh:
                raw = fh.read()
            if not raw:
                return out
            Image.open(BytesIO(raw)).verify()
            out["valid"] = True
            out["optimized"] = img.is_optimized
        except (UnidentifiedImageError, OSError, ValueError):
            out["valid"] = False
        return out
