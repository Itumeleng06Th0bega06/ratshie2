from django.contrib import admin
from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "price_on_request",
        "is_featured",
        "is_active",
        "sort_order",
    )
    list_editable = ("price", "price_on_request", "is_featured", "is_active", "sort_order")
    list_filter = ("is_featured", "is_active")
    search_fields = ("name", "short_description")
    prepopulated_fields = {"slug": ("name",)}
