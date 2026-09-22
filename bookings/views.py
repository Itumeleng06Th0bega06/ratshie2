"""Booking views."""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import Booking
from customers.models import Customer
from services.models import Service
from core.utils import service_whatsapp_message


def booking_form(request, service_slug=None):
    service = None
    if service_slug:
        service = Service.objects.filter(slug=service_slug, is_active=True).first()
    services = Service.objects.filter(is_active=True)
    return render(
        request,
        "bookings/form.html",
        {
            "preselect_service": service,
            "services": services,
            "time_slots": Booking.TIME_SLOTS,
            "wa_quote_msg": service_whatsapp_message(),
            "crumb_list": [("Book a Service", None)],
        },
    )


@require_POST
def booking_submit(request):
    full_name = request.POST.get("full_name", "").strip()
    phone = request.POST.get("phone", "").strip()
    email = request.POST.get("email", "").strip()
    vmake = request.POST.get("vehicle_make", "").strip()
    vmodel = request.POST.get("vehicle_model", "").strip()
    vyear = request.POST.get("vehicle_year", "").strip()
    reg = request.POST.get("registration", "").strip()
    service_id = request.POST.get("service", "").strip()
    pref_date = request.POST.get("preferred_date", "").strip()
    pref_time = request.POST.get("preferred_time", "morning").strip()
    notes = request.POST.get("notes", "").strip()

    errors = []
    if not full_name:
        errors.append("Please enter your full name.")
    if not phone:
        errors.append("Please enter a phone number.")
    if not pref_date:
        errors.append("Please choose a preferred date.")

    if errors:
        messages.error(request, " ".join(errors))
        return redirect("bookings:form")

    customer, _ = Customer.objects.get_or_create(
        phone=phone or None, defaults={"full_name": full_name, "email": email}
    )
    if not _ and email and not customer.email:
        customer.email = email
        customer.save()

    service_obj = Service.objects.filter(pk=service_id).first() if service_id else None
    time_ok = pref_time if pref_time in dict(Booking.TIME_SLOTS) else "morning"

    Booking.objects.create(
        customer=customer,
        vehicle_make=vmake,
        vehicle_model=vmodel,
        vehicle_year=int(vyear) if vyear.isdigit() else None,
        registration=reg,
        service=service_obj,
        service_name=service_obj.name if service_obj else "",
        preferred_date=pref_date or None,
        preferred_time=time_ok,
        notes=notes,
    )

    return render(
        request,
        "bookings/success.html",
        {"customer_name": full_name, "service": service_obj, "wa_quote_msg": service_whatsapp_message()},
    )
