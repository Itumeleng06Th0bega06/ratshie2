"""
Core site-level models: editable business settings, FAQs and testimonials.

Testimonials are intentionally absent from supplied material - the model exists
so genuine reviews can be added through the admin later, and the template shows
a tasteful placeholder until data is present.
"""
from django.db import models
from django.conf import settings
from customers.models import Customer


class SiteConfig(models.Model):
    """Singleton holding editable contact / business details used across the site."""

    site_name = models.CharField(max_length=120, default=settings.SITE_NAME)
    tagline = models.CharField(max_length=200, default=settings.SITE_TAGLINE)
    phone = models.CharField(max_length=32, default=settings.BUSINESS_PHONE)
    phone_display = models.CharField(max_length=32, default=settings.BUSINESS_PHONE_DISPLAY)
    whatsapp_number = models.CharField(max_length=32, default=settings.WHATSAPP_NUMBER)
    whatsapp_display = models.CharField(max_length=32, default=settings.WHATSAPP_DISPLAY)
    email = models.EmailField(default=settings.BUSINESS_EMAIL)
    contact_name = models.CharField(max_length=120, default=settings.CONTACT_NAME)
    address = models.CharField(max_length=255, default=settings.BUSINESS_ADDRESS)
    service_radius_km = models.PositiveIntegerField(default=settings.SERVICE_RADIUS_KM)
    standard_delivery_days = models.PositiveIntegerField(
        "Standard delivery (business days)",
        default=7,
        help_text="Number of business days (Mon-Fri) for standard delivery estimates.",
    )

    # Short marketing copy (editable)
    hero_headline = models.CharField(max_length=160, default="Expert Automotive Care")
    hero_statement = models.TextField(
        default=(
            "Professional vehicle servicing, diagnostics, repairs and quality "
            "automotive products you can trust."
        )
    )
    about_short = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site configuration"
        verbose_name_plural = "Site configuration"

    def __str__(self):
        return self.site_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FAQ(models.Model):
    """Frequently asked questions (accordion)."""

    question = models.CharField(max_length=255)
    answer = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order"]
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question


class Testimonial(models.Model):
    """Genuine customer reviews, managed through admin. Empty until supplied."""

    customer_name = models.CharField(max_length=120)
    vehicle = models.CharField(max_length=120, blank=True)
    content = models.TextField()
    rating = models.PositiveSmallIntegerField(
        default=5, help_text="Star rating out of 5."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer_name} ({self.rating}/5)"


class ContactEnquiry(models.Model):
    """General contact enquiries from the website."""

    ENQUIRY_TYPES = [
        ("general", "General Enquiry"),
        ("service", "Service"),
        ("repair", "Repair"),
        ("diagnostic", "Diagnostic"),
        ("product", "Product"),
        ("spare_part", "Spare Part"),
        ("lubricant", "Lubricant"),
        ("quote", "Quote"),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_enquiries",
    )
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=60, blank=True)
    vehicle_year = models.PositiveIntegerField(null=True, blank=True)
    enquiry_type = models.CharField(max_length=20, choices=ENQUIRY_TYPES, default="general")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Contact enquiries"

    def __str__(self):
        return f"Contact enquiry #{self.pk} ({self.enquiry_type})"


class Notification(models.Model):
    """Dashboard notification, the single source of truth for the admin bell.

    The admin context processor reconciles actionable items (open orders,
    pending image verification, new enquiries) against this table keyed by a
    stable ``key``, so read state survives refreshes and only genuinely new
    items surface as unread.
    """

    LEVELS = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    key = models.CharField(max_length=160, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    text = models.CharField(max_length=300)
    level = models.CharField(max_length=20, choices=LEVELS, default="info")
    url = models.CharField(max_length=255, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return self.title or self.text


class PublicHoliday(models.Model):
    """Configurable public holidays excluded from business-day calculations."""

    date = models.DateField(unique=True)
    name = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["date"]
        verbose_name = "Public holiday"
        verbose_name_plural = "Public holidays"

    def __str__(self):
        return self.name or str(self.date)
