"""Template context processor injecting site-wide business config and cart count."""
from decimal import Decimal

from django.conf import settings
from django.db.models import F, Sum
from django.urls import resolve

from core.models import SiteConfig
from payments.payment_methods import get_payment_methods, payfast_enabled, payfast_mode, payfast_summary


def get_cart_count(request):
    """Return the total number of items (sum of quantities) in the session cart."""
    cart = request.session.get("cart", {})
    total = 0
    for info in cart.values():
        try:
            total += int(info.get("qty", 0))
        except (TypeError, ValueError):
            continue
    return total


def site_globals(request):
    cfg = SiteConfig.load()
    whatsapp = cfg.whatsapp_number or ""
    # Normalise to international digits for wa.me links
    digits = "".join(ch for ch in whatsapp if ch.isdigit())
    if digits.startswith("0"):
        digits = "27" + digits[1:]
    wa_link = f"https://wa.me/{digits}" if digits else "#"

    return {
        "site_config": cfg,
        "whatsapp_link": wa_link,
        "whatsapp_number_raw": digits,
        "cart_count": get_cart_count(request),
        "enabled_cart": getattr(settings, "ENABLE_CART", True),
        # Payment / PayFast globals (see payments.payment_methods for the source)
        "payment_methods": get_payment_methods(),
        "payfast_enabled": payfast_enabled(),
        "payfast_mode": payfast_mode(),
        "payfast_message": payfast_summary()["message"],
    }


def admin_command_bar(request):
    """Context for the premium admin command bar + command-centre dashboard.

    Only does work for authenticated staff on admin pages. The dashboard KPIs
    are computed once, when the request resolves to the admin index view.
    """
    if not (request.user.is_active and getattr(request.user, "is_staff", False)):
        return {}

    from products.models import Product, ProductImage, ProductEnquiry
    from orders.models import Order
    from customers.models import Customer

    try:
        match = resolve(request.path)
    except Exception:
        return {}
    is_dashboard = match.app_names == ["admin"] and match.url_name == "index"

    ctx = {}

    # Sidebar "active" flags based on the current admin path.
    path = request.path
    ctx["is_dashboard_page"] = is_dashboard
    ctx["is_product_list"] = path.startswith("/admin/products/product/") and not "/change/" in path and not "/add/" in path
    ctx["is_order_list"] = path.startswith("/admin/orders/order/") and not "/change/" in path and not "/add/" in path

    if is_dashboard:
        all_orders = Order.objects.all()
        secured = Order.objects.filter(status__in=("paid", "processing", "ready", "completed"))
        revenue = secured.aggregate(s=Sum("total"))["s"] or Decimal("0")
        sale_qs = Product.objects.filter(
            is_active=True, original_price__isnull=False, original_price__gt=F("price")
        ).order_by("-updated_at")

        ctx.update(
            {
                "dash_orders_count": all_orders.count(),
                "dash_open_orders": all_orders.exclude(status__in=("completed", "cancelled", "refunded")).count(),
                "dash_revenue": revenue,
                "dash_products": Product.objects.filter(is_active=True).count(),
                "dash_sale_products": sale_qs.count(),
                "dash_customers": Customer.objects.count(),
                "dash_members": Customer.objects.filter(user__isnull=False).count(),
                "dash_pending_images": ProductImage.objects.filter(status=ProductImage.Status.PENDING).count(),
                "dash_pending_enquiries": ProductEnquiry.objects.filter(status="new").count(),
                "dash_recent_orders": all_orders.select_related("customer")[:6],
                "dash_sale_list": sale_qs[:6],
                "dash_new_members": Customer.objects.filter(user__isnull=False)
                .select_related("user")
                .order_by("-created_at")[:5],
                "order_status_choices": Order.Status.choices,
            }
        )

    active_orders = Order.objects.exclude(status__in=("completed", "cancelled", "refunded"))
    ctx["orders_count"] = active_orders.count()

    # ------------------------------------------------------------------
    # Notifications — DB-backed, reconciled to live state each request.
    # Only *new* items surface as unread; existing items keep their read
    # state, and items that have been resolved are retired to read.
    # ------------------------------------------------------------------
    from core.models import Notification

    actionable = []
    for order in active_orders.order_by("created_at")[:6]:
        actionable.append(
            {
                "key": f"order:{order.pk}",
                "title": f"Order {order.reference}",
                "text": f"Order {order.reference} — {order.get_status_display()}",
                "url": f"/admin/orders/order/{order.pk}/change/",
                "level": "warning" if order.status == "pending" else "info",
            }
        )
    for img in ProductImage.objects.filter(status=ProductImage.Status.PENDING).select_related("product")[:4]:
        actionable.append(
            {
                "key": f"image:{img.pk}",
                "title": "Verify product image",
                "text": f"Verify image: {img.product.name}",
                "url": f"/admin/products/productimage/{img.pk}/change/",
                "level": "info",
            }
        )
    for enquiry in ProductEnquiry.objects.filter(status="new")[:2]:
        actionable.append(
            {
                "key": f"enquiry:{enquiry.pk}",
                "title": "New product enquiry",
                "text": f"New enquiry: {enquiry.product_name or enquiry.product}",
                "url": f"/admin/products/productenquiry/{enquiry.pk}/change/",
                "level": "success",
            }
        )

    seen_keys = set()
    for item in actionable:
        seen_keys.add(item["key"])
        Notification.objects.update_or_create(key=item["key"], defaults=item)

    # Retire notifications for items that are no longer actionable.
    from django.db.models import Q

    persisted_keys = list(
        Notification.objects.filter(key__in=[item["key"] for item in actionable]).values_list("key", flat=True)
    )
    stale_q = Q()
    for prefix in ("order:", "image:", "enquiry:"):
        stale_q |= Q(key__startswith=prefix)
    Notification.objects.filter(stale_q).exclude(key__in=persisted_keys).update(is_read=True)

    unread_qs = Notification.objects.filter(is_read=False)
    recent_read = Notification.objects.filter(is_read=True).exclude(
        key__in=[item["key"] for item in actionable]
    )[:4]
    notifications = [
        {
            "pk": n.pk,
            "title": n.title,
            "text": n.text,
            "level": n.level,
            "url": n.url or "/admin/",
            "is_read": n.is_read,
        }
        for n in list(unread_qs[:10]) + list(recent_read)
    ]

    ctx["notifications"] = notifications
    ctx["unread_count"] = unread_qs.count()
    return ctx
