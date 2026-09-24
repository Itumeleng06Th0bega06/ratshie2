"""Cart and checkout views for the Ratshie shop."""
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse

from .models import Order, OrderItem
from products.models import Product
from products.services import can_purchase_product, cart_restriction_errors, line_totals
from customers.models import Customer
from core.utils import cart_from_session, save_cart, cart_items
from .services import resolve_shipping_method, shipping_methods


def _build_lines(cart, user=None):
    items = cart_items(cart)
    lines = []
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    for it in items:
        p = it["product"]
        qty = it["qty"]
        line_total, original_line_total, discount = line_totals(p.price, p.original_price, qty)
        allowed, reason = can_purchase_product(user, p)
        lines.append(
            {
                "product": p,
                "qty": qty,
                "line_total": line_total,
                "original_line_total": original_line_total,
                "discount": discount,
                "restricted": (not allowed and reason == "member_only"),
                "image": p.public_image.image if p.public_image else None,
            }
        )
        subtotal += original_line_total
        discount_total += discount
    total = subtotal - discount_total
    return lines, subtotal, discount_total, total


def cart_view(request):
    cart = cart_from_session(request)
    lines, subtotal, discount_total, total = _build_lines(cart, request.user)
    total_qty = sum(l["qty"] for l in lines)
    return render(
        request,
        "orders/cart.html",
        {
            "lines": lines,
            "subtotal": subtotal,
            "discount_total": discount_total,
            "total": total,
            "total_qty": total_qty,
            "cart_count": total_qty,
            "restricted_items": _restricted_lines(lines),
            "crumb_list": [("Cart", None)],
        },
    )


def _restricted_lines(lines):
    return [l for l in lines if l.get("restricted")]


def cart_partial(request):
    """Return an HTML fragment (cart contents + summary) for HTMX quantity updates."""
    cart = cart_from_session(request)
    lines, subtotal, discount_total, total = _build_lines(cart, request.user)
    total_qty = sum(l["qty"] for l in lines)
    return render(
        request,
        "orders/_cart_panel.html",
        {"lines": lines, "subtotal": subtotal, "discount_total": discount_total, "total": total, "total_qty": total_qty, "restricted_items": _restricted_lines(lines)},
    )


@require_POST
def cart_add(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    allowed, reason = can_purchase_product(request.user, product)
    if not allowed and reason == "member_only":
        if request.headers.get("HX-Request"):
            return render(request, "components/member_purchase_prompt.html", {"product": product}, status=403)
        messages.error(
            request,
            f"“{product.name}” is a members-only sale product. Sign in or register a free account to purchase it.",
        )
        return HttpResponseRedirect(reverse("products:detail", kwargs={"slug": product.slug}))
    if not allowed:
        messages.error(request, "Sorry, this item is currently unavailable.")
        return HttpResponseRedirect(reverse("products:detail", kwargs={"slug": product.slug}))
    cart = cart_from_session(request)
    try:
        qty = max(1, int(request.POST.get("quantity", 1)))
    except (ValueError, TypeError):
        qty = 1
    current = int(cart.get(str(product.pk), {}).get("qty", 0))
    cart[str(product.pk)] = {"qty": current + qty}
    save_cart(request, cart)
    if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render(request, "components/cart_added.html", {"product": product, "cart_count": sum(int(v.get("qty", 0)) for v in cart.values())})
    next_url = request.POST.get("next", "")
    if next_url and next_url.startswith("/"):
        return HttpResponseRedirect(next_url)
    return HttpResponseRedirect(reverse("orders:cart"))


@require_POST
def cart_set_qty(request, pk):
    """Set a line quantity (inc/dec/update). Returns cart fragment if htmx."""
    product = get_object_or_404(Product, pk=pk)
    cart = cart_from_session(request)
    try:
        qty = int(request.POST.get("qty", 1))
    except (ValueError, TypeError):
        qty = 0
    allowed, reason = can_purchase_product(request.user, product)
    if not allowed and reason == "member_only":
        if request.headers.get("HX-Request"):
            return render(request, "components/member_purchase_prompt.html", {"product": product}, status=403)
        messages.error(
            request,
            f"“{product.name}” is a members-only sale product. Sign in or register a free account to purchase it.",
        )
        return HttpResponseRedirect(reverse("orders:cart"))
    if not allowed:
        messages.error(request, "Sorry, this item is currently unavailable or out of stock.")
        return HttpResponseRedirect(reverse("orders:cart"))
    if qty > product.stock:
        qty = product.stock
    if qty <= 0:
        cart.pop(str(pk), None)
    else:
        cart[str(pk)] = {"qty": qty}
    save_cart(request, cart)
    if request.headers.get("HX-Request"):
        return cart_partial(request)
    return HttpResponseRedirect(reverse("orders:cart"))


@require_POST
def cart_remove(request, pk):
    cart = cart_from_session(request)
    cart.pop(str(pk), None)
    save_cart(request, cart)
    if request.headers.get("HX-Request"):
        return cart_partial(request)
    return HttpResponseRedirect(reverse("orders:cart"))


@require_POST
def cart_clear(request):
    request.session["cart"] = {}
    messages.info(request, "Your cart has been cleared.")
    if request.headers.get("HX-Request"):
        return cart_partial(request)
    return HttpResponseRedirect(reverse("orders:cart"))


def checkout(request):
    cart = cart_from_session(request)
    if not cart:
        return redirect("orders:cart")
    lines, subtotal, discount_total, total = _build_lines(cart, request.user)
    total_qty = sum(l["qty"] for l in lines)
    methods = shipping_methods(total)
    default_method = next((m for m in methods if m["code"] == Order.ShippingMethod.PICKUP), None) or methods[0] if methods else None
    return render(
        request,
        "orders/checkout.html",
        {
            "lines": lines,
            "subtotal": subtotal,
            "discount_total": discount_total,
            "total": total,
            "total_qty": total_qty,
            "restricted_items": _restricted_lines(lines),
            "shipping_methods": methods,
            "selected_method": default_method["code"] if default_method else "",
            "restriction_errors": cart_restriction_errors(request.user, cart_items(cart))
            if not request.user.is_authenticated
            else [],
            "crumb_list": [("Cart", "orders:cart"), ("Checkout", None)],
        },
    )


@require_POST
def checkout_submit(request):
    cart = cart_from_session(request)
    items = cart_items(cart)
    if not items:
        messages.error(request, "Your cart is empty.")
        return redirect("orders:cart")

    # Revalidate purchase authorization server-side before creating an order.
    rerrors = list(cart_restriction_errors(request.user, items))
    for it in items:
        allowed, reason = can_purchase_product(request.user, it["product"])
        if not allowed and reason != "member_only":
            rerrors.append(f"“{it['product'].name}” is currently unavailable or out of stock.")
    if rerrors:
        for e in rerrors:
            messages.error(request, e)
        has_member = any("member" in e.lower() for e in rerrors)
        if has_member:
            messages.error(request, "Sale products require a registered member account. Sign in or register to continue.")
        else:
            messages.error(request, "Please update your cart and try again.")
        return redirect("orders:checkout")

    # Recompute the order total server-side. Free-delivery eligibility and the
    # shipping fee are decided from this value; the browser never supplies a fee.
    _, _, _, total_before_shipping = _build_lines(cart, request.user)

    full_name = request.POST.get("full_name", "").strip()
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    shipping_code = request.POST.get("shipping_method", "").strip()
    delivery_address = request.POST.get("delivery_address", "").strip()
    notes = request.POST.get("notes", "").strip()

    # Resolve the shipping method from config server-side, defaulting to local
    # pickup when the submitted code is missing/invalid so a tampered value can
    # never attach an unexpected fee.
    shipping = resolve_shipping_method(shipping_code, total_before_shipping)
    if shipping is None:
        shipping = {
            "code": "",
            "label": "Delivery to be arranged",
            "fee": Decimal("0"),
            "needs_address": False,
        }
    delivery_option = "delivery" if shipping["needs_address"] else "collection"

    errors = []
    if not full_name:
        errors.append("Please provide your full name.")
    if not phone:
        errors.append("Please provide a phone number.")
    if not email:
        errors.append("Please provide an email address for your order confirmation.")
    if shipping["needs_address"] and not delivery_address:
        errors.append("Please provide a delivery address.")

    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect("orders:checkout")

    customer, _ = Customer.objects.get_or_create(
        phone=phone or None, defaults={"full_name": full_name, "email": email}
    )
    if not _ and email and not customer.email:
        customer.email = email
        customer.save()
    if request.user.is_authenticated and customer.user_id is None:
        customer.user = request.user
        customer.save()
    elif request.user.is_authenticated:
        customer.email = request.user.email or customer.email
        if not customer.full_name:
            customer.full_name = request.user.get_full_name() or request.user.username
        customer.save()

    from payments.models import Payment

    # Create the order, its items and the payment record in one transaction. The
    # cart is only cleared once everything exists, so a mid-creation failure
    # rolls back cleanly and the customer keeps their items.
    with transaction.atomic():
        order = Order.objects.create(
            customer=customer,
            customer_name=full_name,
            email=email,
            phone=phone,
            delivery_option=delivery_option,
            delivery_address=delivery_address,
            delivery_fee=shipping["fee"],
            shipping_method=shipping["code"],
            shipping_method_label=shipping["label"],
            notes=notes,
            status=Order.Status.PAYMENT_PENDING,
            payment_status=Order.Status.PAYMENT_PENDING,
            payment_reference=Order._generate_reference(),
        )

        for it in items:
            OrderItem.objects.create(
                order=order,
                product=it["product"],
                product_name=it["product"].name,
                quantity=it["qty"],
                unit_price=it["product"].price,
            )

        order.recalc_totals()
        # Pickup orders skip the courier-style delivery window entirely.
        if shipping["code"] in (Order.ShippingMethod.STANDARD, Order.ShippingMethod.FREE):
            order.recalc_delivery_estimate()

        Payment.objects.create(
            reference=order.payment_reference,
            customer=customer,
            order=order,
            amount=order.total,
            description=f"Order {order.reference}",
        )

        # Only clear the cart once the order AND its payment record exist.
        request.session["cart"] = {}

    return redirect("payments:details", reference=order.payment_reference)


@staff_member_required
@require_POST
def order_status_update(request, pk):
    """Inline, no-reload order status update used by the command-centre dashboard."""
    order = get_object_or_404(Order, pk=pk)
    status = request.POST.get("status", "").strip()
    if status not in Order.Status.values:
        return JsonResponse({"error": "Invalid status"}, status=400)
    order.status = status
    order.save(update_fields=["status", "updated_at"])
    return JsonResponse({"ok": True, "status": status, "label": order.get_status_display()})
