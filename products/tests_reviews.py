"""Tests for the product rating & member review system.

Covers:
- Rating aggregation on the Product model (average, count, per-star
  distribution) and that hidden reviews are excluded everywhere.
- One review per member per product (the unique constraint).
- Anonymous visitors see a sign-in prompt; members see the form.
- Creating, updating (never duplicating) and deleting a review.
- Server-side validation of the rating and a useful comment.
- Ratings surface on the shop cards and in the product's JSON-LD.

Runs against Django's throwaway test database, so db.sqlite3 is untouched.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Product, ProductReview

User = get_user_model()


def make_product(name="Oil Filter", **kwargs):
    defaults = {
        "name": name,
        "price": Decimal("199.00"),
        "stock": 5,
        "availability": "in_stock",
        "is_available": True,
    }
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


def make_user(username="member", **kwargs):
    kwargs.setdefault("password", "test-pass-123")
    return User.objects.create_user(username, **kwargs)


class RatingAggregationTests(TestCase):
    def test_empty_product_has_no_rating(self):
        product = make_product()
        self.assertEqual(product.rating_count, 0)
        self.assertIsNone(product.average_rating)
        self.assertEqual(
            product.rating_distribution,
            [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0)],
        )

    def test_average_count_and_distribution(self):
        product = make_product()
        ProductReview.objects.create(product=product, user=make_user("a"), rating=5, comment="Excellent")
        ProductReview.objects.create(product=product, user=make_user("b"), rating=3, comment="It is okay")

        fresh = Product.objects.get(pk=product.pk)
        self.assertEqual(fresh.rating_count, 2)
        self.assertEqual(fresh.average_rating, 4.0)
        self.assertEqual(
            fresh.rating_distribution,
            [(1, 0), (2, 0), (3, 1), (4, 0), (5, 1)],
        )

    def test_average_rounds_to_one_decimal(self):
        product = make_product()
        ProductReview.objects.create(product=product, user=make_user("a"), rating=5, comment="Five stars")
        ProductReview.objects.create(product=product, user=make_user("b"), rating=4, comment="Four stars")
        ProductReview.objects.create(product=product, user=make_user("c"), rating=4, comment="Four again")
        fresh = Product.objects.get(pk=product.pk)
        self.assertEqual(fresh.average_rating, 4.3)

    def test_hidden_reviews_are_excluded(self):
        product = make_product()
        ProductReview.objects.create(
            product=product, user=make_user("a"), rating=1, comment="Spam", is_visible=False
        )
        fresh = Product.objects.get(pk=product.pk)
        self.assertEqual(fresh.rating_count, 0)
        self.assertIsNone(fresh.average_rating)

    def test_one_review_per_member_per_product(self):
        product = make_product()
        user = make_user()
        ProductReview.objects.create(product=product, user=user, rating=5, comment="First")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductReview.objects.create(product=product, user=user, rating=1, comment="Second")


class ReviewDisplayTests(TestCase):
    def setUp(self):
        self.product = make_product()
        self.user = make_user(first_name="Thabo")

    def test_anonymous_sees_signin_prompt_instead_of_form(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Share your experience")
        self.assertNotContains(
            response, reverse("products:review_submit", args=[self.product.slug])
        )

    def test_member_sees_the_review_form(self):
        self.client.force_login(self.user)
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, 'id="reviews"')
        self.assertContains(
            response, reverse("products:review_submit", args=[self.product.slug])
        )

    def test_review_is_rendered_on_the_detail_page(self):
        ProductReview.objects.create(
            product=self.product, user=self.user, rating=4, title="Solid", comment="Works well"
        )
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "Solid")
        self.assertContains(response, "Works well")
        self.assertContains(response, "Thabo")

    def test_existing_review_prefills_the_picker_and_fields(self):
        ProductReview.objects.create(
            product=self.product, user=self.user, rating=3, title="My headline", comment="My review body"
        )
        self.client.force_login(self.user)
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(
            response, 'value="3" class="star-picker__input" checked'
        )
        self.assertContains(response, 'value="My headline"')
        self.assertContains(response, "My review body")

    def test_structured_data_gains_aggregate_rating(self):
        ProductReview.objects.create(
            product=self.product, user=self.user, rating=5, comment="Perfect"
        )
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "aggregateRating")
        self.assertContains(response, "ratingValue")

    def test_detail_page_reports_average_rating(self):
        ProductReview.objects.create(
            product=self.product, user=self.user, rating=5, comment="Perfect"
        )
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "1 review")


class ReviewSubmitTests(TestCase):
    def setUp(self):
        self.product = make_product()
        self.user = make_user()
        self.url = reverse("products:review_submit", args=[self.product.slug])

    def test_requires_login(self):
        response = self.client.post(self.url, {"rating": "5", "comment": "A great product"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("customers:login"), response.url)
        self.assertFalse(ProductReview.objects.exists())

    def test_get_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_creates_a_visible_review(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url, {"rating": "5", "title": "Great", "comment": "Very happy with it"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith("#reviews"))
        review = ProductReview.objects.get(product=self.product, user=self.user)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.title, "Great")
        self.assertTrue(review.is_visible)

    def test_resubmitting_updates_instead_of_duplicating(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"rating": "5", "comment": "First thoughts"})
        self.client.post(self.url, {"rating": "2", "comment": "Changed my mind"})

        self.assertEqual(
            ProductReview.objects.filter(product=self.product, user=self.user).count(), 1
        )
        review = ProductReview.objects.get(product=self.product, user=self.user)
        self.assertEqual(review.rating, 2)
        self.assertEqual(review.comment, "Changed my mind")

    def test_rating_out_of_range_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"rating": "9", "comment": "A great product"})
        self.assertEqual(response.status_code, 200)  # the page is re-rendered
        self.assertFalse(ProductReview.objects.exists())
        self.assertContains(response, "valid")

    def test_missing_rating_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"comment": "A great product"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductReview.objects.exists())

    def test_too_short_comment_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"rating": "4", "comment": "ok"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductReview.objects.exists())
        self.assertContains(response, "short sentence")


class ReviewDeleteTests(TestCase):
    def setUp(self):
        self.product = make_product()
        self.user = make_user("owner")
        self.other = make_user("other")
        self.review = ProductReview.objects.create(
            product=self.product, user=self.user, rating=5, comment="My honest review"
        )
        self.url = reverse("products:review_delete", args=[self.product.slug])

    def test_member_can_delete_their_own_review(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProductReview.objects.filter(pk=self.review.pk).exists())

    def test_member_cannot_delete_someone_elses_review(self):
        self.client.force_login(self.other)
        self.client.post(self.url)
        self.assertTrue(ProductReview.objects.filter(pk=self.review.pk).exists())

    def test_delete_requires_login(self):
        self.client.post(self.url)
        self.assertTrue(ProductReview.objects.filter(pk=self.review.pk).exists())


class ShopRatingTests(TestCase):
    def test_reviewed_product_shows_stars_on_the_card(self):
        product = make_product()
        ProductReview.objects.create(product=product, user=make_user(), rating=4, comment="Good stuff")
        response = self.client.get(reverse("products:shop"))
        self.assertContains(response, "product-card__rating")
        self.assertContains(response, "4.0")

    def test_product_without_reviews_shows_no_stars(self):
        make_product()
        response = self.client.get(reverse("products:shop"))
        self.assertNotContains(response, "product-card__rating")
