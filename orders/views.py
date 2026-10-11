"""Cart and checkout views for the Ratshie shop."""
import json
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
from products.services import can_purchase_product, cart_restriction_errors, cart_stock_errors, line_totals
from customers.models import Customer
from core.utils import cart_from_session, save_cart, cart_items
from .services import cart_delivery


def _build_lines(cart, user=None):
    items = cart_items(cart)
    # One shared calculator so the cart page, drawer and checkout always agree.
    delivery = cart_delivery(items)
    # Only custom fees are attached to a specific product; the standard fee is
    # one line for the whole order, so it has no product to map back to.
    delivery_by_pk = {
        d["product"].pk: d
        for d in (delivery["lines"] if delivery else [])
        if d["product"] is not None
    }
    lines = []
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    for it in items:
        p = it["product"]
        qty = it["qty"]
        line_total, original_line_total, discount = line_totals(p.price, p.original_price, qty)
        allowed, reason = can_purchase_product(user, p)
        d = delivery_by_pk.get(p.pk)
        lines.append(
            {
                "product": p,
                "qty": qty,
                "line_total": line_total,
                "original_line_total": original_line_total,
                "discount": discount,
                "restricted": (not allowed and reason == "member_only"),
                "image": p.public_image.image if p.public_image else None,
                "delivery_type": d["type"] if d else "standard",
                "delivery_fee": d["fee"] if d else None,
                "delivery_is_free": d["is_free"] if d else False,
                "delivery_label": d["label"] if d else "Standard delivery",
            }
        )
        subtotal += original_line_total
        discount_total += discount
    total = subtotal - discount_total
    return lines, subtotal, discount_total, total, delivery


def _delivery_context(delivery):
    """Normalise a :func:`cart_delivery` result for templates."""
    if delivery is None:
        return {
            "delivery_fee": Decimal("0.00"),
            "delivery_is_free": True,
            "delivery_lines": [],
        }
    return {
        "delivery_fee": delivery["fee"],
        "delivery_is_free": delivery["is_free"],
        "delivery_lines": delivery["lines"],
    }


def cart_view(request):
    cart = cart_from_session(request)
    lines, subtotal, discount_total, total, delivery = _build_lines(cart, request.user)
    total_qty = sum(l["qty"] for l in lines)
    ctx = _delivery_context(delivery)
    context = {
        "lines": lines,
        "subtotal": subtotal,
        "discount_total": discount_total,
        "total": total,
        "total_qty": total_qty,
        "cart_count": total_qty,
        "grand_total": total + ctx["delivery_fee"],
        "restricted_items": _restricted_lines(lines),
        "crumb_list": [("Cart", None)],
        **ctx,
    }
    return render(request, "orders/cart.html", context)


def _restricted_lines(lines):
    return [l for l in lines if l.get("restricted")]


def _cart_context(request):
    """Build the shared context for the cart page and the cart drawer."""
    cart = cart_from_session(request)
    lines, subtotal, discount_total, total, delivery = _build_lines(cart, request.user)
    total_qty = sum(l["qty"] for l in lines)
    ctx = _delivery_context(delivery)
    return {
        "lines": lines,
        "subtotal": subtotal,
        "discount_total": discount_total,
        "total": total,
        "total_qty": total_qty,
        "cart_count": total_qty,
        "grand_total": total + ctx["delivery_fee"],
        "restricted_items": _restricted_lines(lines),
        **ctx,
    }


def _cart_fragment_response(request, context):
    """Return the cart-page or cart-drawer fragment after a cart mutation."""
    if request.POST.get("cart_target") == "drawer":
        response = render(request, "orders/_cart_drawer_panel.html", context)
    else:
        response = render(request, "orders/_cart_panel.html", context)
    # Lets the drawer/header badges stay in sync without a second request.
    response["HX-Trigger"] = json.dumps({"cartCount": context["total_qty"]})
    return response


def cart_partial(request):
    """Return an HTML fragment (cart contents + summary) for HTMX quantity updates."""
    cart = cart_from_session(request)
    lines, subtotal, discount_total, total, delivery = _build_lines(cart, request.user)
    total_qty = sum(l["qty"] for l in lines)
    ctx = _delivery_context(delivery)
    return render(
        request,
        "orders/_cart_panel.html",
        {
            "lines": lines,
            "subtotal": subtotal,
            "discount_total": discount_total,
            "total": total,
            "total_qty": total_qty,
            "grand_total": total + ctx["delivery_fee"],
            "restricted_items": _restricted_lines(lines),
            **ctx,
        },
    )


def cart_drawer(request):
    """Return the sliding cart-drawer fragment for the current session cart."""
    return render(request, "orders/_cart_drawer_panel.html", _cart_context(request))


@require_POST
def cart_add(request, slug):
    """Add-to-cart for the ``/orders/cart/add/`` URL.

    This route is not linked from any template - the product card and product
    page post to ``products:cart_add`` - but it is a live, reachable endpoint.
    It used to carry its own copy of the member-only gate that redirected to the
    product page instead of sign-in, so the same action behaved differently
    depending on which URL was posted to. It now delegates to the products view,
    making the sale gate a single implementation with a single outcome.
    """
    from products.views import cart_add as products_cart_add

    return products_cart_add(request, slug)


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
        return _cart_fragment_response(request, _cart_context(request))
    return HttpResponseRedirect(reverse("orders:cart"))


@require_POST
def cart_remove(request, pk):
    cart = cart_from_session(request)
    cart.pop(str(pk), None)
    save_cart(request, cart)
    if request.headers.get("HX-Request"):
        return _cart_fragment_response(request, _cart_context(request))
    return HttpResponseRedirect(reverse("orders:cart"))


@require_POST
def cart_clear(request):
    request.session["cart"] = {}
    messages.info(request, "Your cart has been cleared.")
    if request.headers.get("HX-Request"):
        return _cart_fragment_response(request, _cart_context(request))
    return HttpResponseRedirect(reverse("orders:cart"))


def checkout(request):
    cart = cart_from_session(request)
    if not cart:
        return redirect("orders:cart")
    lines, subtotal, discount_total, total, delivery = _build_lines(cart, request.user)
    total_qty = sum(l["qty"] for l in lines)
    # Delivery is resolved server-side from each product's settings and shown
    # before the customer confirms. The browser never supplies this amount.
    ctx = _delivery_context(delivery)
    return render(
        request,
        "orders/checkout.html",
        {
            "lines": lines,
            "subtotal": subtotal,
            "discount_total": discount_total,
            "total": total,
            "grand_total": total + ctx["delivery_fee"],
            "total_qty": total_qty,
            "restricted_items": _restricted_lines(lines),
            "restriction_errors": cart_restriction_errors(request.user, cart_items(cart))
            if not request.user.is_authenticated
            else [],
            "crumb_list": [("Cart", "orders:cart"), ("Checkout", None)],
            # One-shot: a rejected terms checkbox shows its message inline, once.
            "terms_error": request.session.pop("checkout_terms_error", ""),
            **ctx,
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
    # Stock is re-checked against the database here, at order submission. The
    # cart quantity alone is never proof that the units still exist.
    rerrors.extend(cart_stock_errors(items))
    # Keep the first occurrence of each message, preserving order.
    seen_errors = set()
    rerrors = [e for e in rerrors if not (e in seen_errors or seen_errors.add(e))]
    if rerrors:
        for e in rerrors:
            messages.error(request, e)
        has_member = any("member" in e.lower() for e in rerrors)
        if has_member:
            messages.error(request, "Sale products require a registered member account. Sign in or register to continue.")
        else:
            messages.error(request, "Please update your cart and try again.")
        return redirect("orders:checkout")

    # Recompute pricing server-side before creating the order. The delivery fee
    # is calculated from each product's delivery settings; the browser never
    # supplies a fee.
    _lines, _subtotal, _discount, _total, delivery = _build_lines(cart, request.user)
    fee = delivery["fee"] if delivery else Decimal("0.00")

    full_name = request.POST.get("full_name", "").strip()
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    delivery_address = request.POST.get("delivery_address", "").strip()
    notes = request.POST.get("notes", "").strip()
    # Terms acceptance is required and is enforced here, not in the browser, so
    # the order cannot be created by posting the form without the checkbox.
    terms_accepted = request.POST.get("accept_terms") in ("1", "on", "true", "yes")

    # Every online order is delivered; the fee is the server-calculated total
    # for the distinct products in the cart.

    errors = []
    if not full_name:
        errors.append("Please provide your full name.")
    if not phone:
        errors.append("Please provide a phone number.")
    if not email:
        errors.append("Please provide an email address for your order confirmation.")
    if not delivery_address:
        errors.append("Please provide a delivery address.")
    # The terms rejection is shown inline, beside the checkbox, rather than as a
    # floating toast. It is carried in the session until the next checkout GET,
    # which renders it next to the box.
    terms_error = "" if terms_accepted else "Please accept the Terms & Conditions to place your order."

    if errors:
        for e in errors:
            messages.error(request, e)
    if errors or terms_error:
        if terms_error:
            request.session["checkout_terms_error"] = terms_error
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
    from django.utils import timezone

    # Create the order, its items and the payment record in one transaction. The
    # cart is only cleared once everything exists, so a mid-creation failure
    # rolls back cleanly and the customer keeps their items.
    with transaction.atomic():
        order = Order.objects.create(
            customer=customer,
            customer_name=full_name,
            email=email,
            phone=phone,
            delivery_option=Order.DeliveryChoice.DELIVERY,
            delivery_address=delivery_address,
            delivery_fee=fee,
            shipping_method=Order.ShippingMethod.STANDARD,
            shipping_method_label=Order.ShippingMethod.STANDARD.label,
            notes=notes,
            # Both acceptance values are recorded from the server's own clock and
            # the validated flag, never from a client-supplied timestamp.
            terms_accepted=True,
            terms_accepted_at=timezone.now(),
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
        # Delivery orders get a courier-style delivery window estimate.
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
