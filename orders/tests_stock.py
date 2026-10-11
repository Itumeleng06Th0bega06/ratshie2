"""Stock deduction tests for the order/payment flow.

Stock is reduced exactly once, at the confirmed payment stage. These tests
prove that duplicate payment notifications cannot double-deduct, that failed or
cancelled orders never restore (or deduct) stock incorrectly, and that a race
for the last unit can never drive stock negative.

Runs against Django's throwaway test database, so ``db.sqlite3`` is untouched.
"""
from decimal import Decimal
import itertools
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from core.utils import amount_str, payfast_sign
from payments.models import Payment
from products.models import Product
from products.stock import deduct_stock_for_order

from .models import Order, OrderItem

TEST_PAYFAST = {
    "PAYFAST_MERCHANT_ID": "10054184",
    "PAYFAST_MERCHANT_KEY": "qj6m1q1x51moy",
    "PAYFAST_PASSPHRASE": "testpassphrase",
    "PAYFAST_SANDBOX": True,
    "PAYFAST_RETURN_URL_PREFIX": "http://127.0.0.1:8000",
}

_counter = itertools.count(1)


def make_product(**overrides):
    defaults = {
        "name": f"Stock Part {next(_counter)}",
        "price": Decimal("100.00"),
        "stock": 10,
        "is_available": True,
        "is_active": True,
        "is_member_only": False,
    }
    defaults.update(overrides)
    return Product.objects.create(**defaults)


def make_order_with_item(product, qty):
    order = Order.objects.create(
        status=Order.Status.PAYMENT_PENDING,
        payment_status=Order.Status.PAYMENT_PENDING,
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=qty,
        unit_price=product.price,
    )
    order.recalc_totals()
    return order


def make_payment(order, reference="PF-STOCK-1"):
    return Payment.objects.create(
        reference=reference,
        order=order,
        amount=order.total,
        description="Stock test order",
    )


def itn_payload(payment, payment_status="COMPLETE", **overrides):
    data = {
        "m_payment_id": payment.reference,
        "merchant_id": "10054184",
        "merchant_key": "qj6m1q1x51moy",
        "pf_payment_id": "56789000",
        "payment_status": payment_status,
        "item_name": payment.description,
        "amount": amount_str(payment.amount),
    }
    data.update(overrides)
    data["signature"] = payfast_sign(data)
    return data


class DeductStockForOrderTests(TestCase):
    def test_deducts_stock_once(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 3)
        self.assertTrue(deduct_stock_for_order(order))
        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 7)
        self.assertTrue(order.stock_deducted)
        self.assertIsNotNone(order.stock_deducted_at)

    def test_second_call_is_a_no_op(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 3)
        deduct_stock_for_order(order)
        self.assertFalse(deduct_stock_for_order(order))
        product.refresh_from_db()
        self.assertEqual(product.stock, 7)

    def test_shortfall_is_clamped_to_zero_never_negative(self):
        product = make_product(stock=2)
        order = make_order_with_item(product, 5)
        deduct_stock_for_order(order)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)

    def test_missing_product_is_skipped(self):
        order = Order.objects.create(
            status=Order.Status.PAYMENT_PENDING,
            payment_status=Order.Status.PAYMENT_PENDING,
        )
        OrderItem.objects.create(
            order=order, product=None, product_name="Gone", quantity=2, unit_price=10
        )
        self.assertTrue(deduct_stock_for_order(order))
        order.refresh_from_db()
        self.assertTrue(order.stock_deducted)

    def test_conditional_decrement_guard_prevents_oversell(self):
        product = make_product(stock=1)
        from django.db.models import F

        first = Product.objects.filter(pk=product.pk, stock__gte=1).update(
            stock=F("stock") - 1
        )
        second = Product.objects.filter(pk=product.pk, stock__gte=1).update(
            stock=F("stock") - 1
        )
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)


class ConcurrentDeductionTests(TestCase):
    """Two orders competing for the same last unit must never oversell.

    The database serialises the writes and the conditional decrement
    (``filter(stock__gte=qty)``) rejects the loser, so stock can never go
    negative. SQLite's shared-cache test database does not support true
    parallel writers, so this exercises the same guard the workers rely on.
    """

    def test_concurrent_orders_cannot_oversell(self):
        product = make_product(stock=1)
        o1 = make_order_with_item(product, 1)
        o2 = make_order_with_item(product, 1)

        # Both orders were created while a unit still appeared available (the
        # classic race), then both payments confirm.
        deduct_stock_for_order(o1)
        deduct_stock_for_order(o2)

        product.refresh_from_db()
        self.assertEqual(product.stock, 0)
        self.assertGreaterEqual(product.stock, 0)


@override_settings(**TEST_PAYFAST)
class ItnStockDeductionTests(TestCase):
    def _post(self, payment, payment_status="COMPLETE"):
        url = reverse("payments:itn")
        data = itn_payload(payment, payment_status=payment_status)
        with mock.patch("payments.views._validated_by_payfast", return_value=True):
            return self.client.post(url, data)

    def test_success_itn_deducts_stock(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 4)
        payment = make_payment(order)

        response = self._post(payment)

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 6)
        self.assertTrue(order.stock_deducted)

    def test_duplicate_success_itn_deducts_only_once(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 4)
        payment = make_payment(order)

        self._post(payment)
        self._post(payment)  # PayFast retries the same notification

        product.refresh_from_db()
        self.assertEqual(product.stock, 6)

    def test_failed_itn_does_not_deduct_stock(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 4)
        payment = make_payment(order)

        response = self._post(payment, payment_status="FAILED")

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 10)
        self.assertFalse(order.stock_deducted)
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_failed_after_success_does_not_restore_or_double_deduct(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 4)
        payment = make_payment(order)

        self._post(payment)  # success -> stock 6
        self._post(payment, payment_status="FAILED")  # late failure notification

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 6)  # unchanged: no restore, no re-deduct
        self.assertTrue(order.stock_deducted)
        self.assertEqual(order.status, Order.Status.PAID)


class AdminMarkPaidDeductsStockTests(TestCase):
    """Marking an order paid in the admin (e.g. an offline payment) deducts."""

    def _admin(self):
        from django.contrib.admin.sites import AdminSite
        from orders.admin import OrderAdmin

        return OrderAdmin(Order, AdminSite())

    def _fake_form(self, order):
        from types import SimpleNamespace

        return SimpleNamespace(instance=order, save_m2m=lambda: None)

    def test_marking_paid_via_admin_deducts_once(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 2)
        order.payment_status = Order.Status.PAID
        order.save(update_fields=["payment_status"])

        admin_obj = self._admin()
        # save_related is what both the change form and list_editable call.
        admin_obj.save_related(None, self._fake_form(order), [], change=True)
        admin_obj.save_related(None, self._fake_form(order), [], change=True)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 8)
        self.assertTrue(order.stock_deducted)

    def test_still_pending_order_does_not_deduct(self):
        product = make_product(stock=10)
        order = make_order_with_item(product, 2)  # payment_pending

        admin_obj = self._admin()
        admin_obj.save_related(None, self._fake_form(order), [], change=True)

        product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(product.stock, 10)
        self.assertFalse(order.stock_deducted)
