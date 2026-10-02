from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from .models import Customer, Vehicle


# Django's stock UserAdmin ships a filter sidebar on /admin/auth/user/. The rest
# of this project's changelists have no list_filter, so subclass it without
# any to keep the admin consistent.
admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class RatshieUserAdmin(UserAdmin):
    list_filter = ()


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
    search_fields = ("make", "model", "registration", "customer__full_name")
