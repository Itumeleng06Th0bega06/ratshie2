from django.contrib import admin
from .models import Customer, Vehicle


class VehicleInline(admin.TabularInline):
    model = Vehicle
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "created_at")
    search_fields = ("full_name", "phone", "email")
    inlines = [VehicleInline]


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("make", "model", "year", "registration", "customer")
    list_filter = ("make",)
    search_fields = ("make", "model", "registration", "customer__full_name")
