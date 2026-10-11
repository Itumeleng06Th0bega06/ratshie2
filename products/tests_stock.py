"""Stock tracking tests: automatic badges, quantity limits and oversell guards.

These cover the customer-facing surfaces (product card, product page, cart and
checkout) plus the automatic admin badge. The order/payment side of stock
deduction lives in ``orders/tests_stock.py``.

Runs against Django's throwaway test database, so ``db.sqlite3`` is untouched.
"""
from decimal import Decimal
import itertools

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Product
from .services import cart_stock_errors, clamp_quantity

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


class StockStatusTests(TestCase):
    """The status comes from the real quantity and nowhere else."""

    def test_ten_is_in_stock_and_has_no_badge(self):
        product = make_product(stock=10)
        self.assertEqual(product.stock_status, "in")
        self.assertEqual(product.stock_warning_label, "")
        self.assertEqual(product.stock_badge_class, "")
        self.assertTrue(product.in_stock)

    def test_nine_is_limited_stock(self):
        product = make_product(stock=9)
        self.assertEqual(product.stock_status, "limited")
        self.assertEqual(product.stock_warning_label, "Limited Stock")
        self.assertEqual(product.stock_badge_class, "badge--limited")
        self.assertTrue(product.in_stock)

    def test_one_is_limited_stock(self):
        product = make_product(stock=1)
        self.assertEqual(product.stock_status, "limited")
        self.assertEqual(product.stock_warning_label, "Limited Stock")
        self.assertTrue(product.in_stock)

    def test_zero_is_out_of_stock_and_blocks_purchase(self):
        product = make_product(stock=0)
        self.assertEqual(product.stock_status, "out")
        self.assertEqual(product.stock_warning_label, "Out of Stock")
        self.assertEqual(product.stock_badge_class, "badge--out")
        self.assertFalse(product.in_stock)

    def test_restock_from_nine_to_ten_removes_the_badge(self):
        product = make_product(stock=9)
        self.assertEqual(product.stock_warning_label, "Limited Stock")
        product.stock = 10
        product.save()
        product.refresh_from_db()
        self.assertEqual(product.stock_warning_label, "")

    def test_restock_from_zero_to_one_removes_out_of_stock(self):
        product = make_product(stock=0)
        self.assertEqual(product.stock_warning_label, "Out of Stock")
        product.stock = 1
        product.save()
        product.refresh_from_db()
        self.assertEqual(product.stock_warning_label, "Limited Stock")

    def test_zero_stock_is_unbuyable_even_if_availability_says_in_stock(self):
        # A stale hand-picked availability must never make sold-out stock buyable.
        product = make_product(stock=0, availability="in_stock")
        self.assertFalse(product.in_stock)

    def test_stored_availability_is_derived_from_stock(self):
        self.assertEqual(make_product(stock=0).availability, "out_of_stock")
        self.assertEqual(make_product(stock=5).availability, "limited")
        self.assertEqual(make_product(stock=25).availability, "in_stock")


class StockBadgeSurfaceTests(TestCase):
    """The same calculation drives the card and the product page."""

    def test_card_shows_out_of_stock_badge(self):
        make_product(name="Soldout Widget", stock=0)
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertIn("Out of Stock", html)
        self.assertIn("badge--out", html)

    def test_card_shows_limited_stock_badge(self):
        make_product(name="Limited Widget", stock=4)
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertIn("Limited Stock", html)
        self.assertIn("badge--limited", html)

    def test_card_shows_no_stock_badge_at_ten(self):
        make_product(name="Plenty Widget", stock=10)
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertNotIn("Limited Stock", html)
        self.assertNotIn("Out of Stock", html)

    def test_card_and_detail_agree(self):
        product = make_product(name="Consistent Widget", stock=3)
        card_html = self.client.get(reverse("products:shop")).content.decode()
        detail_html = self.client.get(product.get_absolute_url()).content.decode()
        self.assertIn("Limited Stock", card_html)
        self.assertIn("Limited Stock", detail_html)

    def test_detail_out_of_stock_hides_add_to_cart(self):
        product = make_product(name="Soldout Widget", stock=0)
        html = self.client.get(product.get_absolute_url()).content.decode()
        self.assertIn("Out of Stock", html)
        self.assertIn("Request This Item", html)
        self.assertNotIn("Add to Cart", html)

    def test_detail_quantity_input_is_capped_at_stock(self):
        product = make_product(name="Limited Widget", stock=3)
        html = self.client.get(product.get_absolute_url()).content.decode()
        self.assertIn('max="3"', html)


class CartStockLimitTests(TestCase):
    """The cart can never hold more units than are actually available."""

    def _cart(self):
        return self.client.session.get("cart") or {}

    def test_cannot_add_more_than_stock(self):
        product = make_product(stock=2)
        url = reverse("products:cart_add", kwargs={"slug": product.slug})
        self.client.post(url, {"quantity": 5})
        self.assertEqual(self._cart()[str(product.pk)]["qty"], 2)

    def test_repeated_adds_stop_at_stock(self):
        product = make_product(stock=3)
        url = reverse("products:cart_add", kwargs={"slug": product.slug})
        for _ in range(10):
            self.client.post(url, {"quantity": 1})
        self.assertEqual(self._cart()[str(product.pk)]["qty"], 3)

    def test_out_of_stock_product_is_not_added(self):
        product = make_product(stock=0)
        url = reverse("products:cart_add", kwargs={"slug": product.slug})
        self.client.post(url, {"quantity": 1})
        self.assertNotIn(str(product.pk), self._cart())

    def test_buy_now_is_capped_at_stock(self):
        product = make_product(stock=2)
        url = reverse("products:buy_now", kwargs={"slug": product.slug})
        self.client.post(url, {"quantity": 9})
        self.assertEqual(self._cart()[str(product.pk)]["qty"], 2)

    def test_cart_set_qty_is_capped_at_stock(self):
        product = make_product(stock=2)
        add = reverse("orders:cart_add", kwargs={"slug": product.slug})
        self.client.post(add, {"quantity": 1})
        set_qty = reverse("orders:cart_set_qty", kwargs={"pk": product.pk})
        self.client.post(set_qty, {"qty": 99})
        self.assertEqual(self._cart()[str(product.pk)]["qty"], 2)


class CartStockHelperTests(TestCase):
    def test_clamp_quantity(self):
        product = make_product(stock=4)
        self.assertEqual(clamp_quantity(product, 0), 0)
        self.assertEqual(clamp_quantity(product, 3), 3)
        self.assertEqual(clamp_quantity(product, 99), 4)
        self.assertEqual(clamp_quantity(make_product(stock=0), 5), 0)

    def test_cart_stock_errors_flags_over_buy(self):
        product = make_product(stock=2)
        errors = cart_stock_errors([{"product": product, "qty": 3}])
        self.assertEqual(len(errors), 1)
        self.assertIn("Only 2", errors[0])

    def test_cart_stock_errors_accepts_within_stock(self):
        product = make_product(stock=2)
        self.assertEqual(cart_stock_errors([{"product": product, "qty": 2}]), [])

    def test_cart_stock_errors_flags_out_of_stock(self):
        product = make_product(stock=0)
        errors = cart_stock_errors([{"product": product, "qty": 1}])
        self.assertEqual(len(errors), 1)
        self.assertIn("out of stock", errors[0])


@override_settings(**{
    "PAYFAST_MERCHANT_ID": "10054184",
    "PAYFAST_MERCHANT_KEY": "qj6m1q1x51moy",
    "PAYFAST_PASSPHRASE": "testpassphrase",
    "PAYFAST_SANDBOX": True,
    "PAYFAST_RETURN_URL_PREFIX": "http://127.0.0.1:8000",
})
class CheckoutStockValidationTests(TestCase):
    """Order submission re-checks stock server-side (cart qty is not proof)."""

    def _place_order(self):
        return self.client.post(
            reverse("orders:checkout_submit"),
            {
                "full_name": "Stock Buyer",
                "email": "buyer@example.com",
                "phone": "071 555 1234",
                "delivery_address": "1 Main St",
                "accept_terms": "1",
            },
        )

    def test_order_rejected_when_cart_exceeds_stock(self):
        from orders.models import Order

        product = make_product(stock=5)
        # Put more in the cart than stock, then shrink the real stock behind the
        # customer's back (another buyer got there first).
        self.client.post(
            reverse("products:cart_add", kwargs={"slug": product.slug}),
            {"quantity": 4},
        )
        Product.objects.filter(pk=product.pk).update(stock=1)

        response = self._place_order()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.exists())

    def test_order_accepted_when_within_stock(self):
        from orders.models import Order

        product = make_product(stock=5)
        self.client.post(
            reverse("products:cart_add", kwargs={"slug": product.slug}),
            {"quantity": 2},
        )
        self._place_order()
        order = Order.objects.get()
        self.assertEqual(order.items.get().quantity, 2)


class ProductStockAdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            "stockadmin", "a@b.com", "pw12345!"
        )
        self.client.force_login(self.admin)

    def test_changelist_shows_stock_column_and_filter(self):
        make_product(name="Listed", stock=3)
        response = self.client.get(reverse("admin:products_product_changelist"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="field-stock"', html)
        self.assertIn('class="field-stock_badge"', html)
        # The automatic stock filter is offered.
        self.assertIn("stock status", html)

    def test_stock_filter_isolates_out_of_stock(self):
        soldout = make_product(name="Sold Out One", stock=0)
        avail = make_product(name="Available One", stock=20)
        response = self.client.get(
            reverse("admin:products_product_changelist"), {"stock_status": "out"}
        )
        self.assertContains(response, soldout.name)
        self.assertNotContains(response, avail.name)

    def test_availability_is_read_only_on_change_form(self):
        product = make_product(name="Readonly A", stock=4)
        response = self.client.get(
            reverse("admin:products_product_change", args=[product.pk])
        )
        html = response.content.decode()
        # The quantity is editable...
        self.assertIn('name="stock"', html)
        # ...but the badge/availability is not user-editable.
        self.assertNotIn('name="availability"', html)
