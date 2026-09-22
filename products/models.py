"""
Product catalogue for Ratshie.

Products are internally classified as either a Spare Part or a Lubricant for
administration/organisation only. The public shop presents a single unified
product catalogue (no public category navigation).
"""
from django.db import models
from django.utils.text import slugify
from django.urls import reverse
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class ProductCategory(models.Model):
    """Top-level shop category. Only 'Spare Parts' and 'Lubricants' should exist."""

    SPARE_PARTS = "spare-parts"
    LUBRICANTS = "lubricants"

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="product_categories/", blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Product categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    """Product gallery images with ordering, primary designation and verification status."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    product = models.ForeignKey(
        "Product", on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(
        "Alt text",
        max_length=160,
        blank=True,
        help_text="Short plain-language description of the image (used by screen readers and search engines).",
    )
    image_source = models.CharField(
        "Source",
        max_length=300,
        blank=True,
        help_text="Administrative metadata: where this image came from (e.g. manufacturer site, Wikimedia Commons). Not shown to customers.",
    )
    source_url = models.URLField(
        "Source page URL",
        max_length=500,
        blank=True,
        help_text="Link back to the original page the image was sourced from. Not shown to customers.",
    )
    status = models.CharField(
        "Verification status",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Only VERIFIED images are shown to the public.",
    )
    verification_notes = models.TextField(
        "Verification notes",
        blank=True,
        help_text="Private admin notes about how this image was checked.",
    )
    sort_order = models.PositiveIntegerField(
        "Sort order",
        default=0,
        help_text="Lower numbers appear first. Image 0 is shown first on the product page.",
    )
    is_primary = models.BooleanField(default=False, help_text="Main product image (the one shown as the product thumbnail).")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        verbose_name_plural = "Product images"

    def __str__(self):
        return f"{self.product.name} - Image {self.sort_order}"

    @property
    def is_verified(self):
        return self.status == self.Status.VERIFIED

    @property
    def is_optimized(self):
        return bool(self.image and self.image.name.lower().endswith(".webp"))

    def save(self, *args, **kwargs):
        # Ensure only one primary image per product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(
                is_primary=False
            )
        super().save(*args, **kwargs)


class Product(models.Model):
    """An individual spare part or lubricant for sale."""

    class ProductType(models.TextChoices):
        SPARE_PART = "spare_part", "Spare Part"
        LUBRICANT = "lubricant", "Lubricant"

    AVAILABILITY = [
        ("in_stock", "In Stock"),
        ("limited", "Limited Stock"),
        ("backorder", "Backorder"),
        ("on_request", "On Request"),
        ("out_of_stock", "Out of Stock"),
    ]

    product_type = models.CharField(
        "Product type",
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.SPARE_PART,
        help_text="Internal classification for administration only.",
    )

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    short_description = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    brand = models.CharField(max_length=80, blank=True)
    sku = models.CharField("SKU / Part number", max_length=80, blank=True)

    # Pricing (demo/seed pricing is fully editable from Django admin)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    original_price = models.DecimalField(
        "Original price",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Set higher than the current price to show the product ON SALE (with a struck-through original price and dynamically-calculated discount).",
    )
    is_member_only = models.BooleanField(
        "Member-only purchase",
        default=False,
        help_text=(
            "When enabled, only registered, authenticated members may purchase this "
            "product. Anonymous visitors can still view it and its price, but cannot "
            "add it to the cart or buy it. On-sale products should normally be "
            "member-only so every visitor sees the deal but only members can buy."
        ),
    )

    # Stock / availability
    availability = models.CharField(max_length=20, choices=AVAILABILITY, default="in_stock")
    stock = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(
        default=True,
        help_text=("Uncheck to hide Add to Cart / Buy buttons and show this item as unavailable."),
    )

    # Vehicle compatibility (spare parts)
    vehicle_makes = models.CharField(max_length=200, blank=True, help_text="Comma-separated makes.")
    vehicle_models = models.CharField(max_length=200, blank=True)

    # Lubricant fields
    viscosity = models.CharField(max_length=40, blank=True)
    volume = models.CharField(max_length=40, blank=True)
    oil_type = models.CharField(max_length=60, blank=True)
    spec = models.CharField("API / specification", max_length=160, blank=True)

    # Additional technical specifications (list of "Label: value")
    specifications = models.JSONField(default=list, blank=True, help_text="List of [label, value] pairs.")

    # Badges
    is_featured = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)
    is_genuine = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Products"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("products:detail", kwargs={"slug": self.slug})

    @property
    def primary_image(self):
        """Return the primary image or the first image in gallery."""
        primary = self.images.filter(is_primary=True).first()
        if primary:
            return primary
        return self.images.first()

    @property
    def primary_image_url(self):
        """Return the URL of the primary image."""
        img = self.primary_image
        return img.image.url if img else None

    @property
    def gallery_images(self):
        """Return all gallery images ordered."""
        return self.images.all()

    @property
    def verified_images(self):
        """Return only VERIFIED images, ordered (primary first)."""
        qs = self.images.filter(status=ProductImage.Status.VERIFIED).order_by(
            "-is_primary", "sort_order", "created_at"
        )
        return qs

    @property
    def verified_primary_image(self):
        """Return the primary VERIFIED image, else the first VERIFIED image, else None."""
        img = self.verified_images.filter(is_primary=True).first()
        return img or self.verified_images.first()

    @property
    def verified_image_url(self):
        """URL of the primary verified image (public display only)."""
        img = self.verified_primary_image
        return img.image.url if img else None

    @property
    def public_image(self):
        """Image to show publicly.

        Rule: only VERIFIED images appear in production. In development only,
        fall back to any stored image (placeholder) so the catalogue still
        renders while real images are being approved.
        """
        if self.verified_primary_image:
            return self.verified_primary_image
        if settings.DEBUG:
            return self.primary_image
        return None

    @property
    def public_image_url(self):
        img = self.public_image
        return img.image.url if img else None

    @property
    def public_gallery_images(self):
        """Verified gallery images; in dev fall back to stored images."""
        if self.verified_images:
            return self.verified_images
        if settings.DEBUG:
            return self.gallery_images
        return []

    @property
    def display_price(self):
        return f"R {self.price:,.2f}"

    @property
    def display_original_price(self):
        if self.original_price is not None:
            return f"R {self.original_price:,.2f}"
        return None

    # Backwards-compatible alias
    @property
    def display_compare_at(self):
        return self.display_original_price

    @property
    def is_on_sale(self):
        return self.original_price is not None and self.original_price > self.price

    @property
    def discount_percent(self):
        """Dynamically-calculated discount percentage (0-100), or None when not on sale."""
        if not self.is_on_sale or not self.original_price:
            return None
        diff = self.original_price - self.price
        return int(round((diff / self.original_price) * 100))

    # Backwards-compatible alias
    @property
    def save_percent(self):
        return self.discount_percent

    @property
    def save_amount(self):
        if not self.is_on_sale:
            return None
        return f"R {self.original_price - self.price:,.2f}"

    @property
    def in_stock(self):
        return self.is_available and self.availability in ("in_stock", "limited", "backorder") and self.stock > 0

    @property
    def specs_present(self):
        return bool(self.specifications) or any(
            [
                self.viscosity,
                self.volume,
                self.oil_type,
                self.spec,
                self.vehicle_makes,
                self.vehicle_models,
            ]
        )

    @property
    def product_type_name(self):
        return self.get_product_type_display()

    # Delivery timeframe
    DELIVERY_MODES = [
        ("standard", "Use standard delivery"),
        ("specific", "Specific delivery date"),
        ("range", "Delivery date range"),
    ]
    delivery_mode = models.CharField(
        "Delivery mode",
        max_length=20,
        choices=DELIVERY_MODES,
        default="standard",
        help_text="Select how delivery time is determined for this product.",
    )
    delivery_date_from = models.DateField(
        "Delivery date from",
        null=True,
        blank=True,
        help_text="Specific delivery date (used when Delivery mode is 'Specific date').",
    )
    delivery_date_to = models.DateField(
        "Delivery date to",
        null=True,
        blank=True,
        help_text="End of delivery range (used when Delivery mode is 'Date range').",
    )

    @property
    def delivery_estimate_display(self):
        """Return formatted delivery estimate for this product given an order date."""
        from core import delivery

        f, t = delivery.product_delivery_window(self, timezone.localdate())
        return delivery.format_delivery_estimate(f, t)

    def clean(self):
        """Validate delivery mode and date fields."""
        mode = self.delivery_mode
        if mode == "specific" and not self.delivery_date_from:
            raise ValidationError({"delivery_mode": "Specific date mode requires delivery_date_from."})
        if mode == "range":
            if not self.delivery_date_from or not self.delivery_date_to:
                raise ValidationError(
                    {"delivery_mode": "Range mode requires both delivery_date_from and delivery_date_to."}
                )
            if self.delivery_date_to < self.delivery_date_from:
                raise ValidationError(
                    {"delivery_date_to": "End date must be after start date."}
                )
        # When mode is standard, ensure date fields are cleared at form level;
        # the model clean() just validates the current state.

    def save(self, *args, **kwargs):
        # If mode is standard, clear date fields to avoid stale data
        if self.delivery_mode == "standard":
            self.delivery_date_from = None
            self.delivery_date_to = None
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductEnquiry(models.Model):
    """An enquiry about a specific product (availability / compatibility / price)."""

    STATUS = [
        ("new", "New"),
        ("in_progress", "In Progress"),
        ("quoted", "Quoted"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    CONTACT = [("phone", "Phone"), ("whatsapp", "WhatsApp"), ("email", "Email")]

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_enquiries",
    )
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=160, blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True)

    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=60, blank=True)
    vehicle_year = models.PositiveIntegerField(null=True, blank=True)
    registration = models.CharField(max_length=30, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    message = models.TextField(blank=True)
    preferred_contact = models.CharField(max_length=20, choices=CONTACT, default="whatsapp")

    status = models.CharField(max_length=20, choices=STATUS, default="new")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Product enquiries"

    def __str__(self):
        return f"{self.product_name or self.product or 'Product'} enquiry #{self.pk}"


def seed_categories():
    """Ensure the two primary categories exist. Callable from a data migration / shell."""
    from products.models import ProductCategory

    for name, slug, desc in (
        (
            "Spare Parts",
            "spare-parts",
            "Genuine and quality replacement parts, filters, brake components, belts, "
            "suspension and electrical parts for a wide range of vehicles.",
        ),
        (
            "Lubricants",
            "lubricants",
            "Engine oils, gearbox and transmission fluids, brake fluid, coolant and "
            "quality automotive lubricants.",
        ),
    ):
        ProductCategory.objects.get_or_create(
            slug=slug, defaults={"name": name, "description": desc}
        )
