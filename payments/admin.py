from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "customer",
        "amount",
        "status",
        "payfast_transaction_id",
        "created_at",
    )
    search_fields = ("reference", "customer__full_name", "payfast_transaction_id")
    readonly_fields = ("reference", "created_at", "updated_at", "raw_response")
