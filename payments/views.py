"""PayFast integration.

Flow:
  1. GET payments/details/<ref>/ -> show "Complete your payment" page.
  2. Form on that page POSTs to PayFast (hosted redirect). Card details are
     collected ONLY by PayFast - never on our server.
  3. PayFast then calls the ITN endpoint (server-to-server) which we verify.
  4. Return URL shows success/failure/pending to the customer.
"""
from urllib.parse import urlencode
from decimal import Decimal
import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, HttpResponseBadRequest

from .models import Payment
from orders.models import Order
from core.utils import payfast_sign, payfast_submit_url, amount_str
from .payment_methods import payfast_enabled, is_valid_method_code, get_payment_methods

logger = logging.getLogger(__name__)

SANDBOX_ITN_VALIDATE = "https://sandbox.payfast.co.za/eng/query/validate"
PROD_ITN_VALIDATE = "https://www.payfast.co.za/eng/query/validate"


def _itn_validate_url():
    return SANDBOX_ITN_VALIDATE if settings.PAYFAST_SANDBOX else PROD_ITN_VALIDATE


def payment_details(request, reference):
    payment = get_object_or_404(Payment, reference=reference)
    enabled = payfast_enabled()
    chosen = request.GET.get("method", "")
    if not is_valid_method_code(chosen):
        chosen = ""
    chosen_label = ""
    if chosen:
        for m in get_payment_methods():
            if m["code"] == chosen:
                chosen_label = m["name"]
                break
    # Do not build PayFast submit fields until a real merchant is configured.
    # This keeps the UI intact but prevents submitting empty credentials / never
    # pretending a payment can be processed before the account exists.
    form_fields = _build_payfast_fields(payment, chosen) if enabled else {}
    return render(
        request,
        "payments/details.html",
        {
            "payment": payment,
            "form_fields": form_fields,
            "payfast_url": payfast_submit_url() if enabled else "",
            "sandbox": settings.PAYFAST_SANDBOX,
            "payfast_enabled": enabled,
            "chosen_method": chosen,
            "chosen_method_label": chosen_label,
        },
    )


def _build_payfast_fields(payment, payment_method=""):
    """Build the hidden form fields to submit to PayFast.

    ``payment_method`` is an optional PayFast method code (e.g. 'cc', 'ef').
    When provided it is included in the signed payload BEFORE the signature is
    computed, so the exact values PayFast receives always cover the signature.
    """
    base = settings.PAYFAST_RETURN_URL_PREFIX
    fields = {
        "merchant_id": settings.PAYFAST_MERCHANT_ID,
        "merchant_key": settings.PAYFAST_MERCHANT_KEY,
        "return_url": f"{base}/payments/return/{payment.reference}/",
        "cancel_url": f"{base}/payments/cancel/{payment.reference}/",
        "notify_url": f"{base}/payments/itn/",
        "m_payment_id": payment.reference,
        "amount": amount_str(payment.amount),
        "item_name": payment.description or f"Payment {payment.reference}",
    }
    if payment_method:
        fields["payment_method"] = payment_method
    fields["signature"] = payfast_sign(fields)
    if settings.DEBUG:
        # Diagnostic only: parameter names, amount and the resulting signature.
        # NEVER log merchant_key or the passphrase.
        logger.debug(
            "payfast fields=%s amount=%s passphrase_configured=%s signature=%s",
            list(fields.keys()),
            fields.get("amount"),
            bool(settings.PAYFAST_PASSPHRASE),
            fields["signature"],
        )
    return fields


def _amount_matches(payment, data) -> bool:
    """Return True only if the ITN 'amount' matches the server-side payment total.

    The browser-reported amount must never be trusted; the server compares it
    against the amount stored on the Payment before marking it successful.
    """
    from decimal import Decimal, InvalidOperation

    try:
        itn_amount = Decimal(str(data.get("amount", "")))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return itn_amount == Decimal(str(payment.amount))


def _update_payment_from_itn(data):
    """Update Payment status from a verified ITN payload.

    Security:
      - Only update if the paid amount matches the order total (server-determined).
      - Never downgrade an already-successful payment (prevents re-processing).
    """
    ref = data.get("m_payment_id", "")
    try:
        payment = Payment.objects.get(reference=ref)
    except Payment.DoesNotExist:
        return None

    status = data.get("payment_status", "").lower()

    # Verify the amount against the server-side order total. Do not trust the browser.
    if not _amount_matches(payment, data):
        return None

    status_map = {
        "complete": "success",
        "completed": "success",
        "pending": "pending",
        "failed": "failed",
        "cancelled": "failed",
        "denied": "failed",
    }
    new_status = status_map.get(status, payment.status)

    # Prevent duplicate processing / downgrades: once success, never change.
    if payment.status == "success":
        return payment

    if new_status == "success":
        payment.status = "success"
        payment.payfast_transaction_id = data.get("pf_payment_id", "")
        payment.raw_response = data
        payment.save(update_fields=["status", "payfast_transaction_id", "raw_response", "updated_at"])

        if payment.order:
            order = payment.order
            order.status = Order.Status.PAID
            order.payment_status = Order.Status.PAID
            order.payfast_transaction_id = data.get("pf_payment_id", "")
            order.save(update_fields=["status", "payment_status", "payfast_transaction_id", "updated_at"])

            # Ensure a delivery estimate exists and notify the customer of the
            # paid order (idempotent: duplicate ITNs will not re-send).
            try:
                if not order.delivery_estimate_from:
                    order.recalc_delivery_estimate()
                from orders.notifications import send_order_confirmation
                send_order_confirmation(order)
            except Exception:
                # Notification failures must never break ITN handling.
                logger.exception("post-payment notification failed for %s", payment.reference)
    elif new_status == "failed" and payment.status == "pending":
        payment.status = "failed"
        payment.raw_response = data
        payment.save(update_fields=["status", "raw_response", "updated_at"])
        if payment.order and payment.order.payment_status == Order.Status.PAYMENT_PENDING:
            payment.order.status = Order.Status.CANCELLED
            payment.order.payment_status = Order.Status.PAYMENT_PENDING
            payment.order.save(update_fields=["status", "payment_status", "updated_at"])

    return payment


def _verify_signature(data: dict) -> bool:
    """Verify that a POST came from PayFast by recomputing the signature."""
    # For ITN validation PayFast appends signature & token; remove them
    sig = data.get("signature", "")
    clean = {k: v for k, v in data.items() if k not in ("signature", "token")}
    expect = payfast_sign(clean)
    return sig.upper() == expect.upper() if sig else False


@require_GET
def payment_return(request, reference):
    """Landing page PayFast sends the customer back to.

    The authoritative status is the server-side Payment/Order state (updated via
    ITN). The browser query param is used only as a hint and never trusted for
    amounts.
    """
    payment = Payment.objects.filter(reference=reference).first()
    if payment and payment.status == "success":
        state = "success"
    elif payment and payment.status == "failed":
        state = "failed"
    else:
        hint = request.GET.get("payment_status", "").lower()
        state = "success" if hint in ("complete", "completed") else "pending"
    return render(
        request,
        "payments/result.html",
        {"state": state, "payment": payment, "order": payment.order if payment else None},
    )


@require_GET
def payment_cancel(request, reference):
    payment = Payment.objects.filter(reference=reference).first()
    return render(
        request,
        "payments/result.html",
        {"state": "cancelled", "payment": payment},
    )


@csrf_exempt
@require_POST
def payment_itn(request):
    """Server-to-server notification from PayFast. Must verify before trusting."""
    data = request.POST.copy()
    if not _verify_signature(data):
        return HttpResponseBadRequest("Invalid signature")
    # Best-practice ITN validation: re-confirm the payload with PayFast before
    # accepting it as authoritative (defends against forged/cached ITNs).
    if not _validated_by_payfast(data):
        return HttpResponseBadRequest("ITN validation failed")
    _update_payment_from_itn(data)
    # PayFast expects HTTP 200 for successful processing
    return HttpResponse("OK", status=200)


def _validated_by_payfast(data: dict) -> bool:
    """Ask PayFast's validate endpoint whether this ITN is valid."""
    import urllib.request

    # Use the same fields PayFast sent (including our signature check data).
    body = urlencode(data).encode("utf-8")
    req = urllib.request.Request(_itn_validate_url(), data=body)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8", "replace")
    except Exception:
        # If we cannot reach PayFast to validate, do not trust the ITN.
        return False
    # PayFast returns "VALID" to confirm the notification is genuine.
    first_line = payload.strip().splitlines()[0].strip() if payload.strip() else ""
    return first_line.upper() == "VALID"
