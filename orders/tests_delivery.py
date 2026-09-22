"""Tests for the delivery-estimate and customer-notification system."""
from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from core import delivery
from core.models import PublicHoliday, SiteConfig
from orders.models import (
    Order,
    OrderDeliveryHistory,
    OrderItem,
    OrderNotification,
)
from orders.notifications import send_order_confirmation, send_delivery_update
from payments.models import Payment
from products.models import Product


def create_product(**overrides):
    defaults = {
        "name": "Test Part",
        "price": Decimal("50.00"),
        "availability": "in_stock",
        "stock": 5,
        "is_available": True,
        "is_active": True,
    }
    defaults.update(overrides)
    return Product.objects.create(**defaults)


def create_order(product, delivery_option="delivery"):
    order = Order.objects.create(
        customer_name="Test Customer",
        email="customer@example.com",
        phone="071 555 1234",
        delivery_option=delivery_option,
        delivery_address="1 Main St" if delivery_option == "delivery" else "",
        delivery_fee=Decimal("40.00"),
        status=Order.Status.PAYMENT_PENDING,
        payment_status=Order.Status.PAYMENT_PENDING,
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=1,
        unit_price=product.price,
    )
    order.recalc_totals()
    return order


class BusinessDayCalculationTests(TestCase):
    def test_add_business_days_skips_weekend(self):
        # Friday + 1 business day = Monday
        friday = date(2026, 9, 11)
        self.assertEqual(delivery.add_business_days(friday, 1), date(2026, 9, 14))

    def test_add_business_days_multi_week(self):
        monday = date(2026, 9, 7)
        self.assertEqual(delivery.add_business_days(monday, 5), date(2026, 9, 14))

    def test_add_business_days_zero_returns_start(self):
        d = date(2026, 9, 11)
        self.assertEqual(delivery.add_business_days(d, 0), d)

    def test_public_holiday_skipped(self):
        PublicHoliday.objects.create(date=date(2026, 9, 11), name="Test Holiday")
        thursday = date(2026, 9, 10)
        # Thursday + 1 business day skips Friday (holiday) -> Monday
        self.assertEqual(delivery.add_business_days(thursday, 1), date(2026, 9, 14))

    def test_standard_delivery_days_from_config(self):
        cfg = SiteConfig.load()
        cfg.standard_delivery_days = 3
        cfg.save()
        self.assertEqual(delivery.standard_delivery_days(), 3)

    def test_format_single_date(self):
        self.assertEqual(
            delivery.format_delivery_estimate(date(2026, 9, 18)),
            "18 September 2026",
        )

    def test_format_same_month_range(self):
        self.assertEqual(
            delivery.format_delivery_estimate(date(2026, 9, 18), date(2026, 9, 22)),
            "18–22 September 2026",
        )

    def test_format_cross_month_range(self):
        self.assertEqual(
            delivery.format_delivery_estimate(date(2026, 9, 28), date(2026, 10, 2)),
            "28 September 2026–2 October 2026",
        )

    def test_format_empty(self):
        self.assertEqual(delivery.format_delivery_estimate(None), "")
        self.assertEqual(delivery.format_delivery_estimate(None, None), "")


class ProductDeliveryWindowTests(TestCase):
    def test_standard_mode_uses_business_days(self):
        SiteConfig.load().standard_delivery_days = 7
        SiteConfig.load().save()
        product = create_product()
        order_date = date(2026, 9, 11)  # Friday
        f, t = delivery.product_delivery_window(product, order_date)
        self.assertEqual(f, order_date)
        expected_end = delivery.add_business_days(order_date, 7)
        self.assertEqual(t, expected_end)

    def test_specific_date_mode(self):
        product = create_product(
            delivery_mode="specific", delivery_date_from=date(2026, 10, 1)
        )
        f, t = delivery.product_delivery_window(product, date(2026, 9, 11))
        self.assertEqual(f, date(2026, 10, 1))
        self.assertEqual(t, date(2026, 10, 1))

    def test_range_mode(self):
        product = create_product(
            delivery_mode="range",
            delivery_date_from=date(2026, 10, 5),
            delivery_date_to=date(2026, 10, 9),
        )
        f, t = delivery.product_delivery_window(product, date(2026, 9, 11))
        self.assertEqual(f, date(2026, 10, 5))
        self.assertEqual(t, date(2026, 10, 9))


class OrderDeliveryWindowTests(TestCase):
    def test_order_uses_latest_product_window(self):
        p1 = create_product(name="Fast", delivery_mode="specific", delivery_date_from=date(2026, 10, 1))
        p2 = create_product(name="Slow", delivery_mode="specific", delivery_date_from=date(2026, 10, 8))
        order = create_order(p1)
        OrderItem.objects.create(
            order=order, product=p2, product_name=p2.name, quantity=1, unit_price=p2.price
        )
        f, t = delivery.order_delivery_window(order)
        self.assertEqual(f, date(2026, 10, 8))
        self.assertEqual(t, date(2026, 10, 8))

    def test_recalc_delivery_estimate_sets_fields(self):
        product = create_product()
        order = create_order(product)
        order.recalc_delivery_estimate()
        self.assertIsNotNone(order.delivery_estimate_from)
        self.assertIsNotNone(order.delivery_estimate_to)
        self.assertEqual(order.delivery_estimate_source, "product")

    def test_recalc_uses_created_at_when_no_override(self):
        product = create_product()
        order = create_order(product)
        order.created_at = timezone.now() - timedelta(days=2)
        order.save(update_fields=["created_at"])
        f, _ = order.recalc_delivery_estimate()
        self.assertEqual(f, timezone.localdate() - timedelta(days=2))


class DeliveryEstimateDisplayTests(TestCase):
    def test_admin_override_display(self):
        product = create_product()
        order = create_order(product)
        order.delivery_estimate_from = date(2026, 10, 1)
        order.delivery_estimate_to = date(2026, 10, 3)
        order.delivery_estimate_source = "admin_override"
        order.save()
        self.assertEqual(
            delivery.format_delivery_estimate(
                order.delivery_estimate_from, order.delivery_estimate_to
            ),
            "1–3 October 2026",
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SMS_API_URL="",
    SMS_API_KEY="",
)
class NotificationTests(TestCase):
    def test_order_confirmation_email_sent(self):
        product = create_product()
        order = create_order(product)
        order.recalc_delivery_estimate()
        send_order_confirmation(order)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Confirmed", mail.outbox[0].subject)
        self.assertIn(order.email, mail.outbox[0].to)
        record = OrderNotification.objects.filter(
            order=order, kind="confirmation", channel="email"
        ).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "sent")

    def test_confirmation_is_idempotent(self):
        product = create_product()
        order = create_order(product)
        order.recalc_delivery_estimate()
        send_order_confirmation(order)
        send_order_confirmation(order)
        self.assertEqual(len(mail.outbox), 1)

    def test_sms_failure_recorded_when_no_provider(self):
        product = create_product()
        order = create_order(product)
        order.recalc_delivery_estimate()
        send_order_confirmation(order)
        record = OrderNotification.objects.filter(
            order=order, kind="confirmation", channel="sms"
        ).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "failed")
        self.assertTrue(record.failure_reason)

    def test_delivery_update_sends_and_records_history(self):
        product = create_product()
        order = create_order(product)
        order.recalc_delivery_estimate()
        prev_from, prev_to = order.delivery_estimate_from, order.delivery_estimate_to
        order.delivery_estimate_from = date(2026, 11, 2)
        order.delivery_estimate_to = date(2026, 11, 6)
        order.delivery_estimate_source = "admin_override"
        order.save()
        send_delivery_update(order, reason="Stock delay")
        self.assertEqual(len(mail.outbox), 1)
        rec = OrderNotification.objects.filter(
            order=order, kind="delivery_update"
        ).first()
        self.assertIsNotNone(rec)


class OrderHistoryModelTests(TestCase):
    def test_history_record_created(self):
        product = create_product()
        order = create_order(product)
        OrderDeliveryHistory.objects.create(
            order=order,
            previous_from=date(2026, 10, 1),
            previous_to=date(2026, 10, 3),
            new_from=date(2026, 11, 1),
            new_to=date(2026, 11, 5),
            reason="Supplier delay",
        )
        self.assertEqual(order.delivery_history.count(), 1)
        entry = order.delivery_history.first()
        self.assertEqual(entry.reason, "Supplier delay")
        self.assertEqual(entry.new_from, date(2026, 11, 1))