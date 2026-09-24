"""Order notification service: email + SMS with idempotent logging."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from core import delivery
from core.sms import send_sms

from .models import OrderNotification

logger = logging.getLogger(__name__)


def _log(order, kind, channel, ok, detail=""):
    OrderNotification.objects.create(
        order=order,
        customer=order.customer,
        kind=kind,
        channel=channel,
        status="sent" if ok else "failed",
        failure_reason="" if ok else (detail or "")[:255],
    )


def _already_sent(order, kind, channel):
    return OrderNotification.objects.filter(
        order=order, kind=kind, channel=channel, status="sent"
    ).exists()


def _send_email(order, kind, subject, template, context):
    recipient = order.email or (order.customer.email if order.customer else "")
    if not recipient:
        _log(order, kind, "email", False, "No email address")
        return False
    try:
        html = render_to_string(template, context)
        msg = EmailMultiAlternatives(subject, "", settings.DEFAULT_FROM_EMAIL, [recipient])
        msg.attach_alternative(html, "text/html")
        msg.send()
        _log(order, kind, "email", True)
        return True
    except Exception as exc:
        logger.warning("Order email failed: %s", exc)
        _log(order, kind, "email", False, str(exc))
        return False


def _send_sms_for(order, kind, message):
    phone = order.phone or (order.customer.phone if order.customer else "")
    ok, detail = send_sms(phone, message)
    _log(order, kind, "sms", ok, detail)
    return ok


def send_order_confirmation(order):
    """Send the initial confirmation email + SMS once payment succeeds."""
    est = delivery.format_delivery_estimate(
        order.delivery_estimate_from, order.delivery_estimate_to
    )
    pickup = None
    if order.shipping_method == "pickup":
        from .models import ShippingSettings

        pickup = ShippingSettings.load()
    context = {
        "order": order,
        "customer_name": order.customer_name or (order.customer.full_name if order.customer else ""),
        "order_number": order.pk,
        "reference": order.reference,
        "total": order.total,
        "estimate": est,
        "items": order.items.all(),
        "delivery_address": order.delivery_address,
        "shipping_method_label": order.shipping_method_label,
        "shipping_fee": order.delivery_fee,
        "pickup_location": pickup.pickup_location if pickup else "",
        "pickup_instructions": pickup.pickup_instructions if pickup else "",
        "support_email": settings.BUSINESS_EMAIL,
        "support_phone": settings.BUSINESS_PHONE_DISPLAY,
    }
    email_subject = f"Order #{order.pk} Confirmed"
    if not _already_sent(order, "confirmation", "email"):
        _send_email(order, "confirmation", email_subject, "orders/email/confirmation.html", context)
    sms_message = (
        f"Your order #{order.pk} has been confirmed. Payment received. Estimated delivery: {est}."
        if est
        else f"Your order #{order.pk} has been confirmed. Payment received."
    )
    if not _already_sent(order, "confirmation", "sms"):
        _send_sms_for(order, "confirmation", sms_message)


def send_delivery_update(order, reason=""):
    """Send the delivery-change notification (email + SMS)."""
    est = delivery.format_delivery_estimate(order.delivery_estimate_from, order.delivery_estimate_to)
    context = {
        "order": order,
        "customer_name": order.customer_name or (order.customer.full_name if order.customer else ""),
        "order_number": order.pk,
        "reference": order.reference,
        "estimate": est,
        "reason": reason,
        "support_email": settings.BUSINESS_EMAIL,
        "support_phone": settings.BUSINESS_PHONE_DISPLAY,
    }
    _send_email(
        order,
        "delivery_update",
        f"Delivery Update for Order #{order.pk}",
        "orders/email/delivery_update.html",
        context,
    )
    sms_message = f"Update for order #{order.pk}: your new estimated delivery is {est}." if est else f"Update for order #{order.pk}: delivery estimate changed."
    _send_sms_for(order, "delivery_update", sms_message)