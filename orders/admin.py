from django import forms
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import Order, OrderItem, OrderDeliveryHistory, OrderNotification
from .notifications import send_order_confirmation, send_delivery_update
from core import delivery


class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ("product", "quantity")

    def clean(self):
        data = super().clean()
        product = data.get("product")
        if not product:
            return data
        original = self.instance
        is_new = original.pk is None
        product_changed = original.product_id != product.pk
        if is_new or product_changed:
            original.product_name = product.name
            original.unit_price = product.price
        return data


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    form = OrderItemForm
    extra = 0
    autocomplete_fields = ("product",)
    readonly_fields = ("line_total",)
    ordering = ("pk",)
    verbose_name_plural = "items"
    template = "admin/edit_inline/order_items.html"

    @admin.display(description="Line total")
    def line_total(self, obj):
        return f"R {obj.line_total:,.2f}" if obj.unit_price else "—"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "quantity", "unit_price", "line_total")
    search_fields = ("product_name", "order__reference", "product__name")
    list_filter = ("order__status",)

    @admin.display(description="Line total")
    def line_total(self, obj):
        return f"R {obj.line_total:,.2f}" if obj.unit_price else "—"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "customer_name",
        "phone",
        "items_count",
        "total",
        "status",
        "payment_status",
        "delivery_option",
        "created_at",
    )
    list_editable = ("status", "payment_status")
    list_filter = ("status", "payment_status", "delivery_option")
    search_fields = ("reference", "payment_reference", "customer_name", "phone", "email", "notes")
    date_hierarchy = "created_at"
    readonly_fields = (
        "reference",
        "created_at",
        "updated_at",
        "delivery_estimate_from",
        "delivery_estimate_to",
        "delivery_estimate_source",
    )
    save_on_top = True
    inlines = [OrderItemInline]
    change_list_template = "admin/orders/order/changelist.html"
    change_form_template = "admin/orders/order/change_form.html"
    actions = ["mark_processing", "mark_ready", "mark_completed", "mark_cancelled"]

    def changelist_view(self, request, extra_context=None):
        qs = self.get_queryset(request)
        extra_context = extra_context or {}
        extra_context["order_stats"] = {
            "total": qs.count(),
            "pending": qs.filter(status="pending").count(),
            "processing": qs.filter(status="processing").count(),
            "completed": qs.filter(status="completed").count(),
            "cancelled": qs.filter(status="cancelled").count(),
        }
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description="# Items")
    def items_count(self, obj):
        return obj.items.count()

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        urls = super().get_urls()
        custom = [
            path(
                "<int:order_pk>/delivery/",
                self.admin_site.admin_view(self.order_delivery_override),
                name="%s_%s_delivery_override" % info,
            ),
        ]
        return custom + urls

    def order_delivery_override(self, request, order_pk):
        order = Order.objects.get(pk=order_pk)
        est_from = order.delivery_estimate_from
        est_to = order.delivery_estimate_to

        if request.method == "POST":
            new_from = request.POST.get("delivery_estimate_from")
            new_to = request.POST.get("delivery_estimate_to")
            reason = request.POST.get("reason", "").strip()
            notify = request.POST.get("notify") == "on"

            from datetime import datetime

            try:
                if new_from:
                    new_from = datetime.strptime(new_from, "%Y-%m-%d").date()
                else:
                    new_from = est_from
            except (ValueError, TypeError):
                new_from = est_from

            try:
                if new_to:
                    new_to = datetime.strptime(new_to, "%Y-%m-%d").date()
                else:
                    new_to = est_to
            except (ValueError, TypeError):
                new_to = est_to

            prev_from = order.delivery_estimate_from
            prev_to = order.delivery_estimate_to

            order.delivery_estimate_from = new_from
            order.delivery_estimate_to = new_to
            order.delivery_estimate_source = "admin_override"
            order.delivery_estimate_updated_at = timezone.now()
            order.save()

            OrderDeliveryHistory.objects.create(
                order=order,
                previous_from=prev_from,
                previous_to=prev_to,
                new_from=new_from,
                new_to=new_to,
                reason=reason if reason else "Admin override",
            )

            if notify:
                send_delivery_update(order, reason=reason or "Admin override")

            messages.success(request, "Delivery estimate updated successfully.")
            return redirect("admin:orders_order_change", order.pk)

        class DeliveryOverrideForm(forms.Form):
            delivery_estimate_from = forms.DateField(
                widget=admin.widgets.AdminDateWidget,
                required=False,
            )
            delivery_estimate_to = forms.DateField(
                widget=admin.widgets.AdminDateWidget,
                required=False,
            )
            reason = forms.CharField(
                widget=forms.Textarea(attrs={"rows": 3}),
                required=False,
                label="Reason for change",
            )
            notify = forms.BooleanField(
                required=False,
                initial=False,
                label="Send notification to customer",
            )

        form = DeliveryOverrideForm(
            initial={
                "delivery_estimate_from": est_from,
                "delivery_estimate_to": est_to,
            }
        )

        context = {
            "order": order,
            "form": form,
            "est_from": est_from,
            "est_to": est_to,
            "title": "Change Delivery Estimate",
        }
        return render(request, "admin/orders/order/delivery_override_form.html", context)


@admin.register(OrderDeliveryHistory)
class OrderDeliveryHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "previous_from", "previous_to", "new_from", "new_to", "reason", "created_at", "notified_email", "notified_sms")
    list_filter = ("created_at",)
    search_fields = ("order__reference", "reason")
    date_hierarchy = "created_at"


@admin.register(OrderNotification)
class OrderNotificationAdmin(admin.ModelAdmin):
    list_display = ("order", "kind", "channel", "status", "created_at")
    list_filter = ("kind", "channel", "status", "created_at")
    search_fields = ("order__reference", "created_at")
    date_hierarchy = "created_at"