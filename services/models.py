"""
Service catalogue for the Ratshie workshop.

Services are the mechanical repairs and diagnostics offered by the workshop.
Prices are optional and only shown when supplied.
"""
from django.db import models
from django.utils.text import slugify
from django.urls import reverse


class Service(models.Model):
    """A specific workshop service (repair, diagnostic or maintenance task)."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    short_description = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=40,
        blank=True,
        help_text="Name of an inline SVG icon (see templates for available keys).",
    )
    image = models.ImageField(upload_to="services/", blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_on_request = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("services:detail", kwargs={"slug": self.slug})

    @property
    def display_price(self):
        if self.price is not None:
            return f"R {self.price:,.2f}"
        return "Price on request"


SERVICE_STATUS = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]
