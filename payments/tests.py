"""Tests for the PayFast integration (payments app)."""
import re
from decimal import Decimal
from unittest import mock
from urllib.error import URLError

from django.test import TestCase, override_settings
from django.urls import reverse

from core.utils import amount_str, payfast_sign
from orders.models import Order
from payments.models import Payment
from payments.views import (
    _amount_matches,
    _build_payfast_fields,
    _update_payment_from_itn,
    _validated_by_payfast,
    _verify_signature,
)

TEST_PAYFAST = {
    "PAYFAST_MERCHANT_ID": "10054184",
    "PAYFAST_MERCHANT_KEY": "qj6m1q1x51moy",
    "PAYFAST_PASSPHRASE": "testpassphrase",
    "PAYFAST_SANDBOX": True,
    "PAYFAST_RETURN_URL_PREFIX": "http://127.0.0.1:8000",
}


def make_payment(**overrides):
    order = Order.objects.create(
        status=Order.Status.PAYMENT_PENDING,
        payment_status=Order.Status.PAYMENT_PENDING,
    )
    order.recalc_totals()
    return Payment.objects.create(
        reference="PF-TEST-REF-1",
        order=order,
        amount=Decimal("100.00"),
        description="Order RS-TEST",
        **overrides,
    )


def itn_payload(payment, signature=True, **overrides):
    data = {
        "m_payment_id": payment.reference,
        "merchant_id": "10054184",
        "merchant_key": "qj6m1q1x51moy",
        "pf_payment_id": "56781234",
        "payment_status": "COMPLETE",
        "item_name": payment.description,
        "amount": amount_str(payment.amount),
    }
    data.update(overrides)
    if signature:
        data["signature"] = payfast_sign(data)
    return data


@override_settings(**TEST_PAYFAST)
class PaymentDetailsViewTests(TestCase):
    def setUp(self):
        self.payment = make_payment()

    def test_details_renders_payfast_form_when_configured(self):
        url = reverse("payments:details", kwargs={"reference": self.payment.reference})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertTrue(ctx["payfast_enabled"])
        self.assertTrue(ctx["sandbox"])
        self.assertEqual(
            ctx["payfast_url"], "https://sandbox.payfast.co.za/eng/process"
        )
        fields = ctx["form_fields"]
        self.assertEqual(fields["merchant_id"], "10054184")
        self.assertEqual(fields["m_payment_id"], self.payment.reference)
        self.assertEqual(fields["amount"], "100.00")
        self.assertIn("signature", fields)

    @override_settings(
        PAYFAST_MERCHANT_ID="", PAYFAST_MERCHANT_KEY="", PAYFAST_ENABLED=False
    )
    def test_details_no_form_when_disabled(self):
        url = reverse("payments:details", kwargs={"reference": self.payment.reference})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertFalse(ctx["payfast_enabled"])
        self.assertEqual(ctx["form_fields"], {})
        self.assertEqual(ctx["payfast_url"], "")

    def test_details_404_for_unknown_reference(self):
        url = reverse("payments:details", kwargs={"reference": "NOPE-123"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def _payfast_form(self, response):
        """Return (names, values) of every hidden input in the PayFast <form>."""
        html = response.content.decode()
        m = re.search(r'<form[^>]*action="[^"]+payfast[^"]*"[^>]*>(.*?)</form>', html, re.S)
        self.assertIsNotNone(m, "PayFast form not found in details page")
        inputs = re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', m.group(1))
        return [k for k, _ in inputs], {k: v for k, v in inputs}

    def test_details_form_submits_only_signed_fields(self):
        """Regression for 'Generated signature does not match submitted
        signature': the form must POST exactly the canonical signed fields to
        PayFast. Any extra hidden input (e.g. csrfmiddlewaretoken) is included
        by PayFast when it regenerates the signature, guaranteeing a mismatch."""
        url = reverse("payments:details", kwargs={"reference": self.payment.reference})
        names, _ = self._payfast_form(self.client.get(url))
        self.assertNotIn("csrfmiddlewaretoken", names)
        self.assertEqual(
            names,
            [
                "merchant_id",
                "merchant_key",
                "return_url",
                "cancel_url",
                "notify_url",
                "m_payment_id",
                "amount",
                "item_name",
                "signature",
            ],
        )

    def test_details_signature_reconstructs_from_form_fields(self):
        """The submitted signature must equal PayFast's recomputation over the
        exact fields rendered in the form (canonical data, nothing added later)."""
        url = reverse("payments:details", kwargs={"reference": self.payment.reference})
        _, fields = self._payfast_form(self.client.get(url))
        sig = fields.pop("signature")
        self.assertNotEqual(sig, "")
        self.assertEqual(payfast_sign(fields), sig)


@override_settings(**TEST_PAYFAST)
class PayfastFieldsTests(TestCase):
    def test_build_payfast_fields_urls(self):
        payment = make_payment()
        fields = _build_payfast_fields(payment)
        self.assertEqual(
            fields["return_url"],
            f"http://127.0.0.1:8000/payments/return/{payment.reference}/",
        )
        self.assertEqual(
            fields["cancel_url"],
            f"http://127.0.0.1:8000/payments/cancel/{payment.reference}/",
        )
        self.assertEqual(
            fields["notify_url"], "http://127.0.0.1:8000/payments/itn/"
        )
        self.assertEqual(fields["amount"], "100.00")
        self.assertNotEqual(fields["signature"], "")


@override_settings(**TEST_PAYFAST)
class AmountMatchingTests(TestCase):
    def setUp(self):
        self.payment = make_payment()

    def test_exact_match(self):
        self.assertTrue(_amount_matches(self.payment, {"amount": "100.00"}))

    def test_mismatch_rejected(self):
        self.assertFalse(_amount_matches(self.payment, {"amount": "100.01"}))
        self.assertFalse(_amount_matches(self.payment, {"amount": "1.00"}))

    def test_invalid_amount_rejected(self):
        self.assertFalse(_amount_matches(self.payment, {"amount": "not-a-number"}))
        self.assertFalse(_amount_matches(self.payment, {"amount": ""}))


@override_settings(**TEST_PAYFAST)
class SignatureVerificationTests(TestCase):
    def test_valid_signature(self):
        data = {"a": "1", "b": "hello world"}
        data["signature"] = payfast_sign(data)
        self.assertTrue(_verify_signature(data))

    def test_token_field_does_not_break_verification(self):
        data = {"a": "1"}
        data["signature"] = payfast_sign(data)  # signature excludes the token
        data["token"] = "abc123"  # PayFast appends token to the ITN POST
        self.assertTrue(_verify_signature(data))

    def test_missing_signature_fails(self):
        self.assertFalse(_verify_signature({"a": "1"}))

    def test_tampered_signature_fails(self):
        data = {"a": "1"}
        data["signature"] = payfast_sign(data)
        data["a"] = "2"  # tamper after signing
        self.assertFalse(_verify_signature(data))

    def test_changed_value_fails(self):
        data = {"m_payment_id": "PF-TEST-REF-1", "amount": "100.00"}
        data["signature"] = payfast_sign(data)
        data["amount"] = "999.00"
        self.assertFalse(_verify_signature(data))


@override_settings(**TEST_PAYFAST)
class ItnViewTests(TestCase):
    def setUp(self):
        self.payment = make_payment()

    def test_success_itn_marks_payment_and_order_paid(self):
        url = reverse("payments:itn")
        with mock.patch("payments.views._validated_by_payfast", return_value=True):
            response = self.client.post(url, itn_payload(self.payment))
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.order = self.payment.order
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, "success")
        self.assertEqual(self.payment.payfast_transaction_id, "56781234")
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.order.payment_status, Order.Status.PAID)
        self.assertEqual(self.order.payfast_transaction_id, "56781234")

    def test_bad_signature_returns_400(self):
        url = reverse("payments:itn")
        data = itn_payload(self.payment)
        data["signature"] = "deadbeef" * 4
        with mock.patch("payments.views._validated_by_payfast", return_value=True) as m:
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        m.assert_not_called()

    def test_itn_without_signature_returns_400(self):
        url = reverse("payments:itn")
        response = self.client.post(url, itn_payload(self.payment, signature=False))
        self.assertEqual(response.status_code, 400)

    def test_failed_external_validation_returns_400(self):
        url = reverse("payments:itn")
        with mock.patch("payments.views._validated_by_payfast", return_value=False):
            response = self.client.post(url, itn_payload(self.payment))
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")

    def test_amount_tampering_does_not_mark_paid(self):
        url = reverse("payments:itn")
        data = itn_payload(self.payment, amount="0.01")
        with mock.patch("payments.views._validated_by_payfast", return_value=True):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.payment.payfast_transaction_id, "")

    def test_failed_itn_from_pending_cancels_order(self):
        url = reverse("payments:itn")
        data = itn_payload(self.payment, payment_status="FAILED")
        with mock.patch("payments.views._validated_by_payfast", return_value=True):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.order = self.payment.order
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")
        self.assertEqual(self.order.status, Order.Status.CANCELLED)

    def test_duplicate_success_is_not_downgraded(self):
        self.payment.status = "success"
        self.payment.save()
        url = reverse("payments:itn")
        data = itn_payload(self.payment, payment_status="FAILED")
        with mock.patch("payments.views._validated_by_payfast", return_value=True):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "success")

    def test_pending_itn_keeps_pending(self):
        url = reverse("payments:itn")
        data = itn_payload(self.payment, payment_status="PENDING")
        with mock.patch("payments.views._validated_by_payfast", return_value=True):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")

    def test_unknown_reference_returns_200(self):
        url = reverse("payments:itn")
        data = itn_payload(self.payment, signature=False)
        data["m_payment_id"] = "DOES-NOT-EXIST"
        data["signature"] = payfast_sign(data)
        with mock.patch("payments.views._validated_by_payfast", return_value=True):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)


@override_settings(**TEST_PAYFAST)
class PaymentReturnCancelTests(TestCase):
    def setUp(self):
        self.payment = make_payment()

    def test_return_success_state_when_paid(self):
        self.payment.status = "success"
        self.payment.save()
        url = reverse("payments:return", kwargs={"reference": self.payment.reference})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["state"], "success")

    def test_return_failed_state_when_failed(self):
        self.payment.status = "failed"
        self.payment.save()
        url = reverse("payments:return", kwargs={"reference": self.payment.reference})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["state"], "failed")

    def test_return_pending_honours_query_hint(self):
        url = reverse("payments:return", kwargs={"reference": self.payment.reference})
        response = self.client.get(url, {"payment_status": "complete"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["state"], "success")

    def test_return_pending_without_hint(self):
        url = reverse("payments:return", kwargs={"reference": self.payment.reference})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["state"], "pending")

    def test_cancel_state(self):
        url = reverse("payments:cancel", kwargs={"reference": self.payment.reference})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["state"], "cancelled")


@override_settings(**TEST_PAYFAST)
class ValidatedByPayfastTests(TestCase):
    def _fake_urlopen(self, payload, exc=None):
        if exc:
            inner = mock.Mock(side_effect=exc)
        else:
            inner = mock.MagicMock()
            inner.read.return_value = payload
            inner.__enter__.return_value = inner  # make `with urlopen(...) as resp` yield inner
        return mock.patch("urllib.request.urlopen", return_value=inner)

    def test_valid_response(self):
        with self._fake_urlopen(b"VALID"):
            self.assertTrue(_validated_by_payfast({"x": "1"}))

    def test_invalid_response(self):
        with self._fake_urlopen(b"INVALID"):
            self.assertFalse(_validated_by_payfast({"x": "1"}))

    def test_blank_response(self):
        with self._fake_urlopen(b""):
            self.assertFalse(_validated_by_payfast({"x": "1"}))

    def test_network_error_fails_closed(self):
        with self._fake_urlopen(None, exc=URLError("boom")):
            self.assertFalse(_validated_by_payfast({"x": "1"}))


@override_settings(**TEST_PAYFAST)
class UpdatePaymentFromItnTests(TestCase):
    def setUp(self):
        self.payment = make_payment()

    def test_returns_none_for_unknown_reference(self):
        data = {"m_payment_id": "UNKNOWN", "amount": "100.00"}
        self.assertIsNone(_update_payment_from_itn(data))

    def test_returns_none_when_amount_mismatch(self):
        data = {"m_payment_id": self.payment.reference, "amount": "1.00"}
        self.assertIsNone(_update_payment_from_itn(data))

    def test_returns_payment_on_success(self):
        data = itn_payload(self.payment)
        result = _update_payment_from_itn(data)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "success")

    def test_success_then_failed_preserves_success(self):
        data = itn_payload(self.payment)
        _update_payment_from_itn(data)
        failed = itn_payload(self.payment, payment_status="FAILED")
        _update_payment_from_itn(failed)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "success")