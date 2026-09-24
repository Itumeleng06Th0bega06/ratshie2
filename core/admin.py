from django.contrib import admin
from .models import SiteConfig, FAQ, Testimonial, Notification, PublicHoliday
from .forms import HoneypottedAdminAuthenticationForm

# Harden the shared admin login form with a hidden honeypot + per-IP cooldown.
# Assigned here (not in the AdminSite subclass) so the site-wide admin site
# keeps every model registered by @admin.register across all apps.
admin.site.login_form = HoneypottedAdminAuthenticationForm


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name")
    search_fields = ("name", "date")
    ordering = ("date",)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("site_name", "phone_display", "whatsapp_display", "email", "address", "standard_delivery_days")
    # Singleton: one editable record
    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "vehicle", "rating", "is_active", "created_at")
    list_filter = ("is_active", "rating")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "level", "is_read", "created_at")
    list_editable = ("is_read",)
    list_filter = ("is_read", "level")
    search_fields = ("title", "text")
    date_hierarchy = "created_at"
    readonly_fields = ("key", "created_at", "updated_at")
