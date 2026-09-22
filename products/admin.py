from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html, mark_safe
from .models import Product, ProductEnquiry, ProductImage, ProductCategory


class ProductImageInline(admin.StackedInline):
    model = ProductImage
    extra = 0
    fields = (
        "preview",
        "image",
        "alt_text",
        "status",
        "is_primary",
        "sort_order",
        "image_source",
        "source_url",
        "verification_notes",
    )
    readonly_fields = ("preview",)
    ordering = ("sort_order", "id")
    verbose_name_plural = "Product images (first = shown first; tick 'Primary' for the main image)"

    def preview(self, obj):
        if obj.pk and obj.image:
            return format_html(
                '<div style="display:flex;align-items:center;gap:12px">'
                '<img src="{}" style="width:64px;height:64px;object-fit:contain;background:#f4f4f6;'
                'border-radius:8px;border:1px solid #e2e2e8"/>'
                '<div style="display:flex;flex-direction:column;gap:4px">'
                '{}<span style="font-size:12px;color:#667085">{}</span></div></div>',
                obj.image.url,
                _status_badge(obj),
                obj.image.name,
            )
        return mark_safe('<span style="color:#999">No image yet — use the Image field below to upload.</span>')

    preview.short_description = "Current image"


from django import forms
from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html, mark_safe
from .models import Product, ProductEnquiry, ProductImage, ProductCategory


class ProductAdminForm(forms.ModelForm):
    """Form for Product admin with delivery mode validation."""

    class Meta:
        model = Product
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("delivery_mode")

        # Validate mode-specific requirements
        if mode == "specific" and not cleaned.get("delivery_date_from"):
            raise forms.ValidationError(
                {"delivery_mode": "Specific date mode requires delivery_date_from."}
            )
        if mode == "range":
            if not cleaned.get("delivery_date_from") or not cleaned.get("delivery_date_to"):
                raise forms.ValidationError(
                    {
                        "delivery_mode": "Range mode requires both delivery_date_from and delivery_date_to."
                    }
                )
            if cleaned.get("delivery_date_to") and cleaned.get("delivery_date_from"):
                if cleaned["delivery_date_to"] < cleaned["delivery_date_from"]:
                    raise forms.ValidationError(
                        {"delivery_date_to": "End date must be after start date."}
                    )
        # When mode is standard, the admin save_model will clear date fields
        return cleaned


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = (
        "preview",
        "product",
        "status_badge",
        "status",
        "optimized",
        "source_url",
        "alt_text",
        "sort_order",
        "is_primary",
    )
    list_filter = ("status", "is_primary", "product__brand")
    search_fields = ("product__name", "product__sku", "alt_text", "source_url", "image_source")
    raw_id_fields = ("product",)
    list_select_related = ("product",)
    list_editable = ("status", "is_primary", "sort_order")
    date_hierarchy = "created_at"
    readonly_fields = ("preview", "created_at")
    fields = (
        "product",
        "image",
        "preview",
        "alt_text",
        "status",
        "image_source",
        "source_url",
        "verification_notes",
        "sort_order",
        "is_primary",
    )
    actions = ["mark_verified", "mark_rejected", "mark_pending"]

    def preview(self, obj):
        if obj.pk and obj.image:
            return format_html(
                '<img src="{}" style="width:70px;height:70px;object-fit:contain;background:#f4f4f6;'
                'border-radius:6px;border:1px solid #e2e2e8"/>',
                obj.image.url,
            )
        return "—"

    preview.short_description = "Preview"

    def status_badge(self, obj):
        return _status_badge(obj)

    status_badge.short_description = "Status"

    def optimized(self, obj):
        return obj.is_optimized

    optimized.short_description = "WebP"
    optimized.boolean = True

    @admin.action(description="Mark selected images as VERIFIED")
    def mark_verified(self, request, queryset):
        n = queryset.update(status=ProductImage.Status.VERIFIED)
        self.message_user(request, f"{n} image(s) marked VERIFIED.")

    @admin.action(description="Mark selected images as REJECTED")
    def mark_rejected(self, request, queryset):
        n = queryset.update(status=ProductImage.Status.REJECTED)
        self.message_user(request, f"{n} image(s) marked REJECTED.")

    @admin.action(description="Mark selected images as PENDING")
    def mark_pending(self, request, queryset):
        n = queryset.update(status=ProductImage.Status.PENDING)
        self.message_user(request, f"{n} image(s) marked PENDING.")


def _status_badge(obj):
    color = {
        "VERIFIED": "#1a7f37",
        "PENDING": "#b3560b",
        "REJECTED": "#c62828",
    }.get(obj.status, "#666")
    return format_html('<span style="color:{};font-weight:700">{}</span>', color, obj.get_status_display())


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    search_fields = ("name", "slug", "description")
    list_editable = ("sort_order", "is_active")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    inlines = [ProductImageInline]
    list_display = (
        "thumbnail",
        "name",
        "product_type",
        "brand",
        "sku",
        "price",
        "sale_price_display",
        "discount",
        "purchase_restriction",
        "is_member_only",
        "is_available",
        "is_featured",
        "is_active",
    )
    list_display_links = ("thumbnail", "name")
    list_editable = (
        "product_type",
        "price",
        "is_member_only",
        "is_available",
        "is_featured",
        "is_active",
    )
    list_filter = ("product_type", "availability", "is_featured", "is_active", "is_available", "is_member_only", "brand")
    search_fields = ("name", "sku", "brand", "description", "short_description", "vehicle_makes")
    list_per_page = 50
    prepopulated_fields = {"slug": ("name",)}
    save_on_top = True

    fieldsets = (
        (
            "DEMO CATALOGUE DATA",
            {
                "fields": (),
                "classes": ("wide",),
                "description": (
                    "⚠ DEMO PRICE — VERIFY BEFORE PRODUCTION. Product prices and details are "
                    "demonstration (seed) data. Update them before launching the store."
                ),
            },
        ),
        ("Identification", {"fields": ("product_type", "name", "slug", "brand", "sku")}),
        ("Description", {"fields": ("short_description", "description")}),
        ("Pricing & discount", {"fields": ("original_price", "price", "discount_display", "availability")}),
        ("Delivery", {"fields": ("delivery_mode", "delivery_date_from", "delivery_date_to"), "classes": ("collapse",)}),
        ("Images", {"fields": ("image_status",)}),
        ("Vehicle compatibility", {"fields": ("vehicle_makes", "vehicle_models"), "classes": ("collapse",)}),
        ("Lubricant details", {"fields": ("viscosity", "volume", "oil_type", "spec"), "classes": ("collapse",)}),
        ("Technical specifications", {"fields": ("specifications",), "classes": ("collapse",)}),
        ("Badges & status", {"fields": ("is_featured", "is_new", "is_genuine", "is_available", "is_active")}),
        (
            "Purchase access",
            {
                "fields": ("is_member_only", "member_only_note"),
                "classes": ("wide",),
            },
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at", "updated_at", "discount_display", "image_status", "member_only_note")

    actions = [
        "mark_featured",
        "unmark_featured",
        "set_active",
        "set_inactive",
        "set_member_only",
        "unset_member_only",
    ]

    @admin.display(description="Members only", boolean=True)
    def purchase_restriction(self, obj):
        return obj.is_member_only

    purchase_restriction.short_description = "Members only"

    def member_only_note(self, obj):
        if not obj.is_on_sale and not obj.is_member_only:
            return mark_safe(
                '<span style="color:#666">This product is open to everyone. Ticking '
                "<b>Member-only purchase</b> restricts buying (not viewing) to registered "
                "members — recommended for sale items.</span>"
            )
        if obj.is_member_only and not obj.is_on_sale:
            return mark_safe(
                '<span style="color:#b3560b;font-weight:600">Members-only, not currently '
                "on sale. Registering members can buy this; visitors can only view.</span>"
            )
        if not obj.is_member_only and obj.is_on_sale:
            return mark_safe(
                '<span style="color:#b3560b;font-weight:600">⚠ This product is ON SALE but '
                "sale items normally require registration — any visitor can currently buy "
                "it. Tick <b>Member-only purchase</b> to gate it.</span>"
            )
        return mark_safe(
            '<span style="color:#1a7f37;font-weight:600">✓ On sale + members-only. Visitors '
            "see the deal; only registered members can purchase.</span>"
        )

    member_only_note.short_description = "Guidance"

    @admin.display(description="Img")
    def thumbnail(self, obj):
        img_url = obj.primary_image_url
        if img_url:
            return format_html(
                '<img src="{}" style="width:44px;height:44px;object-fit:contain;background:#fff;'
                'border-radius:6px;border:1px solid #eee" />',
                img_url,
            )
        return "—"

    @admin.display(description="Stock")
    def stock_badge(self, obj):
        color = "#1a7f37" if obj.in_stock else "#b3560b" if obj.availability == "on_request" else "#c62828"
        label = obj.get_availability_display()
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, label)

    @admin.display(description="Sale price", empty_value="—")
    def sale_price_display(self, obj):
        return f"→ R {obj.price:,.2f}" if obj.is_on_sale else "—"

    @admin.display(description="Discount")
    def discount(self, obj):
        if obj.is_on_sale and obj.discount_percent is not None:
            return f"{obj.discount_percent}% OFF"
        return "—"

    @admin.display(description="Discount (read-only)")
    def discount_display(self, obj):
        if not obj.original_price:
            return mark_safe('<span style="color:#666">No original price — not on sale.</span>')
        if obj.is_on_sale:
            return format_html(
                '<span style="color:#1a7f37;font-weight:600">{} OFF</span> '
                '<span style="color:#666">(saving R {:,})</span>',
                f"{obj.discount_percent}%",
                obj.original_price - obj.price,
            )
        return format_html(
            '<span style="color:#666">Original {} is not above current price — product is not on sale.</span>',
            f"R {obj.original_price:,.2f}",
        )

    @admin.display(description="Image status")
    def image_status(self, obj):
        verified = obj.verified_images
        if verified:
            n = verified.count()
            return mark_safe(
                f'<span style="color:#1a7f37;font-weight:600">✓ {n} image(s) VERIFIED and published.</span>'
            )
        total = obj.images.count()
        if total:
            pending = obj.images.filter(status=ProductImage.Status.PENDING).count()
            return mark_safe(
                f'<span style="color:#b3560b;font-weight:600">⚠ No VERIFIED image yet '
                f'({pending} pending / {total} total). Nothing is shown to the public.</span>'
            )
        return mark_safe(
            '<span style="color:#c62828;font-weight:600">⚠ No images. Upload and VERIFY before publishing.</span>'
        )

    @admin.action(description="Mark selected as featured")
    def mark_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} product(s) marked as featured.")

    @admin.action(description="Unmark selected as featured")
    def unmark_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} product(s) unmarked as featured.")

    @admin.action(description="Set selected as active")
    def set_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} product(s) activated.")

    @admin.action(description="Set selected as inactive")
    def set_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} product(s) deactivated.")

    @admin.action(description="Restrict selected to registered members only")
    def set_member_only(self, request, queryset):
        updated = queryset.update(is_member_only=True)
        self.message_user(request, f"{updated} product(s) restricted to registered members.")

    @admin.action(description="Open selected to all visitors")
    def unset_member_only(self, request, queryset):
        updated = queryset.update(is_member_only=False)
        self.message_user(request, f"{updated} product(s) opened to all visitors.")

    def save_model(self, request, obj, form, change):
        # When delivery mode switches to standard, clear date fields
        if obj.delivery_mode == "standard":
            obj.delivery_date_from = None
            obj.delivery_date_to = None
        super().save_model(request, obj, form, change)


@admin.register(ProductEnquiry)
class ProductEnquiryAdmin(admin.ModelAdmin):
    list_display = (
        "product_name",
        "product",
        "customer",
        "quantity",
        "status",
        "preferred_contact",
        "created_at",
    )
    list_filter = ("status", "preferred_contact", "created_at")
    search_fields = ("product_name", "message", "vehicle_make", "vehicle_model", "customer__full_name")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    actions = ["mark_in_progress", "mark_closed"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product", "customer")

    @admin.action(description="Mark selected enquiries as In Progress")
    def mark_in_progress(self, request, queryset):
        queryset.update(status="in_progress")
        self.message_user(request, "Selected enquiries marked as In Progress.")

    @admin.action(description="Mark selected enquiries as Closed")
    def mark_closed(self, request, queryset):
        queryset.update(status="closed")
        self.message_user(request, "Selected enquiries marked as Closed.")
