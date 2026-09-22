from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "customer",
        "service_name",
        "preferred_date",
        "preferred_time",
        "status",
        "created_at",
    )
    list_filter = ("status", "preferred_time")
    search_fields = ("customer__full_name", "service_name", "registration")
    readonly_fields = ("created_at",)
