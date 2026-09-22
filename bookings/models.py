"""
Workshop service bookings.
"""
from django.db import models


class Booking(models.Model):
    """A customer booking for a workshop service at a preferred date/time."""

    STATUS = [
        ("requested", "Requested"),
        ("confirmed", "Confirmed"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    TIME_SLOTS = [
        ("morning", "Morning (08:00 - 12:00)"),
        ("afternoon", "Afternoon (12:00 - 16:00)"),
        ("late", "Late (16:00 - 17:00)"),
    ]

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=60, blank=True)
    vehicle_year = models.PositiveIntegerField(null=True, blank=True)
    registration = models.CharField(max_length=30, blank=True)

    service = models.ForeignKey(
        "services.Service", on_delete=models.SET_NULL, null=True, blank=True
    )
    service_name = models.CharField(max_length=120, blank=True)

    preferred_date = models.DateField(null=True, blank=True)
    preferred_time = models.CharField(max_length=20, choices=TIME_SLOTS, default="morning")
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS, default="requested")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Booking #{self.pk} ({self.service_name or 'Service'})"
