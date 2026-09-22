"""Quote request views."""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import Quote
from customers.models import Customer, Vehicle
from services.models import Service
from products.models import Product
from core.utils import service_whatsapp_message


def quote_form(request, service_slug=None):
    service = None
    if service_slug:
        service = Service.objects.filter(slug=service_slug, is_active=True).first()
    services = Service.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True)
    from products.models import ProductCategory

    categories = ProductCategory.objects.filter(is_active=True)

    return render(
        request,
        "quotes/form.html",
        {
            "preselect_service": service,
            "services": services,
            "products": products,
            "categories": categories,
            "wa_quote_msg": service_whatsapp_message(),
            "crumb_list": [("Get a Quote", None)],
        },
    )


@require_POST
def quote_submit(request):
    from products.models import ProductCategory

    full_name = request.POST.get("full_name", "").strip()
    phone = request.POST.get("phone", "").strip()
    email = request.POST.get("email", "").strip()
    vmake = request.POST.get("vehicle_make", "").strip()
    vmodel = request.POST.get("vehicle_model", "").strip()
    vyear = request.POST.get("vehicle_year", "").strip()
    reg = request.POST.get("registration", "").strip()
    mileage = request.POST.get("mileage", "").strip()
    service_id = request.POST.get("service", "").strip()
    product_id = request.POST.get("product", "").strip()
    product_free_text = request.POST.get("product_name", "").strip()
    category_id = request.POST.get("product_category", "").strip()
    description = request.POST.get("description", "").strip()
    pref_date = request.POST.get("preferred_date", "").strip()
    contact = request.POST.get("preferred_contact", "whatsapp").strip()

    errors = []
    if not full_name:
        errors.append("Please enter your full name.")
    if not phone:
        errors.append("Please enter a phone number.")
    if not (email or phone):
        errors.append("Provide an email or phone so we can reply.")

    if errors:
        messages.error(request, " ".join(errors))
        return redirect("quotes:form")

    customer, _ = Customer.objects.get_or_create(
        phone=phone or None, defaults={"full_name": full_name, "email": email}
    )
    if not _ and email and not customer.email:
        customer.email = email
        customer.save()

    vehicle = None
    if vmake or vmodel:
        vehicle = Vehicle.objects.create(
            customer=customer,
            make=vmake,
            model=vmodel,
            year=int(vyear) if vyear.isdigit() else None,
            registration=reg,
            mileage=int(mileage) if mileage.isdigit() else None,
        )

    service_obj = Service.objects.filter(pk=service_id).first() if service_id else None
    product_obj = Product.objects.filter(pk=product_id).first() if product_id else None
    category_obj = ProductCategory.objects.filter(pk=category_id).first() if category_id else None

    quote_type = Quote.PRODUCT if (product_obj or product_free_text) else Quote.SERVICE
    Quote.objects.create(
        customer=customer,
        quote_type=quote_type,
        vehicle_make=vmake,
        vehicle_model=vmodel,
        vehicle_year=int(vyear) if vyear.isdigit() else None,
        registration=reg,
        mileage=int(mileage) if mileage.isdigit() else None,
        service=service_obj,
        service_name=service_obj.name if service_obj else "",
        product=product_obj,
        product_name=product_obj.name if product_obj else product_free_text,
        product_category=category_obj,
        description=description,
        preferred_date=pref_date or None,
        preferred_contact=contact if contact in dict(Quote.CONTACT) else "whatsapp",
    )

    return render(
        request,
        "quotes/success.html",
        {"customer_name": full_name, "service": service_obj, "wa_quote_msg": service_whatsapp_message()},
    )
