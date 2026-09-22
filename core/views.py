"""Core views: home, about, contact, error handlers."""
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, path
from django.views.decorators.http import require_GET, require_POST
from django.db.models import F as _F, Q
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.http import JsonResponse

from products.models import Product
from core.models import SiteConfig, FAQ, Testimonial
from core.utils import service_whatsapp_message, wa_short_link
from customers.models import Customer


def home(request):
    cfg = SiteConfig.load()

    featured_products = Product.objects.filter(is_active=True, is_featured=True).order_by("name")[:8]
    on_sale_products = (
        Product.objects.filter(is_active=True, original_price__gt=_F("price")).order_by("name")[:8]
    )

    faqs = FAQ.objects.filter(is_active=True)[:6]
    testimonials = Testimonial.objects.filter(is_active=True)[:6]

    context = {
        "cfg": cfg,
        "featured_products": featured_products,
        "on_sale_products": on_sale_products,
        "faqs": faqs,
        "testimonials": testimonials,
        "wa_quote_msg": service_whatsapp_message(),
        "wa_link": wa_short_link(),
    }
    return render(request, "core/home.html", context)


def about(request):
    cfg = SiteConfig.load()
    faqs = FAQ.objects.filter(is_active=True)
    context = {
        "cfg": cfg,
        "faqs": faqs,
        "wa_quote_msg": service_whatsapp_message(),
        "crumb_list": [("About", None)],
    }
    return render(request, "core/about.html", context)


def contact(request):
    cfg = SiteConfig.load()
    return render(
        request,
        "core/contact.html",
        {
            "cfg": cfg,
            "maps_api_key": settings.GOOGLE_MAPS_API_KEY,
            "crumb_list": [("Contact", None)],
        },
    )


@require_POST
def contact_submit(request):
    name = request.POST.get("full_name", "").strip()
    phone = request.POST.get("phone", "").strip()
    email = request.POST.get("email", "").strip()
    vehicle_make = request.POST.get("vehicle_make", "").strip()
    vehicle_model = request.POST.get("vehicle_model", "").strip()
    vehicle_year = request.POST.get("vehicle_year", "").strip()
    enquiry_type = request.POST.get("enquiry_type", "").strip()
    message = request.POST.get("message", "").strip()

    errors = []
    if not name:
        errors.append("Please provide your full name.")
    if not phone:
        errors.append("Please provide a phone number.")
    if not email:
        errors.append("Please provide an email address.")
    if not enquiry_type:
        errors.append("Please select an enquiry type.")
    if not message:
        errors.append("Please provide a message.")

    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect("contact")

    customer, _ = Customer.objects.get_or_create(
        phone=phone or None, defaults={"full_name": name, "email": email}
    )
    if not _ and email and not customer.email:
        customer.email = email
        customer.save()

    from core.models import ContactEnquiry
    ContactEnquiry.objects.create(
        customer=customer,
        vehicle_make=vehicle_make,
        vehicle_model=vehicle_model,
        vehicle_year=int(vehicle_year) if vehicle_year.isdigit() else None,
        enquiry_type=enquiry_type,
        message=message,
    )

    messages.success(request, "Your enquiry has been sent. We'll get back to you shortly.")
    return redirect("contact")


def faq(request):
    faqs = FAQ.objects.filter(is_active=True)
    return render(
        request,
        "core/faq.html",
        {"faqs": faqs, "wa_quote_msg": service_whatsapp_message(), "crumb_list": [("FAQ", None)]},
    )


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Admin notifications (bell). Marking one notification read also auto-cleans
# stale entries; marking all read retires anything no longer actionable.
# ---------------------------------------------------------------------------
@login_required
@user_passes_test(lambda u: u.is_active and u.is_staff)
@require_POST
def notification_mark_read(request, pk):
    from core.models import Notification

    Notification.objects.filter(pk=pk).update(is_read=True)
    return JsonResponse({"ok": True})


@login_required
@user_passes_test(lambda u: u.is_active and u.is_staff)
@require_POST
def notification_mark_all_read(request):
    from core.models import Notification
    from django.db.models import Q

    stale_q = Q()
    for prefix in ("order:", "image:", "enquiry:"):
        stale_q |= Q(key__startswith=prefix)
    active = Notification.objects.exclude(stale_q)
    Notification.objects.filter(stale_q).exclude(is_read=True).update(is_read=True)
    active.filter(is_read=False).update(is_read=True)
    return JsonResponse({"ok": True})


admin_urlpatterns = [
    path("<int:pk>/read/", notification_mark_read, name="notification_mark_read"),
    path("read-all/", notification_mark_all_read, name="notification_mark_all_read"),
]


# ---------------------------------------------------------------------------
# Admin password reset (no user enumeration — Django's form never says whether
# an account exists). Accessible before login; uses custom premium templates.
# ---------------------------------------------------------------------------
class RatShiePasswordResetView(PasswordResetView):
    template_name = "admin/registration/password_reset_form.html"
    email_template_name = "admin/registration/password_reset_email.html"
    subject_template_name = "admin/registration/password_reset_subject.txt"
    success_url = reverse_lazy("admin_password_reset_done")


class RatShiePasswordResetDoneView(PasswordResetDoneView):
    template_name = "admin/registration/password_reset_done.html"


class RatShiePasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "admin/registration/password_reset_confirm.html"
    success_url = reverse_lazy("admin_password_reset_complete")


class RatShiePasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "admin/registration/password_reset_complete.html"


def handler404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def handler500(request):
    return render(request, "errors/500.html", status=500)


def handler403(request, exception=None):
    return render(request, "errors/403.html", status=403)
