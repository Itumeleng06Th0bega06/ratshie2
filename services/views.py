from django.shortcuts import render, get_object_or_404
from django.conf import settings
from .models import Service
from core.utils import service_whatsapp_message


def service_list(request):
    services = Service.objects.filter(is_active=True)
    return render(
        request,
        "services/list.html",
        {
            "services": services,
            "lead": (
                f"Mechanical repairs, diagnostics, quality parts and lubricants, plus "
                f"mobile spares delivery within {settings.SERVICE_RADIUS_KM} km — one "
                f"reliable automotive partner."
            ),
            "crumb_list": [("Services", None)],
            "wa_quote_msg": service_whatsapp_message(),
        },
    )


def service_detail(request, slug):
    service = get_object_or_404(Service, slug=slug, is_active=True)
    related = Service.objects.filter(is_active=True).exclude(pk=service.pk)[:3]
    return render(
        request,
        "services/detail.html",
        {
            "service": service,
            "related": related,
            "crumb_list": [("Services", "services:list"), (service.name, None)],
            "wa_quote_msg": service_whatsapp_message(),
        },
    )
