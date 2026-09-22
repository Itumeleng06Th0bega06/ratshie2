"""Shared helpers: WhatsApp message links and PayFast submission/signing."""
from urllib.parse import quote, quote_plus
from decimal import Decimal
import hashlib

from django.conf import settings


def wa_short_link():
    cfg_digits = settings.WHATSAPP_NUMBER or ""
    digits = "".join(c for c in cfg_digits if c.isdigit())
    if digits.startswith("0"):
        digits = "27" + digits[1:]
    return f"https://wa.me/{digits}" if digits else "https://wa.me"


def wa_msg_link(message: str) -> str:
    """Return a wa.me link with a pre-filled message."""
    digits = settings.WHATSAPP_NUMBER or ""
    digits = "".join(c for c in digits if c.isdigit())
    if digits.startswith("0"):
        digits = "27" + digits[1:]
    return f"https://wa.me/{digits}?text=" + quote(message)


def service_whatsapp_message():
    return (
        "Hi, I would like to request a quote for my vehicle.\n\n"
        "Vehicle:\n"
        "Service required:\n"
        "Problem:\n"
        "Preferred date:"
    )


def product_whatsapp_message(product=None, product_name="", sku="", price=None, quantity=1):
    lines = ["Hi, I would like to enquire about this product.", ""]
    name = product_name or getattr(product, "name", "")
    if name:
        lines.append(f"Product: {name}")
    p_sku = sku or getattr(product, "sku", "")
    if p_sku:
        lines.append(f"SKU: {p_sku}")
    p_price = price
    if p_price is None and product is not None:
        p_price = getattr(product, "price", None)
    if p_price is not None:
        lines.append(f"Price: R {p_price:,.2f}")
    lines.append(f"Quantity required: {quantity}")
    lines.append("")
    lines.append("Please confirm availability.")
    return "\n".join(lines)


def order_whatsapp_message(order, items=None):
    lines = ["Hi, I would like to confirm my order with Ratshie.", "", f"Order: {order.reference}"]
    if items:
        subtotal = sum(i.unit_price * i.quantity for i in items if i.unit_price is not None)
        lines.append(f"Total: R {subtotal:,.2f}")
    lines.extend(["", "Order items:"])
    for item in items or []:
        price = item.unit_price or Decimal("0")
        lines.append(f"- {item.product_name} x{item.quantity} = R {price * item.quantity:,.2f}")
    lines.extend(["", "Please confirm availability and arrange delivery."])
    return "\n".join(lines)


def payfast_submit_url():
    if settings.PAYFAST_SANDBOX:
        return "https://sandbox.payfast.co.za/eng/process"
    return "https://www.payfast.co.za/eng/process"


def _php_urlencode(value: str) -> str:
    """Mimic PHP ``urlencode`` (RFC 1738) so signatures match PayFast's PHP engine.

    Python's ``quote_plus`` already matches PHP for everything except ``~``
    (PHP percent-encodes it as ``%7E``; ``quote_plus`` leaves it literal) and
    keeps spaces as ``+``, which PayFast requires.
    """
    return quote_plus(value, safe="").replace("~", "%7E")


def payfast_sign(data: dict) -> str:
    """Build the PayFast MD5 signature over ``data`` in submission order.

    PayFast regenerates the signature from the variables in the exact order
    the form submits them - NOT alphabetically (the alphabetical rule applies
    to the REST-style API, not the checkout form). Each value is PHP-encoded
    (URL-encoded, spaces as '+'), blank variables are skipped, and, when a
    passphrase is configured, ``&passphrase=...`` is appended before the MD5.
    """
    pairs = []
    for key, value in data.items():
        if value == "":
            continue
        pairs.append(f"{_php_urlencode(str(key))}={_php_urlencode(str(value).strip())}")
    ph_string = "&".join(pairs)
    if settings.PAYFAST_PASSPHRASE:
        ph_string += f"&passphrase={_php_urlencode(settings.PAYFAST_PASSPHRASE.strip())}"
    return hashlib.md5(ph_string.encode("utf-8")).hexdigest()


def amount_str(value) -> str:
    """Return a 2-decimal, no-thousand-separator amount string PayFast expects."""
    return f"{Decimal(str(value)):.2f}"


# ---------------------------------------------------------------------------
# Cart helpers (session-based, shared across apps)
# ---------------------------------------------------------------------------
def cart_from_session(request):
    return request.session.get("cart", {})


def save_cart(request, cart):
    request.session["cart"] = cart


def cart_items(cart):
    """Return [{product_pk, qty, product}] for the stored cart."""
    from products.models import Product

    pks = [int(k) for k in cart.keys()]
    products = {p.pk: p for p in Product.objects.filter(pk__in=pks, is_active=True)}
    items = []
    for pk_str, info in cart.items():
        pk = int(pk_str)
        p = products.get(pk)
        if not p:
            continue
        items.append({"product": p, "qty": int(info.get("qty", 1))})
    return items


def cart_summary(cart):
    """Return (lines, subtotal, total_qty) for the stored cart."""
    lines = cart_items(cart)
    subtotal = sum(l["product"].price * l["qty"] for l in lines)
    total_qty = sum(l["qty"] for l in lines)
    return lines, subtotal, total_qty


def product_wa_link(message):
    return wa_msg_link(message)
