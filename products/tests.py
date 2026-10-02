"""Tests for the shop page and product card changes.

Covers:
- ?on_sale=1 now filters to genuinely discounted products.
- Product card renders a placeholder when no public image exists.
- Product card hides Add to Cart when the product cannot be purchased.
- ?group=<slug> filters the catalogue using the database-backed ProductGroup.
- populate_products is idempotent, preserves real prices, and stays unbranded.
- The mobile toast animation cannot push itself off-screen.

Runs against Django's throwaway test database, so db.sqlite3 is untouched.
"""
from decimal import Decimal
import json
from pathlib import Path
import tempfile

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from products.models import Product, ProductGroup, ProductImage


def make_product(name="Brake Pad Set", **kwargs):
    defaults = {
        "name": name,
        "price": Decimal("250.00"),
        "stock": 5,
        "availability": "in_stock",
        "is_available": True,
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


class OnSaleFilterTests(TestCase):
    def test_on_sale_filter_excludes_non_discounted(self):
        make_product("Discounted", price=Decimal("80.00"), original_price=Decimal("100.00"))
        make_product("Full price", price=Decimal("100.00"))
        make_product("No original", price=Decimal("50.00"), original_price=None)

        response = self.client.get(reverse("products:shop"), {"on_sale": "1"})
        names = list(response.context["products"].values_list("name", flat=True))
        self.assertEqual(names, ["Discounted"])
        self.assertTrue(response.context["on_sale_only"])

    def test_on_sale_filter_excludes_equal_price(self):
        """original_price == price is not a sale (Product.is_on_sale is False)."""
        make_product("Not really a sale", price=Decimal("100.00"), original_price=Decimal("100.00"))

        response = self.client.get(reverse("products:shop"), {"on_sale": "1"})
        self.assertEqual(list(response.context["products"]), [])

    def test_on_sale_filter_excludes_lower_original(self):
        """original_price < price is not a sale either."""
        make_product("Inverted", price=Decimal("100.00"), original_price=Decimal("50.00"))

        response = self.client.get(reverse("products:shop"), {"on_sale": "1"})
        self.assertEqual(list(response.context["products"]), [])

    def test_without_param_returns_everything(self):
        make_product("Discounted", price=Decimal("80.00"), original_price=Decimal("100.00"))
        make_product("Full price", price=Decimal("100.00"))

        response = self.client.get(reverse("products:shop"))
        self.assertEqual(response.context["products"].count(), 2)
        self.assertFalse(response.context["on_sale_only"])

    def test_on_sale_only_shows_inactive(self):
        """An inactive product must not leak in through the filter."""
        make_product(
            "Retired deal",
            price=Decimal("80.00"),
            original_price=Decimal("100.00"),
            is_active=False,
        )
        response = self.client.get(reverse("products:shop"), {"on_sale": "1"})
        self.assertEqual(list(response.context["products"]), [])


class ProductCardImagePlaceholderTests(TestCase):
    def render_card(self, product):
        response = self.client.get(reverse("products:shop"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_placeholder_shown_when_no_image(self):
        make_product("No Image Part")
        html = self.render_card(None)
        self.assertIn("product-card__placeholder", html)
        self.assertIn("No image available", html)

    def test_real_image_suppresses_placeholder(self):
        product = make_product("Has Image")
        ProductImage.objects.create(
            product=product,
            image="products/test/has-image.png",
            status=ProductImage.Status.VERIFIED,
        )
        html = self.render_card(None)
        self.assertNotIn("product-card__placeholder", html)
        self.assertIn("has-image", html)

    def test_image_row_without_file_falls_back_to_placeholder(self):
        """A ProductImage row with no file must not 500 the whole listing."""
        product = make_product("Orphan Image")
        ProductImage.objects.create(
            product=product,
            status=ProductImage.Status.VERIFIED,
        )
        html = self.render_card(None)
        self.assertIn("product-card__placeholder", html)

    def test_placeholder_picks_icon_by_product_type(self):
        make_product("Oil", product_type="lubricant")
        html = self.render_card(None)
        self.assertIn("#i-oil", html)


class ProductCardAddToCartTests(TestCase):
    def test_add_to_cart_shown_when_in_stock(self):
        make_product("Available")
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertIn("data-add-to-cart", html)

    def test_add_to_cart_hidden_when_out_of_stock(self):
        make_product("Sold out", stock=0)
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertNotIn("data-add-to-cart", html)
        self.assertIn("UNAVAILABLE", html)

    def test_member_only_anonymous_gets_sign_in_prompt(self):
        make_product("Members only", is_member_only=True)
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertNotIn("data-add-to-cart", html)
        self.assertIn("SIGN IN TO BUY", html)

    def test_member_only_signed_in_still_offers_add_to_cart(self):
        from django.contrib.auth import get_user_model

        make_product("Members only", is_member_only=True)
        self.client.force_login(get_user_model().objects.create_user("u", password="p"))
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertIn("data-add-to-cart", html)


class ProductGroupFilterTests(TestCase):
    """?group=<slug> filters from the database, never from hardcoded template names."""

    def setUp(self):
        self.filters = ProductGroup.objects.create(name="Filters", slug="filters", sort_order=10)
        self.braking = ProductGroup.objects.create(name="Braking", slug="braking", sort_order=20)
        self.oil = make_product("Oil Filter", product_group=self.filters)
        self.pad = make_product("Brake Pad", product_group=self.braking)

    def test_groups_are_exposed_to_the_template(self):
        response = self.client.get(reverse("products:shop"))
        self.assertEqual(
            {g.pk for g in response.context["product_groups"]},
            {self.filters.pk, self.braking.pk},
        )
        self.assertIsNone(response.context["selected_group"])

    def test_group_filter_narrows_results(self):
        response = self.client.get(reverse("products:shop"), {"group": "filters"})
        self.assertEqual(list(response.context["products"]), [self.oil])
        self.assertEqual(response.context["selected_group"], self.filters)

    def test_unknown_group_shows_no_products(self):
        response = self.client.get(reverse("products:shop"), {"group": "nope"})
        self.assertEqual(list(response.context["products"]), [])
        self.assertIsNone(response.context["selected_group"])

    def test_inactive_group_is_hidden(self):
        self.braking.is_active = False
        self.braking.save()
        response = self.client.get(reverse("products:shop"))
        self.assertNotIn(self.braking, list(response.context["product_groups"]))

    def test_group_names_render_as_filter_chips(self):
        html = self.client.get(reverse("products:shop")).content.decode()
        self.assertIn("?group=filters", html)
        self.assertIn("?group=braking", html)

    def test_product_without_group_still_lists(self):
        make_product("Ungrouped")
        response = self.client.get(reverse("products:shop"))
        self.assertIn("Ungrouped", [p.name for p in response.context["products"]])


class PopulateProductsCommandTests(TestCase):
    """The populate command must be idempotent and must not invent brands/images."""

    def _run(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("populate_products", *args, stdout=out)
        return out.getvalue()

    def test_populates_groups_and_products(self):
        self._run()
        self.assertEqual(ProductGroup.objects.count(), 7)
        self.assertEqual(Product.objects.count(), 62)
        self.assertEqual(Product.objects.filter(product_group__isnull=True).count(), 0)

    def test_running_twice_creates_no_duplicates(self):
        self._run()
        self._run()
        self.assertEqual(ProductGroup.objects.count(), 7)
        self.assertEqual(Product.objects.count(), 62)

    def test_no_product_claims_a_brand(self):
        self._run()
        self.assertEqual(Product.objects.exclude(brand="").count(), 0)

    def test_creates_no_images(self):
        self._run()
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_does_not_overwrite_existing_price(self):
        existing = make_product("Toyota Corolla Oil Filter", price=Decimal("999.00"))
        self._run()
        existing.refresh_from_db()
        self.assertEqual(existing.price, Decimal("999.00"))

    def test_force_prices_does_overwrite(self):
        existing = make_product("Toyota Corolla Oil Filter", price=Decimal("999.00"))
        self._run("--force-prices")
        existing.refresh_from_db()
        self.assertEqual(existing.price, Decimal("149.00"))

    def test_sale_items_use_existing_sale_logic(self):
        self._run()
        on_sale = [p for p in Product.objects.all() if p.is_on_sale]
        self.assertTrue(on_sale)
        for p in on_sale:
            self.assertGreater(p.original_price, p.price)
            self.assertIsNotNone(p.discount_percent)

    def test_fluids_use_the_lubricant_type(self):
        self._run()
        brake_fluid = Product.objects.get(name="Brake Fluid DOT 4 - 500ml")
        self.assertEqual(brake_fluid.product_type, Product.ProductType.LUBRICANT)
        self.assertEqual(
            Product.objects.filter(product_type=Product.ProductType.SPARE_PART).count(), 61
        )

    def test_matches_hand_created_product_without_a_sku(self):
        existing = make_product("Toyota Corolla Oil Filter", price=Decimal("999.00"))
        self._run()
        self.assertEqual(Product.objects.filter(name="Toyota Corolla Oil Filter").count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.price, Decimal("999.00"))
        self.assertEqual(existing.sku, "RSH-TOYOTA-COROLLA-OIL-FILTER")
        self.assertEqual(existing.product_group.slug, "filters")

    def test_every_group_has_products(self):
        self._run()
        for g in ProductGroup.objects.all():
            self.assertGreater(g.products.count(), 0, f"{g.name} has no products")

    def test_prices_are_positive_and_stock_sensible(self):
        self._run()
        for p in Product.objects.all():
            self.assertGreater(p.price, 0, p.name)
            self.assertGreaterEqual(p.stock, 0, p.name)


class ToastMobileAnimationTests(SimpleTestCase):
    """Regression: the mobile toast was pushed off-screen by its own animation.

    `.toast` is declared with the `animation` shorthand. The full-width mobile
    override must come *after* it or the shorthand wins and the horizontal
    entrance transform slides the toast past the viewport edge.
    """

    @staticmethod
    def _css():
        path = Path(settings.BASE_DIR) / "static" / "css" / "ui.css"
        return path.read_text(encoding="utf-8")

    def test_mobile_toast_overrides_animation_name(self):
        css = self._css()
        self.assertIn("toast-in-block", css)
        self.assertIn("toast-out-block", css)

    def test_mobile_override_is_declared_after_the_animation_shorthand(self):
        css = self._css()
        shorthand = css.index("animation: toast-in 0.32s")
        override = css.index("animation-name: toast-in-block")
        self.assertGreater(
            override, shorthand,
            "The mobile toast override must follow the `.toast` animation "
            "shorthand, otherwise the shorthand resets animation-name.",
        )


class AttachVerifiedProductImagesTests(TestCase):
    """Curated, reviewed images must land as VERIFIED + primary, idempotently.

    MEDIA_ROOT is redirected to a temp directory so tests never write into the
    repository's real media/ folder.
    """

    def setUp(self):
        from tempfile import TemporaryDirectory

        self._media_tmp = TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media_tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._media_tmp.cleanup)

    def _make_manifest(self, tmpdir, product, image_path=None):
        from PIL import Image

        if image_path is None:
            image_path = Path(tmpdir) / "src.jpg"
            Image.new("RGB", (900, 900), (30, 90, 160)).save(image_path)
        manifest = [
            {
                "sku": product.sku,
                "file": str(image_path),
                "alt_text": "Test part",
                "source": "Wikimedia Commons",
                "source_url": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                "licence": "CC BY-SA 4.0",
                "notes": "reviewed by eye",
            }
        ]
        mpath = Path(tmpdir) / "manifest.json"
        mpath.write_text(json.dumps(manifest), encoding="utf-8")
        return str(mpath)

    def _run(self, manifest_path):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("attach_verified_product_images", manifest_path, stdout=out)
        return out.getvalue()

    def test_attaches_verified_primary_image_with_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            product = make_product("Oil Filter", sku="RSH-TEST-OIL-FILTER")
            self._run(self._make_manifest(tmp, product))

            image = ProductImage.objects.get(product=product)
            self.assertEqual(image.status, ProductImage.Status.VERIFIED)
            self.assertTrue(image.is_primary)
            self.assertEqual(image.sort_order, 0)
            self.assertEqual(image.alt_text, "Test part")
            self.assertIn("Wikimedia Commons", image.image_source)
            self.assertIn("CC BY-SA 4.0", image.image_source)
            self.assertIn("commons.wikimedia.org", image.source_url)
            self.assertIn("reviewed by eye", image.verification_notes)

    def test_written_file_is_webp_inside_the_gallery_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            product = make_product("Oil Filter", sku="RSH-TEST-OIL-FILTER")
            self._run(self._make_manifest(tmp, product))

            image = ProductImage.objects.get(product=product)
            self.assertTrue(image.image.name.endswith(".webp"))
            self.assertTrue(image.image.name.startswith("products/gallery/"))
            self.assertTrue(image.image.storage.exists(image.image.name))

    def test_rerunning_does_not_duplicate_or_orphan_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            from django.core.files.storage import default_storage

            product = make_product("Oil Filter", sku="RSH-TEST-OIL-FILTER")
            manifest = self._make_manifest(tmp, product)
            self._run(manifest)
            first = ProductImage.objects.get(product=product).image.name
            self._run(manifest)
            self._run(manifest)

            self.assertEqual(ProductImage.objects.filter(product=product).count(), 1)
            self.assertEqual(ProductImage.objects.get(product=product).image.name, first)

            gallery = default_storage.listdir("products/gallery")[1]
            self.assertEqual(len(gallery), 1, f"orphaned files: {gallery}")

    def test_recreates_a_file_that_was_deleted_from_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            from django.core.files.storage import default_storage

            product = make_product("Oil Filter", sku="RSH-TEST-OIL-FILTER")
            manifest = self._make_manifest(tmp, product)
            self._run(manifest)
            name = ProductImage.objects.get(product=product).image.name
            default_storage.delete(name)
            self._run(manifest)

            image = ProductImage.objects.get(product=product)
            self.assertTrue(image.image.storage.exists(image.image.name))

    def test_unknown_sku_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            product = make_product("Oil Filter", sku="RSH-REAL")
            manifest = self._make_manifest(tmp, product)
            bad = json.loads(Path(manifest).read_text(encoding="utf-8"))
            bad[0]["sku"] = "RSH-DOES-NOT-EXIST"
            Path(manifest).write_text(json.dumps(bad), encoding="utf-8")

            from io import StringIO

            from django.core.management import call_command, CommandError

            with self.assertRaises(CommandError):
                call_command("attach_verified_product_images", manifest, stdout=StringIO())
            self.assertEqual(ProductImage.objects.count(), 0)

    def test_duplicate_sku_in_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            product = make_product("Oil Filter", sku="RSH-TEST-OIL-FILTER")
            manifest = self._make_manifest(tmp, product)
            bad = json.loads(Path(manifest).read_text(encoding="utf-8"))
            Path(manifest).write_text(json.dumps(bad + bad), encoding="utf-8")

            from io import StringIO

            from django.core.management import call_command, CommandError

            with self.assertRaises(CommandError):
                call_command("attach_verified_product_images", manifest, stdout=StringIO())

    def test_large_image_is_shrunk_to_a_web_transfer_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image

            product = make_product("Oil Filter", sku="RSH-TEST-OIL-FILTER")
            # Worst case: a noisy 3000px photo that refuses to compress.
            noise = Image.effect_noise((3000, 3000), 60).convert("RGB")
            big = Path(tmp) / "big.jpg"
            noise.save(big, quality=95)

            manifest = self._make_manifest(tmp, product, image_path=big)
            self._run(manifest)

            stored = ProductImage.objects.get(product=product).image
            self.assertLessEqual(
                stored.size, 150 * 1024 + 4096, f"image still {stored.size} bytes"
            )

    def test_optimised_image_still_matches_source_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image

            product = make_product("Oil Filter", sku="RSH-TEST-OIL-FILTER")
            src = Path(tmp) / "wide.jpg"
            Image.new("RGB", (1600, 800), (200, 40, 40)).save(src)

            self._run(self._make_manifest(tmp, product, image_path=src))
            stored = ProductImage.objects.get(product=product).image
            with Image.open(stored.path) as im:
                self.assertAlmostEqual(
                    im.width / im.height, 2.0, delta=0.05, msg="aspect ratio was not preserved"
                )


class ProductCardImageFitTests(SimpleTestCase):
    """Regression: product photos must be letterboxed, never cropped or stretched."""

    @staticmethod
    def _css():
        return (Path(settings.BASE_DIR) / "static" / "css" / "main.css").read_text(encoding="utf-8")

    def test_card_media_image_uses_object_fit_contain(self):
        css = self._css()
        start = css.index(".product-card__media img {")
        rule = css[start:css.index("}", start)]
        self.assertIn("object-fit: contain", rule)

    def test_card_media_image_is_not_zoomed_in(self):
        css = self._css()
        hover = css.index(".product-card:hover .product-card__media img")
        rule = css[hover:css.index("}", hover)]
        scale = float(rule.split("scale(")[1].split(")")[0])
        self.assertLessEqual(scale, 1.05, "hover zoom must not crop the product")

    def test_media_and_placeholder_share_the_same_surface(self):
        css = self._css()
        media = css[css.index(".product-card__media {"):]
        media = media[:media.index("}")]
        placeholder = css[css.index(".product-card__placeholder {"):]
        placeholder = placeholder[:placeholder.index("}")]
        self.assertIn("background: var(--paper)", media)
        self.assertIn("background: var(--paper)", placeholder)


class NoHomePageTests(TestCase):
    """The shop is the landing page: '/' permanently redirects to '/shop/'."""

    def test_root_url_redirects_to_shop(self):
        response = self.client.get("/")
        self.assertRedirects(
            response, "/shop/", status_code=301, fetch_redirect_response=False
        )

    def test_root_redirect_is_permanent(self):
        """301, not 302, so search engines treat the shop as the canonical entry."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["Location"], "/shop/")

    def test_redirect_target_is_the_named_shop_route(self):
        """The target comes from reverse('products:shop'), not a hardcoded path."""
        from django.urls import reverse, resolve

        self.assertEqual(reverse("products:shop"), "/shop/")
        view = resolve("/").func
        self.assertEqual(view.view_class.__name__, "RedirectView")
        self.assertEqual(view.view_initkwargs["pattern_name"], "products:shop")
        self.assertTrue(view.view_initkwargs["permanent"])

    def test_shop_url_still_serves_the_shop_view(self):
        """/shop/ must be untouched by the redirect: same view, same 200."""
        from django.urls import resolve

        self.assertEqual(resolve("/shop/").view_name, "products:shop")
        self.assertEqual(resolve("/shop/").func.__name__, "shop_index")
        response = self.client.get("/shop/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "shop-hero", status_code=200)

    def test_root_url_lands_on_shop(self):
        """Following the redirect must render the catalogue, not a 404."""
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/shop/")
        # The shop page really rendered, rather than an error page.
        self.assertContains(response, "shop-hero", status_code=200)

    def test_no_redirect_loop(self):
        """One hop only: / -> /shop/ must terminate, never bounce back to /."""
        response = self.client.get("/", follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertEqual(response.redirect_chain[0], ("/shop/", 301))
        for _ in range(5):
            self.assertNotEqual(response.request["PATH_INFO"], "/")

    def test_home_url_name_still_resolves(self):
        """reverse('home') keeps working so old bookmarks/links are not orphaned."""
        from django.urls import reverse

        self.assertEqual(reverse("home"), "/")

    def test_slashless_shop_still_appends_slash(self):
        """APPEND_SLASH must keep /shop working without looping."""
        response = self.client.get("/shop")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["Location"], "/shop/")
        self.assertEqual(self.client.get("/shop", follow=True).status_code, 200)

    def test_other_routes_are_unaffected(self):
        """The root route must not shadow sibling top-level paths."""
        from django.urls import reverse

        self.assertEqual(reverse("about"), "/about/")
        self.assertEqual(reverse("contact"), "/contact/")
        self.assertEqual(reverse("customers:login"), "/account/login/")
        self.assertEqual(reverse("orders:cart"), "/orders/cart/")
        self.assertEqual(reverse("terms"), "/terms/")
        for url in ("/about/", "/contact/", "/terms/", "/account/login/"):
            with self.subTest(url=url):
                self.assertNotEqual(self.client.get(url).status_code, 301)

    def test_home_label_absent_from_navigation(self):
        html = self.client.get("/shop/").content.decode()
        self.assertNotIn(">Home<", html)

    def test_logo_points_at_shop(self):
        html = self.client.get("/shop/").content.decode()
        self.assertNotIn("aria-label=\"Ratshie (Pty) Ltd home\"", html)
        self.assertIn('class="brand"', html)

    def test_no_template_references_home_url(self):
        """Guards against a stray {% url 'home' %} creeping back into a footer."""
        from pathlib import Path

        offenders = []
        for path in Path("templates").rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if "{% url 'home' %}" in text or "core/home.html" in text:
                offenders.append(str(path))
        self.assertEqual(offenders, [])

    def test_home_page_template_is_deleted(self):
        from pathlib import Path

        self.assertFalse(Path("templates/core/home.html").exists())
