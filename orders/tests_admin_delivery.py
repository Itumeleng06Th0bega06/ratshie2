"""Tests for the admin order delivery override + read-only order view."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import Order, OrderDeliveryHistory, OrderItem, OrderNotification
from products.models import Product


def create_admin():
    user = get_user_model().objects.create_superuser(
        username="admin", password="pass12345", email="admin@example.com"
    )
    return user


def create_product():
    return Product.objects.create(
        name="Admin Test Part",
        price=Decimal("80.00"),
        availability="in_stock",
        stock=5,
        is_available=True,
        is_active=True,
    )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OrderAdminDeliveryOverrideTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.client.force_login(self.admin)
        self.product = create_product()
        self.order = Order.objects.create(
            customer_name="Deli Buyer",
            email="deli@example.com",
            phone="071 555 0000",
            delivery_option="delivery",
            delivery_address="9 High St",
            status=Order.Status.PAYMENT_PENDING,
            payment_status=Order.Status.PAYMENT_PENDING,
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            quantity=1,
            unit_price=self.product.price,
        )
        self.order.recalc_totals()
        self.order.recalc_delivery_estimate()

    def test_override_page_renders(self):
        url = reverse("admin:orders_order_delivery_override", args=[self.order.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Change Delivery Estimate")

    def test_override_updates_order_and_history(self):
        url = reverse("admin:orders_order_delivery_override", args=[self.order.pk])
        response = self.client.post(
            url,
            {
                "delivery_estimate_from": "2026-11-02",
                "delivery_estimate_to": "2026-11-06",
                "reason": "Stock delay",
                "notify": "",
            },
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_estimate_from, date(2026, 11, 2))
        self.assertEqual(self.order.delivery_estimate_to, date(2026, 11, 6))
        self.assertEqual(self.order.delivery_estimate_source, "admin_override")
        history = self.order.delivery_history.first()
        self.assertIsNotNone(history)
        self.assertEqual(history.reason, "Stock delay")
        self.assertNotEqual(history.previous_from, history.new_from)

    def test_override_notifies_customer(self):
        from django.core import mail

        url = reverse("admin:orders_order_delivery_override", args=[self.order.pk])
        response = self.client.post(
            url,
            {
                "delivery_estimate_from": "2026-11-10",
                "delivery_estimate_to": "2026-11-12",
                "reason": "Updated",
                "notify": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            OrderNotification.objects.filter(
                order=self.order, kind="delivery_update", channel="email", status="sent"
            ).exists()
        )

    def test_readonly_change_form_renders(self):
        url = reverse("admin:orders_order_change", args=[self.order.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delivery Estimate")