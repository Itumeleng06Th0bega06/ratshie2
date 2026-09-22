"""Unified automotive shop views.

The public shop is a single catalogue (no public category navigation). Products
are internally classified as Spare Part or Lubricant via product_type for admin
management only.
"""
from urllib.parse import quote

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import Product, ProductEnquiry
from customers.models import Customer
from .services import can_purchase_product
from core.utils import (
    product_whatsapp_message,
    cart_from_session,
    save_cart,
    product_wa_link,
)


def _product_qs():
    return Product.objects.filter(is_active=True)


def _sale_register_redirect(request, product):
    """Send an anonymous visitor to registration when they try to add a
    member-only / on-sale product. Server-enforced for every request type:
    HTMX (HX-Redirect), the no-refresh fetch path (JSON redirect), or a plain
    browser POST (302). The item is never added to the cart here."""
    register_url = (
        reverse("customers:register")
        + "?next="
        + quote(product.get_absolute_url())
    )
    messages.warning(request, "Please create an account to purchase sale products.")
    if request.headers.get("HX-Request"):
        resp = HttpResponse(status=200)
        resp["HX-Redirect"] = register_url
        return resp
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"redirect": register_url, "sale_required": True})
    return HttpResponseRedirect(register_url)


def shop_index(request):
    qs = _product_qs().order_by("-is_featured", "name")

    cart = request.session.get("cart", {})
    cart_quantities = {int(k): int(v.get("qty", 0)) for k, v in cart.items()}

    context = {
        "products": qs,
        "cart_quantities": cart_quantities,
        "crumb_list": [("Shop", None)],
    }

    return render(request, "products/shop.html", context)


def product_detail(request, slug):
    product = get_object_or_404(_product_qs(), slug=slug)
    related = (
        Product.objects.filter(product_type=product.product_type, is_active=True)
        .exclude(pk=product.pk)
        .order_by("-is_featured", "name")[:4]
    )
    all_products = Product.objects.filter(is_active=True).exclude(pk=product.pk).order_by("-is_featured", "name")
    if len(related) < 4:
        extra = all_products.exclude(pk__in=[r.pk for r in related])[: 4 - len(related)]
        related = list(related) + list(extra)

    wa_msg = product_whatsapp_message(product=product, quantity=1)
    cart = request.session.get("cart", {})
    in_cart_qty = int(cart.get(str(product.pk), {}).get("qty", 0))

    chasing = request.GET.get("added")
    return render(
        request,
        "products/detail.html",
        {
            "product": product,
            "related": related,
            "product_wa_msg": wa_msg,
            "product_wa_link": product_wa_link(wa_msg),
            "in_cart_qty": in_cart_qty,
            "added": chasing == "1",
            "delivery_estimate": product.delivery_estimate_display,
            "crumb_list": [("Shop", "products:shop"), (product.name, None)],
        },
    )


@require_POST
def cart_add(request, slug):
    product = get_object_or_404(_product_qs(), slug=slug)
    cart = cart_from_session(request)
    try:
        qty = max(1, int(request.POST.get("quantity", 1)))
    except (ValueError, TypeError):
        qty = 1

    # Server-side purchase authorization (member-only / on-sale rule).
    allowed, reason = can_purchase_product(request.user, product)
    if not allowed and reason == "member_only":
        # Anonymous visitor + sale product: redirect to registration. The item
        # is NOT added to the cart (enforced for every request type).
        return _sale_register_redirect(request, product)
    if not allowed:
        messages.error(request, "Sorry, this item is currently unavailable.")
        return HttpResponseRedirect(reverse("products:detail", kwargs={"slug": product.slug}))

    if product.is_available and product.stock and not product.in_stock:
        messages.error(request, "Sorry, this item is currently out of stock.")
        return HttpResponseRedirect(reverse("products:detail", kwargs={"slug": product.slug}))

    current = int(cart.get(str(product.pk), {}).get("qty", 0))
    cart[str(product.pk)] = {"qty": current + qty}
    save_cart(request, cart)

    if "ajax" in request.POST or request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render(
            request,
            "components/cart_added.html",
            {"product": product, "cart_count": sum(int(v.get("qty", 0)) for v in cart.values())},
        )

    next_url = request.POST.get("next", "")
    if next_url and next_url.startswith("/"):
        return HttpResponseRedirect(next_url)
    return HttpResponseRedirect(reverse("products:detail", kwargs={"slug": product.slug}) + "?added=1")


def cart_add_partial(request, slug):
    """HTMX-friendly add-to-cart. Member-only / on-sale products are gated
    server-side: anonymous visitors are sent to registration via HX-Redirect."""
    product = get_object_or_404(_product_qs(), slug=slug)
    allowed, reason = can_purchase_product(request.user, product)
    if not allowed and reason == "member_only":
        return _sale_register_redirect(request, product)
    if not allowed:
        return HttpResponse("", status=409)
    cart = cart_from_session(request)
    current = int(cart.get(str(product.pk), {}).get("qty", 0))
    cart[str(product.pk)] = {"qty": current + 1}
    save_cart(request, cart)
    count = sum(int(v.get("qty", 0)) for v in cart.values())
    html = '<span class="cart-badge js-cart-count">{}</span>'.format(count)
    return HttpResponse(html)


@require_POST
def buy_now(request, slug):
    product = get_object_or_404(_product_qs(), slug=slug)
    cart = cart_from_session(request)
    try:
        qty = max(1, int(request.POST.get("quantity", 1)))
    except (ValueError, TypeError):
        qty = 1

    allowed, reason = can_purchase_product(request.user, product)
    if not allowed and reason == "member_only":
        # Anonymous visitor + sale product ("Buy Now") → registration. Never
        # add to cart; consistent with the Add to Cart gate.
        return _sale_register_redirect(request, product)
    if not allowed:
        messages.error(request, "Sorry, this item is currently unavailable.")
        return HttpResponseRedirect(reverse("products:detail", kwargs={"slug": product.slug}))

    current = int(cart.get(str(product.pk), {}).get("qty", 0))
    cart[str(product.pk)] = {"qty": current + qty}
    save_cart(request, cart)
    return HttpResponseRedirect(reverse("orders:checkout"))


def product_enquiry(request, slug=None):
    product = None
    if slug:
        product = get_object_or_404(_product_qs(), slug=slug)
    context = {
        "product": product,
        "crumbs": [("Shop", "products:shop"), ("Product Enquiry", None)],
    }
    return render(request, "products/enquiry.html", context)


@require_POST
def product_enquiry_submit(request):
    name = request.POST.get("full_name", "").strip()
    phone = request.POST.get("phone", "").strip()
    email = request.POST.get("email", "").strip()
    product_id = request.POST.get("product", "").strip()
    vmake = request.POST.get("vehicle_make", "").strip()
    vmodel = request.POST.get("vehicle_model", "").strip()
    vyear = request.POST.get("vehicle_year", "").strip()
    reg = request.POST.get("registration", "").strip()
    try:
        qty = max(1, int(request.POST.get("quantity", "1")))
    except (ValueError, TypeError):
        qty = 1
    message = request.POST.get("message", "").strip()
    contact = request.POST.get("preferred_contact", "whatsapp").strip()

    errors = []
    if not name:
        errors.append("Please provide your full name.")
    if not phone:
        errors.append("Please provide a phone number.")

    product_obj = Product.objects.filter(pk=product_id).first() if product_id else None

    if errors:
        for e in errors:
            messages.error(request, e)
        if product_obj:
            return redirect("products:product_enquiry", slug=product_obj.slug)
        return redirect("products:enquiry")

    customer, _ = Customer.objects.get_or_create(
        phone=phone or None,
        defaults={"full_name": name, "email": email},
    )
    if not _ and email and not customer.email:
        customer.email = email
        customer.save()
    if request.user.is_authenticated and customer.user_id is None:
        customer.user = request.user
        customer.save()

    ProductEnquiry.objects.create(
        customer=customer if customer.pk else None,
        product=product_obj,
        product_name=product_obj.name if product_obj else (request.POST.get("product_name", "") or ""),
        vehicle_make=vmake,
        vehicle_model=vmodel,
        vehicle_year=int(vyear) if vyear.isdigit() else None,
        registration=reg,
        quantity=qty,
        message=message,
        preferred_contact=contact if contact in dict(ProductEnquiry.CONTACT) else "whatsapp",
    )
    wa_msg = product_whatsapp_message(
        product=product_obj, product_name=product_obj.name if product_obj else "the product I enquired about", quantity=qty
    )
    return render(
        request,
        "products/enquiry_success.html",
        {"product": product_obj, "whatsapp_msg": wa_msg},
    )
