from django import forms
from django.contrib import admin
from django.utils.html import format_html, mark_safe
from .models import Product, ProductEnquiry, ProductImage, ProductCategory, ProductGroup

from core.admin_utils import fmt_money, safe_display
from . import checks  # noqa: F401  (registers ratshie.admin system checks)


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

    @safe_display()
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


class ProductAdminForm(forms.ModelForm):
    """Form for Product admin with delivery timeframe validation."""

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Plain-language help so the admin knows the two delivery concepts are
        # separate: timeframe vs charge.
        if "delivery_type" in self.fields:
            self.fields["delivery_type"].help_text = (
                "How this product is charged for delivery. 'Use standard delivery "
                "fee' reads the global fee in Orders > Delivery settings. 'Custom "
                "delivery fee' uses the amount below."
            )
        if "delivery_fee" in self.fields:
            self.fields["delivery_fee"].help_text = (
                "Required only for 'Custom delivery fee'. Enter 0.00 for free "
                "delivery on this product. Delivery is never negative."
            )
        if "delivery_mode" in self.fields:
            self.fields["delivery_mode"].help_text = "Delivery timeframe, not the cost."
        if "availability" in self.fields:
            self.fields["availability"].help_text = (
                "Derived automatically from the stock quantity. In Stock / "
                "Limited Stock / Out of Stock are never chosen by hand."
            )
        if "stock" in self.fields:
            self.fields["stock"].help_text = (
                "How many units you physically have. 10 or more shows no warning "
                "badge; 1–9 shows 'Limited Stock'; 0 shows 'Out of Stock' and "
                "blocks purchase. The badge is automatic."
            )

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

        # Delivery charge: a custom fee is mandatory for CUSTOM and can never be
        # negative. A fee left behind on the standard option is cleared rather
        # than stored, so it can never be mistaken for the amount charged.
        dtype = cleaned.get("delivery_type")
        dfee = cleaned.get("delivery_fee")
        if dfee is not None and dfee < 0:
            self.add_error("delivery_fee", "Delivery fee cannot be negative.")
        if dtype == "custom":
            if dfee is None:
                self.add_error(
                    "delivery_fee", "Enter a delivery fee for 'Custom delivery fee'."
                )
        elif dfee is not None:
            cleaned["delivery_fee"] = None

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

    @safe_display()
    def preview(self, obj):
        if obj.pk and obj.image:
            return format_html(
                '<img src="{}" style="width:70px;height:70px;object-fit:contain;background:#f4f4f6;'
                'border-radius:6px;border:1px solid #e2e2e8"/>',
                obj.image.url,
            )
        return "—"

    preview.short_description = "Preview"

    @safe_display()
    def status_badge(self, obj):
        return _status_badge(obj)

    status_badge.short_description = "Status"

    @safe_display()
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


@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "product_count", "sort_order", "is_active")
    search_fields = ("name", "slug", "description")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}

    @safe_display()
    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


class StockStatusFilter(admin.SimpleListFilter):
    """Filter the product list by the automatic stock status."""

    title = "stock status"
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return (
            ("out", "Out of Stock (0)"),
            ("limited", "Limited Stock (1–9)"),
            ("in", "In Stock (10+)"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "out":
            return queryset.filter(stock__lte=0)
        if value == "limited":
            return queryset.filter(stock__gte=1, stock__lt=Product.STOCK_LIMITED_MIN)
        if value == "in":
            return queryset.filter(stock__gte=Product.STOCK_LIMITED_MIN)
        return queryset


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    inlines = [ProductImageInline]
    change_list_template = "admin/products/product/changelist.html"
    list_display = (
        "thumbnail",
        "name",
        "product_group",
        "price",
        "sale_price_display",
        "delivery_summary",
        "stock",
        "stock_badge",
        "is_active",
    )
    list_display_links = ("thumbnail", "name")
    list_editable = (
        "product_group",
        "price",
        "stock",
        "is_active",
    )
    list_filter = (StockStatusFilter,)
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
        ("Identification", {"fields": ("product_type", "product_group", "name", "slug", "brand", "sku")}),
        ("Description", {"fields": ("short_description", "description")}),
        (
            "Pricing, availability & stock",
            {
                "fields": ("original_price", "price", "discount_display", "stock", "availability"),
                "description": (
                    "The badge is automatic and cannot be set by hand: 10 or more "
                    "shows no warning, 1–9 shows 'Limited Stock', and 0 shows "
                    "'Out of Stock' and blocks purchase. Set the Stock quantity "
                    "below to change the status."
                ),
            },
        ),
        (
            "Delivery fee",
            {
                "fields": ("delivery_type", "delivery_fee", "delivery_summary"),
                "description": (
                    "How this product is charged for delivery. 'Use standard delivery "
                    "fee' uses the global fee set in Orders &gt; Delivery settings. "
                    "'Custom delivery fee' uses the amount above and may be R0.00 for "
                    "free delivery. The standard fee is charged once per order; each "
                    "custom-delivery product adds its own fee once, regardless of quantity."
                ),
            },
        ),
        (
            "Delivery timeframe",
            {
                "fields": ("delivery_mode", "delivery_date_from", "delivery_date_to"),
                "classes": ("collapse",),
                "description": "When the order is expected to arrive. Separate from the delivery charge above.",
            },
        ),
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
    readonly_fields = (
        "created_at",
        "updated_at",
        "discount_display",
        "image_status",
        "member_only_note",
        "delivery_summary",
        "availability",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request=request, obj=obj))
        if obj is not None:
            # SKU is auto-generated and must stay stable once assigned.
            if "sku" not in fields:
                fields.append("sku")
        return fields

    actions = [
        "mark_featured",
        "unmark_featured",
        "set_active",
        "set_inactive",
        "set_member_only",
        "unset_member_only",
    ]

    @safe_display()
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

    @safe_display()
    @admin.display(description="Delivery fee")
    def delivery_summary(self, obj):
        """Read-only summary of how this product is charged for delivery.

        Mirrors the exact server-side rule used at checkout, so staff can see at
        a glance whether a product uses the global standard fee or carries its
        own (possibly R0.00) custom fee.
        """
        from orders.services import product_delivery

        if not obj.pk:
            return "—"
        info = product_delivery(obj)
        if info["type"] == "custom":
            if info["is_free"]:
                return mark_safe(
                    '<span style="color:#1a7f37;font-weight:600">Custom delivery: '
                    "free (R0.00)</span>"
                )
            return format_html(
                '<span style="color:#1a7f37;font-weight:600">Custom delivery: {}</span>',
                fmt_money(info["fee"]),
            )
        return format_html(
            '<span style="color:#667085">Standard delivery ({})</span>',
            fmt_money(info["fee"]),
        )

    @safe_display()
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

    @safe_display()
    @admin.display(description="Stock status", ordering="stock")
    def stock_badge(self, obj):
        """Automatic stock badge, derived from the real quantity.

        Colours match the storefront badge palette. ``10+`` reads 'In Stock'
        in the admin (for filtering clarity) even though the customer badge is
        omitted, so staff can tell at a glance that nothing is wrong.
        """
        color = {
            "out": "#c62828",
            "limited": "#b3560b",
            "in": "#1a7f37",
        }.get(obj.stock_status, "#666")
        label = obj.stock_warning_label or "In Stock"
        return format_html(
            '<span style="color:{};font-weight:600">{} · {}</span>',
            color,
            label,
            obj.stock,
        )

    @safe_display()
    @admin.display(description="Sale price", empty_value="—")
    def sale_price_display(self, obj):
        if not obj.is_on_sale:
            return "—"
        price = format_html('<span style="color:#1a7f37;font-weight:700">→ {}</span>', fmt_money(obj.price))
        if obj.discount_percent is not None:
            return format_html(
                '{} <span style="color:#1a7f37;font-size:11px;font-weight:600">({} OFF)</span>',
                price,
                f"{obj.discount_percent}%",
            )
        return price

    @safe_display()
    @admin.display(description="Discount (read-only)")
    def discount_display(self, obj):
        if not obj.original_price:
            return mark_safe('<span style="color:#666">No original price — not on sale.</span>')
        if obj.is_on_sale:
            return format_html(
                '<span style="color:#1a7f37;font-weight:600">{} OFF</span> '
                '<span style="color:#666">(saving R {})</span>',
                f"{obj.discount_percent}%",
                fmt_money(obj.original_price - obj.price),
            )
        return format_html(
            '<span style="color:#666">Original {} is not above current price — product is not on sale.</span>',
            fmt_money(obj.original_price),
        )

    @safe_display()
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
