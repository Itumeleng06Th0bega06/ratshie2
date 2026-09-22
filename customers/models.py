"""
Customer-facing models.

A Customer is a person/company that enquires, requests quotes, books services
or places orders with Ratshie. One customer may own multiple vehicles.
"""
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator

PHONE = RegexValidator(
    regex=r"^\+?[0-9\s\-()]{7,20}$",
    message="Enter a valid phone number, e.g. +27 61 488 4254.",
)


class Customer(models.Model):
    """A prospective or existing customer."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
        help_text="Optional link to a registered account on the site.",
    )
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32, validators=[PHONE], blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name_plural = "Customers"

    def __str__(self):
        return self.full_name


class Vehicle(models.Model):
    """A vehicle owned by a customer."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="vehicles")
    make = models.CharField(max_length=60, blank=True)
    model = models.CharField(max_length=60, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    registration = models.CharField(max_length=30, blank=True)
    mileage = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["make", "model"]

    def __str__(self):
        parts = [p for p in (self.make, self.model, str(self.year) if self.year else "") if p]
        name = " ".join(parts)
        if self.registration:
            name += f" ({self.registration})"
        return name or f"Vehicle #{self.pk}"
