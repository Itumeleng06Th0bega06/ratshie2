"""
Quote requests for services / products.
"""
from django.db import models


class Quote(models.Model):
    """A request for a price quote on a service or product."""

    SERVICE = "service"
    PRODUCT = "product"
    TYPE_CHOICES = [
        (SERVICE, "Service quote"),
        (PRODUCT, "Product quote"),
    ]

    STATUS = [
        ("new", "New"),
        ("quoted", "Quoted"),
        ("approved", "Approved"),
        ("declined", "Declined"),
        ("closed", "Closed"),
    ]

    CONTACT = [("phone", "Phone"), ("whatsapp", "WhatsApp"), ("email", "Email")]

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="quotes"
    )
    quote_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=SERVICE)

    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=60, blank=True)
    vehicle_year = models.PositiveIntegerField(null=True, blank=True)
    registration = models.CharField(max_length=30, blank=True)
    mileage = models.PositiveIntegerField(null=True, blank=True)

    service = models.ForeignKey(
        "services.Service", on_delete=models.SET_NULL, null=True, blank=True
    )
    service_name = models.CharField(max_length=120, blank=True)
    product = models.ForeignKey("products.Product", on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=160, blank=True)
    product_category = models.ForeignKey(
        "products.ProductCategory", on_delete=models.SET_NULL, null=True, blank=True
    )

    description = models.TextField(blank=True)
    preferred_date = models.DateField(null=True, blank=True)
    preferred_contact = models.CharField(max_length=20, choices=CONTACT, default="whatsapp")
    attachment = models.FileField(upload_to="quote_attachments/", blank=True)

    status = models.CharField(max_length=20, choices=STATUS, default="new")
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quote #{self.pk} ({self.get_quote_type_display()})"
