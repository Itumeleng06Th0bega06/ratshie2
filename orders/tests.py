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
                "delivery_address": "1 Main St",
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
        self.assertEqual(order.delivery_option, Order.DeliveryChoice.DELIVERY)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        fee = shipping_config().standard_fee
        self.assertEqual(order.total, product.price * 2 + fee)
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
                "delivery_address": "1 Main St",
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
            {"full_name": "A", "email": "a@b.com", "phone": "071 555 1234", "accept_terms": "1", "delivery_address": "1 Main St"},
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
            {"full_name": "Reuse", "email": "r@b.com", "phone": "071 555 4321", "accept_terms": "1", "delivery_address": "1 Main St"},
        )
        add_to_cart(self.client, product)
        self.client.post(
            reverse("orders:checkout_submit"),
            {"full_name": "Reuse2", "email": "r2@b.com", "phone": "071 555 4321", "accept_terms": "1", "delivery_address": "1 Main St"},
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
            {"full_name": "Member", "email": "m@b.com", "phone": "071 555 9999", "accept_terms": "1", "delivery_address": "1 Main St"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(customer_name="Member").count(), 1)


@override_settings(**TEST_PAYFAST)
class FlatDeliveryFeeTests(TestCase):
    """One flat, server-side delivery fee for every order.

    There is no pickup, no free-delivery threshold and no per-product fee: every
    order is delivered and charged the single admin-configured fee, which the
    browser can never override.
    """

    def _checkout(self, **overrides):
        payload = {
            "full_name": "Ship Buyer",
            "email": "ship@b.com",
            "phone": "071 555 7777",
            "accept_terms": "1",
            "delivery_address": "2 Long Rd",
        }
        payload.update(overrides)
        return self.client.post(reverse("orders:checkout_submit"), payload)

    def test_delivery_fee_helper_reads_admin_setting(self):
        from orders.services import delivery_fee

        settings = shipping_config()
        self.assertEqual(delivery_fee(), settings.standard_fee)
        settings.standard_fee = Decimal("123.45")
        settings.save()
        self.assertEqual(delivery_fee(), Decimal("123.45"))

    def test_checkout_charges_the_flat_fee(self):
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout()
        order = Order.objects.get(customer_name="Ship Buyer")
        payment = Payment.objects.get(order=order)
        fee = shipping_config().standard_fee
        self.assertEqual(order.delivery_option, Order.DeliveryChoice.DELIVERY)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)
        self.assertEqual(order.shipping_method_label, "Standard Delivery")
        self.assertEqual(order.delivery_fee, fee)
        self.assertEqual(order.total, product.price + fee)
        self.assertEqual(payment.amount, order.total)
        # A delivery order always keeps a courier-style estimate.
        self.assertIsNotNone(order.delivery_estimate_from)

    def test_delivery_address_is_required(self):
        product = create_product()
        add_to_cart(self.client, product)
        response = self._checkout(delivery_address="")
        self.assertRedirects(response, reverse("orders:checkout"))
        self.assertEqual(Order.objects.count(), 0)

    def test_browser_cannot_submit_its_own_delivery_fee(self):
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout(delivery_fee="0.00", shipping_fee="0.00", shipping_method="pickup")
        order = Order.objects.get(customer_name="Ship Buyer")
        # Pickup and any posted price are ignored: the flat fee always applies.
        self.assertEqual(order.delivery_fee, shipping_config().standard_fee)
        self.assertEqual(order.shipping_method, Order.ShippingMethod.STANDARD)

    def test_zero_fee_config_means_free_delivery(self):
        settings = shipping_config()
        settings.standard_fee = Decimal("0.00")
        settings.save()
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout()
        order = Order.objects.get(customer_name="Ship Buyer")
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.total, product.price)

    def test_historical_order_keeps_its_fee_after_config_change(self):
        product = create_product()
        add_to_cart(self.client, product)
        self._checkout()
        order = Order.objects.get(customer_name="Ship Buyer")
        original_fee = shipping_config().standard_fee

        settings = shipping_config()
        settings.standard_fee = original_fee + Decimal("50.00")
        settings.save()

        order.recalc_totals()
        order.refresh_from_db()
        self.assertEqual(order.delivery_fee, original_fee)

    def test_checkout_page_shows_the_single_fee_before_confirming(self):
        product = create_product()
        add_to_cart(self.client, product)
        response = self.client.get(reverse("orders:checkout"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        fee = shipping_config().standard_fee
        self.assertIn(f"R {fee:,.2f}", html)
        # No shipping-method radios, no free/large-item options anywhere.
        self.assertNotIn('name="shipping_method"', html)
        self.assertNotIn('value="pickup"', html)
        self.assertNotIn('value="free"', html)
        self.assertNotIn("large item", html.lower())

    def test_cart_delivery_helper(self):
        from orders.services import cart_delivery

        self.assertIsNone(cart_delivery([]))
        product = create_product()
        info = cart_delivery([{"product": product, "qty": 1}])
        self.assertEqual(info["fee"], shipping_config().standard_fee)


class RemovedDeliveryRuleTests(TestCase):
    """The old per-product / free / large-item delivery rules are gone."""

    def test_product_has_no_delivery_charge_fields(self):
        product = Product.objects.create(name="Plain Part", price=Decimal("50.00"))
        self.assertFalse(hasattr(product, "delivery_type"))
        self.assertFalse(hasattr(product, "delivery_fee"))

    def test_product_still_has_a_delivery_timeframe(self):
        product = Product.objects.create(name="Timed Part", price=Decimal("50.00"))
        self.assertEqual(product.delivery_mode, "standard")

    def test_shipping_settings_has_only_the_flat_fee(self):
        settings = shipping_config()
        for name in (
            "standard_enabled",
            "free_enabled",
            "free_minimum",
            "big_item_fee",
            "big_item_threshold",
            "pickup_enabled",
            "pickup_location",
            "pickup_instructions",
        ):
            self.assertFalse(hasattr(settings, name))

    def test_product_clean_ignores_delivery_charge(self):
        product = Product.objects.create(name="Clean Part", price=Decimal("50.00"))
        product.full_clean()


class ProductDeliveryAdminTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.admin = get_user_model().objects.create_superuser(
            "deliveryadmin", "a@b.com", "pw12345!"
        )
        self.client.force_login(self.admin)

    def test_admin_list_shows_catalog_product(self):
        create_product(name="Listed")
        response = self.client.get(reverse("admin:products_product_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listed")

    def test_admin_list_shows_core_columns(self):
        create_product(name="Listed")
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
