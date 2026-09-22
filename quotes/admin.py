from django.contrib import admin
from .models import Quote


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "customer",
        "quote_type",
        "vehicle_make",
        "vehicle_model",
        "status",
        "amount",
        "preferred_date",
        "created_at",
    )
    list_filter = ("status", "quote_type", "preferred_contact")
    search_fields = ("customer__full_name", "description", "vehicle_make", "vehicle_model")
    readonly_fields = ("created_at",)
