"""
Orders model for the Ratshie shop.

An order is created when a customer checks out and provides delivery/collection
details. Payment state is managed alongside the order. The server always
recalculates totals from the database - never trusting browser data.
"""
from django.db import models
from django.utils import timezone
import secrets


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAYMENT_PENDING = "payment_pending", "Payment Pending"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class DeliveryChoice(models.TextChoices):
        COLLECTION = "collection", "Collect at Workshop"
        DELIVERY = "delivery", "Delivery"

    reference = models.CharField(max_length=40, unique=True, blank=True)
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )

    customer_name = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)

    delivery_option = models.CharField(max_length=20, choices=DeliveryChoice.choices, default=DeliveryChoice.COLLECTION)
    delivery_address = models.TextField(blank=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment_reference = models.CharField(max_length=40, blank=True)
    payfast_transaction_id = models.CharField(max_length=64, blank=True)

    notes = models.TextField(blank=True)
    delivery_estimate_from = models.DateField(
        "Delivery estimate from",
        null=True,
        blank=True,
        help_text="Calculated delivery start date (business days).",
    )
    delivery_estimate_to = models.DateField(
        "Delivery estimate to",
        null=True,
        blank=True,
        help_text="Calculated delivery end date (business days).",
    )
    delivery_estimate_source = models.CharField(
        "Estimate source",
        max_length=20,
        default="product",
        choices=[
            ("product", "Product settings"),
            ("admin_override", "Admin override"),
        ],
        help_text="Whether estimate came from product settings or admin override.",
    )
    delivery_estimate_updated_at = models.DateTimeField(
        "Estimate updated at",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.reference or self.pk}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        return "RS-" + secrets.token_hex(5).upper()

    def recalc_totals(self):
        subtotal = sum((i.unit_price or 0) * i.quantity for i in self.items.all())
        self.subtotal = subtotal
        self.total = subtotal + (self.delivery_fee or 0)
        self.save(update_fields=["subtotal", "total"])

    def recalc_delivery_estimate(self, save=True):
        """Recalculate the delivery estimate window for this order."""
        from core import delivery

        f, t = delivery.order_delivery_window(self)
        self.delivery_estimate_from = f
        self.delivery_estimate_to = t
        self.delivery_estimate_source = "product"
        self.delivery_estimate_updated_at = timezone.now()
        if save:
            self.save(
                update_fields=[
                    "delivery_estimate_from",
                    "delivery_estimate_to",
                    "delivery_estimate_source",
                    "delivery_estimate_updated_at",
                ]
            )
        return f, t


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=160, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.unit_price or 0) * self.quantity

    def __str__(self):
        return f"{self.product_name or self.product or 'Item'} x{self.quantity}"


class OrderDeliveryHistory(models.Model):
    """Historical record of delivery estimate changes for an order."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="delivery_history"
    )
    previous_from = models.DateField(null=True, blank=True)
    previous_to = models.DateField(null=True, blank=True)
    new_from = models.DateField(null=True, blank=True)
    new_to = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_email = models.BooleanField(default=False)
    notified_sms = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Delivery history"
        verbose_name_plural = "Delivery history"

    def __str__(self):
        return f"Order {self.order.reference} delivery change #{self.pk}"


class OrderNotification(models.Model):
    """Log of notifications sent for an order (email + SMS)."""

    KINDS = [
        ("confirmation", "Order confirmation"),
        ("delivery_update", "Delivery update"),
    ]
    CHANNELS = [
        ("email", "Email"),
        ("sms", "SMS"),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="notifications"
    )
    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    kind = models.CharField(max_length=30, choices=KINDS)
    channel = models.CharField(max_length=10, choices=CHANNELS)
    status = models.CharField(max_length=10, default="sent")
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Order notification"
        verbose_name_plural = "Order notifications"

    def __str__(self):
        return f"Order {self.order.reference} {self.kind} {self.channel} {self.status}"
