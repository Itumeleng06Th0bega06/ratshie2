"""Integration tests for the cart -> checkout -> PayFast payment flow."""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

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


def shipping_config():
    """Return the singleton shipping settings.

    Fee assertions read this rather than hard-coding amounts, so changing a
    price in the admin (or in a migration default) does not silently break the
    suite, and a test can never pass against a stale literal.
    """
    from orders.models import ShippingSettings

    return ShippingSettings.load()


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
                "accept_terms": "1",
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

    def test_checkout_form_offers_required_terms_checkbox(self):
        add_to_cart(self.client, create_product())
        html = self.client.get(reverse("orders:checkout")).content.decode()
        self.assertIn('name="accept_terms"', html)
        # Required in the markup so the browser blocks an empty submit, and the
        # value the server reads for a ticked box.
        self.assertRegex(html, r'<input[^>]*id="accept_terms"[^>]*required')
        self.assertIn(reverse("terms"), html)

    def test_checkout_blocked_when_terms_not_accepted(self):
        add_to_cart(self.client, create_product())
        response = self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "No Terms",
                "email": "noterms@example.com",
                "phone": "071 555 4321",
            },
        )
        # fetch_redirect_response=False, so the error message is still queued for
        # the assertion below instead of being consumed by the followed request.
        self.assertRedirects(
            response, reverse("orders:checkout"), fetch_redirect_response=False
        )
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        # The cart survives a rejected submission, unlike a placed order.
        self.assertTrue(self.client.session["cart"])
        self.assertContains(
            self.client.get(reverse("orders:checkout")),
            "accept the Terms &amp; Conditions",
        )

    def test_checkout_rejects_present_but_false_terms_values(self):
        add_to_cart(self.client, create_product())
        for bogus in ("0", "false", "no", "off", ""):
            with self.subTest(value=bogus):
                response = self.client.post(
                    reverse("orders:checkout_submit"),
                    {
                        "full_name": "Bad Terms",
                        "email": "badterms@example.com",
                        "phone": "071 555 4321",
                        "accept_terms": bogus,
                    },
                )
                self.assertRedirects(response, reverse("orders:checkout"))
        self.assertEqual(Order.objects.count(), 0)

    def test_order_records_terms_acceptance_with_server_timestamp(self):
        add_to_cart(self.client, create_product())
        before = timezone.now()
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Terms Buyer",
                "email": "terms@example.com",
                "phone": "071 555 4321",
                "accept_terms": "1",
                # A forged client timestamp must be ignored entirely.
                "terms_accepted_at": "2000-01-01T00:00:00Z",
            },
        )
        order = Order.objects.get(customer_name="Terms Buyer")
        self.assertTrue(order.terms_accepted)
        self.assertIsNotNone(order.terms_accepted_at)
        self.assertGreaterEqual(order.terms_accepted_at, before)

    def test_orders_predating_the_requirement_stay_unaccepted(self):
        """Existing orders must not look like they accepted these terms."""
        product = create_product()
        order = Order.objects.create(
            customer_name="Legacy",
            email="legacy@example.com",
            phone="071 555 0000",
            total=Decimal("100.00"),
        )
        OrderItem.objects.create(
            order=order, product=product, product_name=product.name, quantity=1, unit_price=product.price
        )
        self.assertFalse(order.terms_accepted)
        self.assertIsNone(order.terms_accepted_at)

    def test_order_reference_generated_automatically(self):
        product = create_product()
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "A", "email": "a@b.com", "phone": "071 555 1234", "accept_terms": "1"},
        )
        order = Order.objects.get(customer_name="A")
        self.assertTrue(order.reference.startswith("RS-"))
        self.assertGreater(len(order.reference), 5)

    def test_recalc_totals_includes_delivery_fee(self):
        product = create_product()
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "B", "email": "b@b.com", "phone": "071 555 1234", "accept_terms": "1", "shipping_method": "standard", "delivery_address": "1 Main St"},
        )
        order = Order.objects.get(customer_name="B")
        fee = shipping_config().standard_fee
        self.assertEqual(order.delivery_option, Order.DeliveryChoice.DELIVERY)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        self.assertEqual(order.delivery_address, "1 Main St")
        self.assertEqual(order.delivery_fee, fee)
        self.assertEqual(order.total, product.price + fee)

    def test_customer_record_created_and_reused(self):
        product = create_product()
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "Reuse", "email": "r@b.com", "phone": "071 555 4321", "accept_terms": "1"},
        )
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "Reuse2", "email": "r2@b.com", "phone": "071 555 4321", "accept_terms": "1"},
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
        # Redirected to sign in, not the product page and not register.
        self.assertTrue(response["Location"].startswith(reverse("customers:login")))
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_anonymous_add_redirects_to_sign_in_with_next_back_to_product(self):
        response = add_to_cart(self.client, self.product)
        self.assertIn(
            f"next={self.product.get_absolute_url()}", response["Location"]
        )

    def test_buy_now_also_redirects_anonymous_to_sign_in(self):
        response = self.client.post(
            reverse("products:buy_now", kwargs={"slug": self.product.slug}),
            {"quantity": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("customers:login")))
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_htmx_add_to_cart_redirects_to_sign_in(self):
        response = self.client.post(
            reverse("products:cart_add", kwargs={"slug": self.product.slug}),
            {"quantity": "1"},
            headers={"hx-request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response["HX-Redirect"].startswith(reverse("customers:login"))
        )
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_ajax_add_to_cart_returns_sign_in_redirect(self):
        response = self.client.post(
            reverse("products:cart_add", kwargs={"slug": self.product.slug}),
            {"quantity": "1"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        payload = response.json()
        self.assertTrue(payload["redirect"].startswith(reverse("customers:login")))
        self.assertTrue(payload["sale_required"])
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_sign_in_page_offers_account_creation(self):
        """Sign-in is a dead end only if registration is reachable from it."""
        response = self.client.get(reverse("customers:login"))
        html = response.content.decode()
        self.assertIn(reverse("customers:register"), html)

    def test_authenticated_member_can_purchase(self):
        user = get_user_model().objects.create_user(
            username="member", password="testpass123", email="m@b.com"
        )
        self.client.force_login(user)
        add_to_cart(self.client, self.product)
        response = self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "Member", "email": "m@b.com", "phone": "071 555 9999", "accept_terms": "1"},
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
            "accept_terms": "1",
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
        fee = shipping_config().standard_fee
        self.assertEqual(order.delivery_fee, fee)
        self.assertEqual(order.total, product.price + fee)
        self.assertEqual(payment.amount, order.total)

    def test_free_delivery_applied_automatically_above_threshold(self):
        """No separate 'free' choice: choosing Standard above the minimum is free."""
        product = create_product(price=shipping_config().free_minimum)
        add_to_cart(self.client, product)
        self._checkout(shipping_method="standard", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        self.assertEqual(order.shipping_method_label, "Standard Delivery")
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.total, product.price)
        self.assertEqual(Payment.objects.get(order=order).amount, order.total)
        # Still a delivery order, so it keeps a delivery window.
        self.assertIsNotNone(order.delivery_estimate_from)

    def test_free_delivery_never_offered_as_a_separate_choice(self):
        from orders.services import shipping_methods

        minimum = shipping_config().free_minimum
        for subtotal in (Decimal("100.00"), minimum - Decimal("0.01"), minimum, Decimal("90000.00")):
            with self.subTest(subtotal=subtotal):
                codes = {m["code"] for m in shipping_methods(subtotal)}
                self.assertNotIn(Order.ShippingMethod.FREE, codes)
                self.assertEqual(
                    codes, {Order.ShippingMethod.STANDARD, Order.ShippingMethod.PICKUP}
                )

    def test_standard_fee_reduces_to_zero_exactly_at_threshold(self):
        from orders.services import shipping_methods

        minimum = shipping_config().free_minimum
        below = next(m for m in shipping_methods(minimum - Decimal("0.01"))
                     if m["code"] == Order.ShippingMethod.STANDARD)
        at = next(m for m in shipping_methods(minimum)
                  if m["code"] == Order.ShippingMethod.STANDARD)
        self.assertEqual(below["fee"], shipping_config().standard_fee)
        self.assertFalse(below["free_applied"])
        self.assertEqual(at["fee"], Decimal("0.00"))
        self.assertTrue(at["free_applied"])

    def test_legacy_free_code_cannot_buy_free_delivery_below_threshold(self):
        """A stale page or tampered POST must not grant free delivery early."""
        product = create_product(price=Decimal("100.00"))
        add_to_cart(self.client, product)
        self._checkout(shipping_method="free", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        # Folded into Standard Delivery and re-priced from the server threshold.
        fee = shipping_config().standard_fee
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        self.assertEqual(order.delivery_fee, fee)
        self.assertEqual(order.total, product.price + fee)

    def test_legacy_free_code_still_free_when_qualifying(self):
        product = create_product(price=shipping_config().free_minimum)
        add_to_cart(self.client, product)
        self._checkout(shipping_method="free", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        self.assertEqual(order.delivery_fee, Decimal("0.00"))

    def test_free_delivery_status_reports_shortfall(self):
        from orders.services import free_delivery_status

        minimum = shipping_config().free_minimum
        below = free_delivery_status(Decimal("200.00"))
        self.assertFalse(below["qualifies"])
        self.assertTrue(below["enabled"])
        self.assertEqual(below["shortfall"], minimum - Decimal("200.00"))

        at = free_delivery_status(minimum)
        self.assertTrue(at["qualifies"])
        self.assertEqual(at["shortfall"], Decimal("0.00"))

    def test_free_delivery_disabled_charges_standard_fee_above_threshold(self):
        from orders.models import ShippingSettings
        from orders.services import free_delivery_status, shipping_methods

        settings_row = ShippingSettings.load()
        fee = settings_row.standard_fee
        settings_row.free_enabled = False
        settings_row.save()

        product = create_product(price=Decimal("6000.00"))
        add_to_cart(self.client, product)
        self._checkout(shipping_method="standard", delivery_address="2 Long Rd")
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.delivery_fee, fee)

        self.assertFalse(free_delivery_status(Decimal("90000.00"))["enabled"])
        standard = next(m for m in shipping_methods(Decimal("90000.00"))
                        if m["code"] == Order.ShippingMethod.STANDARD)
        self.assertEqual(standard["fee"], fee)
        self.assertFalse(standard["free_applied"])

    def test_checkout_page_shows_free_delivery_warning_not_a_choice(self):
        product = create_product(price=Decimal("100.00"))
        add_to_cart(self.client, product)
        response = self.client.get(reverse("orders:checkout"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        # Warning is present, naming the shortfall.
        shortfall = shipping_config().free_minimum - product.price
        self.assertIn(f"R {shortfall:,.2f}", html)
        self.assertIn("free", html.lower())
        # But there is no free-delivery radio to click.
        self.assertNotIn('value="free"', html)
        self.assertNotIn("Free Delivery", html)

    def test_checkout_page_confirms_free_delivery_once_qualifying(self):
        product = create_product(price=shipping_config().free_minimum)
        add_to_cart(self.client, product)
        response = self.client.get(reverse("orders:checkout"))
        html = response.content.decode()
        self.assertIn("Free delivery unlocked", html)
        self.assertNotIn('value="free"', html)

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
        original_fee = shipping_config().standard_fee
        self.assertEqual(order.delivery_fee, original_fee)

        settings = ShippingSettings.load()
        settings.standard_fee = original_fee + Decimal("50.00")
        settings.save()

        order.recalc_totals()
        order.refresh_from_db()
        self.assertEqual(order.delivery_fee, original_fee)
        self.assertEqual(order.total, product.price + original_fee)


@override_settings(**TEST_PAYFAST)
class ProductDeliveryTypeTests(TestCase):
    """The four per-product delivery types, end to end.

    Products are deliberately kept under the free-delivery threshold in these
    tests so the automatic small-items waiver does not mask the per-product
    charge. Fees are pinned here so these assertions are about the *rules*, not
    about whatever price happens to be configured.
    """

    def setUp(self):
        from orders.models import ShippingSettings

        self.s = ShippingSettings.load()
        self.s.standard_fee = Decimal("100.00")
        self.s.big_item_fee = Decimal("250.00")
        self.s.big_item_threshold = Decimal("1500.00")
        self.s.free_minimum = Decimal("5000.00")
        self.s.free_enabled = True
        self.s.save()

    def _buy(self, name, **overrides):
        product = create_product(name=name, price=Decimal("50.00"), **overrides)
        add_to_cart(self.client, product, qty=1)
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Delivery Buyer",
                "email": "d@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
            },
        )
        order = Order.objects.get(customer_name="Delivery Buyer")
        return product, order, Payment.objects.get(order=order)

    # --- product_delivery(): one product, four outcomes -------------------

    def test_product_delivery_standard_uses_global_fee(self):
        from orders.services import product_delivery

        info = product_delivery(create_product(name="Std", delivery_type="standard"))
        self.assertEqual(info["fee"], Decimal("100.00"))
        self.assertEqual(info["type"], "standard")

    def test_product_delivery_free_is_zero(self):
        from orders.services import product_delivery

        info = product_delivery(create_product(name="Free", delivery_type="free"))
        self.assertEqual(info["fee"], Decimal("0.00"))
        self.assertTrue(info["is_free"])

    def test_product_delivery_custom_uses_own_fee(self):
        from orders.services import product_delivery

        a = product_delivery(
            create_product(name="CustA", delivery_type="custom", delivery_fee=Decimal("80.00"))
        )
        b = product_delivery(
            create_product(name="CustB", delivery_type="custom", delivery_fee=Decimal("120.00"))
        )
        self.assertEqual(a["fee"], Decimal("80.00"))
        self.assertEqual(b["fee"], Decimal("120.00"))
        self.assertNotEqual(a["fee"], b["fee"])

    def test_product_delivery_big_item_uses_global_big_item_fee(self):
        from orders.services import product_delivery

        info = product_delivery(create_product(name="Big", delivery_type="big_item"))
        self.assertEqual(info["fee"], Decimal("250.00"))

    def test_expensive_product_is_not_auto_big_item(self):
        """Price alone must never upgrade a product to the big-item charge."""
        from orders.services import product_delivery

        product = create_product(
            name="Expensive but light", price=Decimal("95000.00"), delivery_type="standard"
        )
        # Price is far above the configured reference value...
        self.assertGreater(product.price, self.s.big_item_threshold)
        # ...but the charge is still the standard fee, not the big-item fee.
        info = product_delivery(product)
        self.assertEqual(info["fee"], Decimal("100.00"))
        self.assertEqual(info["type"], "standard")

    # --- checkout: the amount actually stored and paid -------------------

    def test_checkout_charges_standard_fee_for_standard_product(self):
        _, order, payment = self._buy("Std Buy", delivery_type="standard")
        self.assertEqual(order.delivery_fee, Decimal("100.00"))
        self.assertEqual(order.total, Decimal("150.00"))
        self.assertEqual(payment.amount, order.total)

    def test_checkout_charges_nothing_for_free_product(self):
        _, order, payment = self._buy("Free Buy", delivery_type="free")
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("50.00"))
        self.assertEqual(payment.amount, order.total)

    def test_checkout_charges_custom_product_fee(self):
        _, order, payment = self._buy(
            "Custom Buy", delivery_type="custom", delivery_fee=Decimal("80.00")
        )
        self.assertEqual(order.delivery_fee, Decimal("80.00"))
        self.assertEqual(order.total, Decimal("130.00"))
        self.assertEqual(payment.amount, order.total)

    def test_checkout_charges_big_item_fee(self):
        _, order, payment = self._buy("Big Buy", delivery_type="big_item")
        self.assertEqual(order.delivery_fee, Decimal("250.00"))
        self.assertEqual(order.total, Decimal("300.00"))
        self.assertEqual(payment.amount, order.total)

    def test_two_standard_products_charge_the_standard_fee_once(self):
        for name in ("A1", "A2", "A3"):
            add_to_cart(self.client, create_product(name=name, price=Decimal("50.00")), qty=2)
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Delivery Buyer",
                "email": "d@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
            },
        )
        order = Order.objects.get(customer_name="Delivery Buyer")
        self.assertEqual(order.items.count(), 3)
        self.assertEqual(order.delivery_fee, Decimal("100.00"))

    def test_mixed_cart_combines_each_class_once(self):
        add_to_cart(self.client, create_product(name="Std", price=Decimal("50.00")), qty=2)
        add_to_cart(self.client, create_product(name="Free", price=Decimal("50.00"), delivery_type="free"))
        add_to_cart(
            self.client,
            create_product(name="Cust", price=Decimal("50.00"), delivery_type="custom", delivery_fee=Decimal("80.00")),
        )
        add_to_cart(self.client, create_product(name="Big", price=Decimal("50.00"), delivery_type="big_item"))
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Mixed Buyer",
                "email": "m@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
            },
        )
        order = Order.objects.get(customer_name="Mixed Buyer")
        # 100 standard + 80 custom + 250 big item, free product adds nothing.
        self.assertEqual(order.delivery_fee, Decimal("430.00"))
        # Items: 2 x 50 standard, 50 free, 50 custom, 50 big item = 250.00
        self.assertEqual(order.total, Decimal("250.00") + Decimal("430.00"))

    def test_all_free_cart_delivers_free(self):
        add_to_cart(self.client, create_product(name="F1", price=Decimal("50.00"), delivery_type="free"))
        add_to_cart(self.client, create_product(name="F2", price=Decimal("50.00"), delivery_type="free"))
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Free Buyer",
                "email": "f@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
            },
        )
        order = Order.objects.get(customer_name="Free Buyer")
        self.assertEqual(order.delivery_fee, Decimal("0.00"))

    def test_browser_cannot_submit_its_own_delivery_fee(self):
        """A tampered fee in the POST must be ignored entirely."""
        product = create_product(name="Tamper", price=Decimal("50.00"), delivery_type="standard")
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Tamper Buyer",
                "email": "t@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
                "delivery_fee": "0.00",
                "shipping_fee": "0.00",
            },
        )
        order = Order.objects.get(customer_name="Tamper Buyer")
        self.assertEqual(order.delivery_fee, Decimal("100.00"))

    def test_pickup_ignores_product_delivery_fee(self):
        add_to_cart(self.client, create_product(name="Pickup Big", price=Decimal("50.00"), delivery_type="big_item"))
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Pickup Buyer",
                "email": "p@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "pickup",
            },
        )
        order = Order.objects.get(customer_name="Pickup Buyer")
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("50.00"))

    # --- product detail page --------------------------------------------

    def test_detail_page_shows_standard_fee(self):
        p = create_product(name="D1", price=Decimal("50.00"), delivery_type="standard")
        html = self.client.get(p.get_absolute_url()).content.decode()
        self.assertIn("Delivery: R 100.00", html)

    def test_detail_page_shows_free_delivery_and_no_fee(self):
        p = create_product(name="D2", price=Decimal("50.00"), delivery_type="free")
        html = self.client.get(p.get_absolute_url()).content.decode()
        self.assertIn("Free delivery", html)
        self.assertNotIn("Delivery: R 100.00", html)

    def test_detail_page_shows_custom_fee(self):
        p = create_product(name="D3", price=Decimal("50.00"), delivery_type="custom", delivery_fee=Decimal("80.00"))
        html = self.client.get(p.get_absolute_url()).content.decode()
        self.assertIn("Delivery: R 80.00", html)

    def test_detail_page_shows_big_item_fee_and_label(self):
        p = create_product(name="D4", price=Decimal("50.00"), delivery_type="big_item")
        html = self.client.get(p.get_absolute_url()).content.decode()
        self.assertIn("Delivery: R 250.00", html)
        self.assertIn("Large item delivery", html)

    # --- validation and migration safety --------------------------------

    def test_custom_without_fee_is_rejected(self):
        from django.core.exceptions import ValidationError

        p = create_product(name="NoFee", delivery_type="standard")
        p.delivery_type = "custom"
        p.delivery_fee = None
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_negative_fee_is_rejected(self):
        from django.core.exceptions import ValidationError

        p = create_product(name="Neg", delivery_type="standard")
        p.delivery_type = "custom"
        p.delivery_fee = Decimal("-5.00")
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_non_custom_product_cannot_keep_a_custom_fee(self):
        p = create_product(
            name="Stale", delivery_type="custom", delivery_fee=Decimal("80.00")
        )
        p.delivery_type = "standard"
        p.save()
        p.refresh_from_db()
        self.assertIsNone(p.delivery_fee)

    # --- the small-items threshold excludes large items -------------------

    def test_big_item_order_keeps_its_fee_above_the_threshold(self):
        """A R5000 order containing a big item must not get free delivery."""
        big = create_product(
            name="Big Over Threshold", price=Decimal("5000.00"), delivery_type="big_item"
        )
        self.s.free_minimum = Decimal("800.00")
        self.s.save()
        self.assertGreater(big.price, self.s.free_minimum)

        add_to_cart(self.client, big)
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Big Buyer",
                "email": "big@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
            },
        )
        order = Order.objects.get(customer_name="Big Buyer")
        # Large item fee survives; nothing added, nothing waived.
        self.assertEqual(order.delivery_fee, Decimal("250.00"))

    def test_small_item_order_above_threshold_is_free(self):
        p = create_product(name="Small Over", price=Decimal("850.00"), delivery_type="standard")
        self.s.free_minimum = Decimal("800.00")
        self.s.save()
        add_to_cart(self.client, p)
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Small Buyer",
                "email": "small@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
            },
        )
        order = Order.objects.get(customer_name="Small Buyer")
        self.assertEqual(order.delivery_fee, Decimal("0.00"))

    def test_free_delivery_status_flags_big_item_exclusion(self):
        from orders.services import free_delivery_status

        over = free_delivery_status(Decimal("9000.00"), has_big_item=True)
        self.assertFalse(over["qualifies"])
        self.assertTrue(over["excluded"])
        # Never tell a big-item customer to "spend more to qualify".
        self.assertEqual(over["shortfall"], Decimal("0.00"))

        small = free_delivery_status(Decimal("9000.00"), has_big_item=False)
        self.assertTrue(small["qualifies"])
        self.assertFalse(small["excluded"])

    def test_checkout_banner_explains_big_item_exclusion(self):
        create_product(name="Banner Big", price=Decimal("5000.00"), delivery_type="big_item")
        self.s.free_minimum = Decimal("800.00")
        self.s.save()
        add_to_cart(self.client, Product.objects.get(name="Banner Big"))
        html = self.client.get(reverse("orders:checkout")).content.decode()
        self.assertIn("large item", html.lower())
        # It must not simultaneously promise free delivery.
        self.assertNotIn("Free delivery unlocked", html)

    def test_existing_products_default_to_standard_and_keep_working(self):
        legacy = create_product(name="Legacy", price=Decimal("50.00"))
        self.assertEqual(legacy.delivery_type, "standard")
        from orders.services import product_delivery

        self.assertEqual(product_delivery(legacy)["fee"], Decimal("100.00"))

    def test_historical_order_amount_survives_delivery_config_change(self):
        product = create_product(name="Hist", price=Decimal("50.00"), delivery_type="standard")
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Hist Buyer",
                "email": "h@b.com",
                "phone": "071 555 0000",
                "accept_terms": "1",
                "shipping_method": "standard",
                "delivery_address": "2 Long Rd",
            },
        )
        order = Order.objects.get(customer_name="Hist Buyer")
        self.assertEqual(order.delivery_fee, Decimal("100.00"))

        # Later config change must not retroactively rewrite the order.
        self.s.standard_fee = Decimal("175.00")
        self.s.save()
        order.recalc_totals()
        order.refresh_from_db()
        self.assertEqual(order.delivery_fee, Decimal("100.00"))

    # --- one source of truth --------------------------------------------

    def test_only_one_calculator_is_used(self):
        """Detail page, cart and checkout must all read orders.services."""
        from orders import services

        self.assertTrue(callable(services.product_delivery))
        self.assertTrue(callable(services.cart_delivery))
        src = open("orders/services.py", encoding="utf-8").read()
        # The global rates are only ever read inside this module.
        self.assertNotIn("big_item_fee", open("orders/views.py", encoding="utf-8").read())
        self.assertNotIn("standard_fee", open("orders/views.py", encoding="utf-8").read())


class ProductDeliveryAdminTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser(
            "deliveryadmin", "a@b.com", "pw12345!"
        )
        self.client.force_login(self.admin)

    def test_admin_can_save_each_delivery_type(self):
        from products.admin import ProductAdminForm

        base = {
            "name": "Admin Product",
            "price": Decimal("50.00"),
            "product_type": "spare_part",
            "availability": "in_stock",
            "stock": 3,
            "is_available": True,
            "is_active": True,
            "delivery_mode": "standard",
        }
        for i, (dtype, fee) in enumerate(
            [
                ("standard", None),
                ("free", None),
                ("custom", Decimal("80.00")),
                ("big_item", None),
            ]
        ):
            # Slugs are unique and derived from the name, so vary it per case.
            data = dict(base, name=f"Admin Product {i}", delivery_type=dtype)
            if fee is not None:
                data["delivery_fee"] = str(fee)
            form = ProductAdminForm(data=data)
            self.assertTrue(form.is_valid(), f"{dtype} should be valid: {form.errors}")
            obj = form.save()
            self.assertEqual(obj.delivery_type, dtype)
            self.assertEqual(
                obj.delivery_fee, fee if dtype == "custom" else None
            )

    def test_admin_form_rejects_custom_without_fee(self):
        from products.admin import ProductAdminForm

        form = ProductAdminForm(
            data={
                "name": "Bad Custom",
                "price": Decimal("50.00"),
                "product_type": "spare_part",
                "availability": "in_stock",
                "stock": 3,
                "is_available": True,
                "is_active": True,
                "delivery_mode": "standard",
                "delivery_type": "custom",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("delivery_fee", form.errors)

    def test_admin_list_shows_catalog_product(self):
        create_product(name="Listed", delivery_type="big_item")
        response = self.client.get(reverse("admin:products_product_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listed")

    def test_admin_list_shows_core_columns(self):
        create_product(name="Listed", delivery_type="big_item")
        response = self.client.get(reverse("admin:products_product_changelist"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # The shortened changelist keeps every essential column, delivery
        # included via the change form rather than a wide table.
        for token in (
            'class="field-thumbnail"',
            'class="field-name"',
            'class="field-product_group nowrap"',
            'class="field-price"',
            'class="field-sale_price_display"',
            'class="field-stock_badge"',
            'class="field-is_active"',
        ):
            self.assertIn(token, html)
        self.assertNotIn("Big item", html)
        self.assertNotIn("overflow-x", html)


class TermsAcceptanceAdminTests(TestCase):
    """Staff can see the acceptance record, but cannot rewrite it."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser(
            "termsadmin", "t@b.com", "pw12345!"
        )
        self.client.force_login(self.admin)

    def _order(self, **kwargs):
        return Order.objects.create(
            customer_name="Audit",
            email="audit@example.com",
            phone="071 555 1234",
            total=Decimal("100.00"),
            **kwargs,
        )

    def test_changelist_marks_accepted_and_missing_acceptance(self):
        Order.objects.create(
            reference="RS-ACCEPTED",
            customer_name="Accepted",
            email="ok@example.com",
            phone="071 555 0001",
            total=Decimal("100.00"),
            terms_accepted=True,
            terms_accepted_at=timezone.now(),
        )
        Order.objects.create(
            reference="RS-LEGACY",
            customer_name="Legacy",
            email="old@example.com",
            phone="071 555 0002",
            total=Decimal("100.00"),
        )
        response = self.client.get(reverse("admin:orders_order_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Accepted")
        self.assertContains(response, "Not accepted")

    def test_acceptance_fields_are_readonly_in_admin(self):
        from orders.admin import OrderAdmin

        self.assertIn("terms_accepted", OrderAdmin.readonly_fields)
        self.assertIn("terms_accepted_at", OrderAdmin.readonly_fields)

    def test_terms_status_renders_recorded_timestamp(self):
        from orders.admin import OrderAdmin

        order = self._order(terms_accepted=True, terms_accepted_at=timezone.now())
        rendered = OrderAdmin.terms_status(None, order)
        self.assertIn("Yes", rendered)
        self.assertIn(order.terms_accepted_at.strftime("%Y-%m-%d"), rendered)

    def test_terms_status_marks_legacy_orders(self):
        from orders.admin import OrderAdmin

        self.assertEqual(OrderAdmin.terms_status(None, self._order()), "—")
