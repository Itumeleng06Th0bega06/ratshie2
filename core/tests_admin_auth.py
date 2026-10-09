"""Tests for admin login with username or email address.

Covers the admin-only authentication form (core.forms.HoneypottedAdmin-
AuthenticationForm): both identifiers work, wrong credentials and unknown
identifiers are rejected, shared email addresses fail safely, inactive and
non-staff accounts are refused, superuser/staff access still works, and the
public website login is untouched.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.forms import HoneypottedAdminAuthenticationForm

User = get_user_model()

PASSWORD = "s3cure-pass-123"


class AdminEmailUsernameLoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            email="admin@ratshie.co.za",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )

    def _url(self, name):
        return reverse(f"admin:{name}")

    def _post(self, identifier, password):
        return self.client.post(
            self._url("login"),
            {"username": identifier, "password": password},
        )

    def _assert_logged_in(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(self.client.session["_auth_user_id"]), str(self.user.pk))
        # Accessing the admin index proves has_permission() passed.
        self.assertEqual(self.client.get(self._url("index")).status_code, 200)

    def _assert_login_refused(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_site_uses_the_email_or_username_form(self):
        self.assertIs(admin.site.login_form, HoneypottedAdminAuthenticationForm)

    def test_login_field_is_labelled_username_or_email_address(self):
        response = self.client.get(self._url("login"))
        form = response.context["form"]
        self.assertEqual(form.fields["username"].label, "Username or email address")
        self.assertEqual(
            form.fields["username"].widget.attrs["placeholder"], "Username or email address"
        )

    def test_login_succeeds_with_username(self):
        response = self._post("admin", PASSWORD)
        self._assert_logged_in(response)

    def test_login_succeeds_with_email(self):
        response = self._post("admin@ratshie.co.za", PASSWORD)
        self._assert_logged_in(response)

    def test_email_match_is_case_insensitive(self):
        response = self._post("ADMIN@RATSHIE.CO.ZA", PASSWORD)
        self._assert_logged_in(response)

    def test_wrong_password_is_rejected_by_username(self):
        response = self._post("admin", "wrong-password")
        self._assert_login_refused(response)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_wrong_password_is_rejected_by_email(self):
        response = self._post("admin@ratshie.co.za", "wrong-password")
        self._assert_login_refused(response)
        self.assertTrue(response.context["form"].non_field_errors())

    def test_unknown_username_is_rejected(self):
        response = self._post("nobody", PASSWORD)
        self._assert_login_refused(response)

    def test_unknown_email_is_rejected(self):
        response = self._post("unknown@example.com", PASSWORD)
        self._assert_login_refused(response)

    def test_shared_email_cannot_login_arbitrary_account(self):
        User.objects.create_user(
            username="admin2",
            email="shared@example.com",
            password="other-pass-456",
            is_staff=True,
        )
        self.user.email = "shared@example.com"
        self.user.save()
        # The correct password for either account is still refused: ambiguous.
        response = self._post("shared@example.com", PASSWORD)
        self._assert_login_refused(response)
        self.assertIn("username", response.context["form"].errors)
        response = self._post("shared@example.com", "other-pass-456")
        self._assert_login_refused(response)

    def test_inactive_user_cannot_login_by_username(self):
        self.user.is_active = False
        self.user.save()
        response = self._post("admin", PASSWORD)
        self._assert_login_refused(response)

    def test_inactive_user_cannot_login_by_email(self):
        self.user.is_active = False
        self.user.save()
        response = self._post("admin@ratshie.co.za", PASSWORD)
        self._assert_login_refused(response)

    def test_non_staff_user_cannot_login_by_username(self):
        self.user.is_staff = False
        self.user.save()
        response = self._post("admin", PASSWORD)
        self._assert_login_refused(response)

    def test_non_staff_user_cannot_login_by_email(self):
        self.user.is_staff = False
        self.user.save()
        response = self._post("admin@ratshie.co.za", PASSWORD)
        self._assert_login_refused(response)

    def test_honeypot_still_trips_and_refuses(self):
        response = self.client.post(
            self._url("login"),
            {"username": "admin", "password": PASSWORD, "website": "spam"},
        )
        self._assert_login_refused(response)


class PublicLoginUnchangedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member1",
            email="member@example.com",
            password=PASSWORD,
        )

    def test_public_login_still_accepts_username(self):
        response = self.client.post(
            reverse("customers:login"),
            {"username": "member1", "password": PASSWORD},
        )
        self.assertRedirects(response, reverse("customers:account"))
        self.assertEqual(str(self.client.session["_auth_user_id"]), str(self.user.pk))

    def test_admin_form_is_distinct_from_public_login_form(self):
        from customers.forms import LoginForm

        self.assertFalse(issubclass(LoginForm, HoneypottedAdminAuthenticationForm))
        self.assertNotEqual(LoginForm.declared_fields["username"].label, "Username or email address")