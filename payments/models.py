"""
PayFast payment records.

Card details are NEVER collected or stored on the site. PayFast handles all
card/banking details on its hosted/redirect flow. We only store payment
records and verify the transaction server-side.
"""
from django.db import models


class Payment(models.Model):
    """A payment initiated for a quote, booking or order via PayFast."""

    STATUS = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    reference = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )
    # Links to related records (only relevant one is populated)
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True)
    quote = models.ForeignKey("quotes.Quote", on_delete=models.SET_NULL, null=True, blank=True)
    booking = models.ForeignKey("bookings.Booking", on_delete=models.SET_NULL, null=True, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)

    payfast_transaction_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.reference} ({self.status})"
