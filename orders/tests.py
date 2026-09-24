"""Integration tests for the cart -> checkout -> PayFast payment flow."""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from django.contrib.auth import get_user_model

from customers.models import Customer
from orders.models import Order, OrderItem
from payments.models import Payment
from products.models import Product

TEST_PAYFAST = {
    "PAYFAST_MERCHANT_ID": "10054184",
    "PAYFAST_MERCHANT_KEY": "qj6m1q1x51moy",
    "PAYFAST_PASSPHRASE": "Rodricks.Ratshie.911",
    "PAYFAST_SANDBOX": True,
    "PAYFAST_RETURN_URL_PREFIX": "http://127.0.0.1:8000",
}


def create_product(**overrides):
    defaults = {
        "name": "Brake Disc",
        "price": Decimal("100.00"),
        "availability": "in_stock",
        "stock": 5,
        "is_available": True,
        "is_active": True,
        "is_member_only": False,
    }
    defaults.update(overrides)
    return Product.objects.create(**defaults)


def add_to_cart(client, product, qty=1):
    return client.post(
        reverse("orders:cart_add", kwargs={"slug": product.slug}),
        {"quantity": str(qty)},
    )


@override_settings(**TEST_PAYFAST)
class CartCheckoutIntegrationTests(TestCase):
    def test_full_checkout_creates_order_and_payment(self):
        product = create_product()
        add_to_cart(self.client, product, qty=2)

        response = self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Test Buyer",
                "email": "buyer@example.com",
                "phone": "071 555 1234",
                "delivery_option": "collection",
            },
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(customer_name="Test Buyer")
        payment = Payment.objects.get(order=order)
        self.assertRedirects(
            response,
            reverse("payments:details", kwargs={"reference": payment.reference}),
        )
        self.assertEqual(order.status, Order.Status.PAYMENT_PENDING)
        self.assertEqual(order.payment_status, Order.Status.PAYMENT_PENDING)
        self.assertEqual(order.total, product.price * 2)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(payment.amount, order.total)
        self.assertEqual(payment.reference, order.payment_reference)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_checkout_requires_customer_details(self):
        product = create_product()
        add_to_cart(self.client, product)
        response = self.client.post(reverse("orders:checkout_submit"), {})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("orders:checkout"))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    def test_checkout_with_empty_cart_redirects_to_cart(self):
        response = self.client.post(reverse("orders:checkout_submit"), {})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("orders:cart"))

    def test_order_reference_generated_automatically(self):
        product = create_product()
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "A", "email": "a@b.com", "phone": "071 555 1234"},
        )
        order = Order.objects.get(customer_name="A")
        self.assertTrue(order.reference.startswith("RS-"))
        self.assertGreater(len(order.reference), 5)

    def test_recalc_totals_includes_delivery_fee(self):
        product = create_product()
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "B", "email": "b@b.com", "phone": "071 555 1234", "shipping_method": "standard", "delivery_address": "1 Main St"},
        )
        order = Order.objects.get(customer_name="B")
        self.assertEqual(order.delivery_option, Order.DeliveryChoice.DELIVERY)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        self.assertEqual(order.delivery_address, "1 Main St")
        self.assertEqual(order.delivery_fee, Decimal("99.00"))
        self.assertEqual(order.total, product.price + Decimal("99.00"))

    def test_customer_record_created_and_reused(self):
        product = create_product()
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "Reuse", "email": "r@b.com", "phone": "071 555 4321"},
        )
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "Reuse2", "email": "r2@b.com", "phone": "071 555 4321"},
        )
        self.assertEqual(Customer.objects.filter(phone="071 555 4321").count(), 1)
        self.assertEqual(Order.objects.filter(customer__phone="071 555 4321").count(), 2)

    def test_unavailable_product_blocked_at_checkout(self):
        product = create_product(name="Unavailable", is_available=False)
        self.assertFalse(product.in_stock)
        response = add_to_cart(self.client, product)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response, reverse("products:detail", kwargs={"slug": product.slug})
        )
        self.assertEqual(self.client.session.get("cart", {}), {})


@override_settings(**TEST_PAYFAST)
class MemberRestrictionIntegrationTests(TestCase):
    def setUp(self):
        self.product = create_product(name="Member Deal", is_member_only=True)

    def test_anonymous_user_cannot_add_member_only_product(self):
        response = add_to_cart(self.client, self.product)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response, reverse("products:detail", kwargs={"slug": self.product.slug})
        )
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_authenticated_member_can_purchase(self):
        user = get_user_model().objects.create_user(
            username="member", password="testpass123", email="m@b.com"
        )
        self.client.force_login(user)
        add_to_cart(self.client, self.product)
        response = self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "Member", "email": "m@b.com", "phone": "071 555 9999"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(customer_name="Member").count(), 1)


@override_settings(**TEST_PAYFAST)
class ShippingMethodTests(TestCase):
    """Configurable shipping methods: selection, server-side pricing, history."""

    def _checkout(self, **overrides):
        payload = {
            "full_name": "Ship Buyer",
            "email": "ship@b.com",
            "phone": "071 555 7777",
        }
        payload.update(overrides)
        return self.client.post(reverse("orders:checkout_submit"), payload)

    def test_standard_delivery_fee_included_in_total_and_payment(self):
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout(shipping_method="standard", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        payment = Payment.objects.get(order=order)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        self.assertEqual(order.shipping_method_label, "Standard Delivery")
        self.assertEqual(order.delivery_fee, Decimal("99.00"))
        self.assertEqual(order.total, product.price + Decimal("99.00"))
        self.assertEqual(payment.amount, order.total)

    def test_free_delivery_qualifies_at_threshold_and_charges_nothing(self):
        product = create_product(price=Decimal("600.00"))
        add_to_cart(self.client, product)
        self._checkout(shipping_method="free", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.shipping_method, Order.ShippingMethod.FREE)
        self.assertEqual(order.shipping_method_label, "Free Delivery")
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.total, product.price)
        self.assertEqual(Payment.objects.get(order=order).amount, order.total)

    def test_free_delivery_not_offered_below_threshold(self):
        from orders.services import shipping_methods

        product = create_product(price=Decimal("100.00"))
        methods = {m["code"] for m in shipping_methods(product.price)}
        self.assertNotIn(Order.ShippingMethod.FREE, methods)
        self.assertIn(Order.ShippingMethod.STANDARD, methods)
        self.assertIn(Order.ShippingMethod.PICKUP, methods)

    def test_free_delivery_offered_at_threshold(self):
        from orders.services import shipping_methods

        methods = {m["code"] for m in shipping_methods(Decimal("500.00"))}
        self.assertIn(Order.ShippingMethod.FREE, methods)

    def test_local_pickup_free_and_no_delivery_estimate(self):
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout(shipping_method="pickup")
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.delivery_option, Order.DeliveryChoice.COLLECTION)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.PICKUP)
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.delivery_address, "")
        self.assertIsNone(order.delivery_estimate_from)
        self.assertIsNone(order.delivery_estimate_to)
        self.assertEqual(order.total, product.price)

    def test_delivery_address_required_for_standard(self):
        product = create_product()
        add_to_cart(self.client, product)
        response = self._checkout(shipping_method="standard")
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("orders:checkout"))
        self.assertEqual(Order.objects.count(), 0)

    def test_invalid_or_missing_method_falls_back_to_pickup(self):
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout(shipping_method="not-a-method")
        order = Order.objects.filter(customer_name="Ship Buyer").first()
        self.assertIsNotNone(order)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.PICKUP)
        self.assertEqual(order.delivery_fee, Decimal("0.00"))

    def test_disabled_standard_not_offered(self):
        from orders.models import ShippingSettings
        from orders.services import shipping_methods

        settings = ShippingSettings.load()
        settings.standard_enabled = False
        settings.save()
        product = create_product()
        methods = {m["code"] for m in shipping_methods(product.price)}
        self.assertNotIn(Order.ShippingMethod.STANDARD, methods)

    def test_disabled_standard_falls_back_to_pickup(self):
        from orders.models import ShippingSettings

        settings = ShippingSettings.load()
        settings.standard_enabled = False
        settings.save()
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout(shipping_method="standard", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.shipping_method, Order.ShippingMethod.PICKUP)
        self.assertEqual(order.delivery_fee, Decimal("0.00"))

    def test_historical_orders_keep_their_shipping_price(self):
        from orders.models import ShippingSettings

        product = create_product()
        add_to_cart(self.client, product)
        self._checkout(shipping_method="standard", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.delivery_fee, Decimal("99.00"))

        settings = ShippingSettings.load()
        settings.standard_fee = Decimal("150.00")
        settings.save()

        order.recalc_totals()
        order.refresh_from_db()
        self.assertEqual(order.delivery_fee, Decimal("99.00"))
        self.assertEqual(order.total, product.price + Decimal("99.00"))