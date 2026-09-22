"""
Central configuration for the payment methods shown next to the PayFast
payment section.

This is the single source of truth for which payment methods are presented on
the checkout, cart and payment pages. To update the displayed methods, edit
``PAYFAST_PAYMENT_METHODS`` here - no template changes should be required.

``code`` values are PayFast's official ``payment_method`` values. When a
customer selects one on the payment page, the field is included in the signed
payload and PayFast then shows ONLY that method. If nothing is selected, no
``payment_method`` field is sent and PayFast presents every method enabled on
the merchant account.

Only list methods the merchant account actually offers. Methods that are not
enabled on the PayFast account will be rejected if forced via ``payment_method``.
"""
from django.conf import settings

# Ordered so card/EFT (the most common) appear first.
# ``code`` = PayFast's payment_method value ('' disallowed here).
# ``name`` is the display label shown to customers.
PAYFAST_PAYMENT_METHODS = [
    {"code": "cc", "name": "Credit Card"},
    {"code": "dc", "name": "Debit Card"},
    {"code": "ef", "name": "Instant EFT"},
    {"code": "cp", "name": "Capitec Pay"},
    {"code": "mc", "name": "Mobicred"},
    {"code": "mp", "name": "Masterpass"},
    {"code": "sc", "name": "SCode"},
    {"code": "ss", "name": "SnapScan"},
    {"code": "zp", "name": "Zapper"},
    {"code": "mt", "name": "MoreTyme"},
    {"code": "rc", "name": "Store Card"},
    {"code": "mu", "name": "Mukuru"},
    {"code": "ap", "name": "Apple Pay"},
    {"code": "sp", "name": "Samsung Pay"},
    {"code": "ab", "name": "Absa Pay"},
    {"code": "gp", "name": "Google Pay"},
    {"code": "nd", "name": "Nedbank Direct EFT"},
    {"code": "pf", "name": "Payflex"},
]

_AVAILABLE_CODES = {m["code"] for m in PAYFAST_PAYMENT_METHODS}


def get_payment_methods():
    """Return the ordered list of payment methods offered in the UI."""
    return PAYFAST_PAYMENT_METHODS


def is_valid_method_code(code):
    """Return True when ``code`` is one of PayFast's configured method values."""
    return code in _AVAILABLE_CODES


def payfast_enabled():
    """True when real PayFast merchant credentials are configured."""
    return bool(getattr(settings, "PAYFAST_ENABLED", False))


def payfast_mode():
    """Return 'sandbox' or 'live' based on environment configuration."""
    return getattr(settings, "PAYFAST_MODE", "sandbox")


def payfast_summary():
    """Polished, non-technical snapshot used on the public payment UI.

    Returns ``enabled`` (bool) and ``message`` (str) suitable for customers.
    """
    enabled = payfast_enabled()
    if enabled:
        message = "Online payments are available. You will be redirected to a secure PayFast page to complete your payment."
    else:
        message = (
            "Online payment is currently being configured. "
            "To complete your order now, please contact us via WhatsApp."
        )
    return {"enabled": enabled, "message": message}


def payfast_mode():
    """Return 'sandbox' or 'live' based on environment configuration."""
    return getattr(settings, "PAYFAST_MODE", "sandbox")


def payfast_summary():
    """Polished, non-technical snapshot used on the public payment UI.

    Returns ``enabled`` (bool) and ``message`` (str) suitable for customers.
    """
    enabled = payfast_enabled()
    if enabled:
        message = "Online payments are available. You will be redirected to a secure PayFast page to complete your payment."
    else:
        message = (
            "Online payment is currently being configured. "
            "To complete your order now, please contact us via WhatsApp."
        )
    return {"enabled": enabled, "message": message}
