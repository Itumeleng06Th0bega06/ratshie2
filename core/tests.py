"""Tests for core helpers: PayFast signing/formatting and WhatsApp links."""
from decimal import Decimal

from django.test import TestCase, override_settings

from core.utils import (
    amount_str,
    payfast_sign,
    payfast_submit_url,
    product_whatsapp_message,
    wa_msg_link,
    wa_short_link,
)


class PayfastSubmitUrlTests(TestCase):
    @override_settings(PAYFAST_SANDBOX=True)
    def test_sandbox_url(self):
        self.assertEqual(
            payfast_submit_url(), "https://sandbox.payfast.co.za/eng/process"
        )

    @override_settings(PAYFAST_SANDBOX=False)
    def test_live_url(self):
        self.assertEqual(
            payfast_submit_url(), "https://www.payfast.co.za/eng/process"
        )


class AmountStrTests(TestCase):
    def test_formats_two_decimals(self):
        self.assertEqual(amount_str(Decimal("10.5")), "10.50")
        self.assertEqual(amount_str("12"), "12.00")
        self.assertEqual(amount_str(Decimal("0")), "0.00")

    def test_no_thousand_separators(self):
        self.assertEqual(amount_str(Decimal("1234567.89")), "1234567.89")

    def test_rounds_to_two_decimals(self):
        self.assertEqual(amount_str(Decimal("99.999")), "100.00")


class PayfastSignTests(TestCase):
    @override_settings(PAYFAST_PASSPHRASE="testpassphrase")
    def test_signature_vector_in_submission_order(self):
        """Regression pin over PayFast's example data, signed in the order the
        fields are submitted (the checkout-form rule in their docs)."""
        data = {
            "merchant_id": "10010000",
            "merchant_key": "botwt926ngxbg",
            "return_url": "https://www.payfast.co.za/eng/process",
            "m_payment_id": "1001",
            "amount": "100.00",
            "item_name": "OrderTest",
        }
        self.assertEqual(payfast_sign(data), "abde8cec044ae8e6a7b90fbc0592e55f")

    @override_settings(PAYFAST_PASSPHRASE="")
    def test_signature_without_passphrase(self):
        data = {"merchant_id": "100", "amount": "1.00"}
        expected = payfast_sign(data)
        self.assertEqual(len(expected), 32)
        self.assertTrue(expected.isalnum())

    @override_settings(PAYFAST_PASSPHRASE="secret?phrase")
    def test_signature_changes_with_field_order(self):
        data1 = {"b": "x", "a": "y"}
        data2 = {"a": "y", "b": "x"}
        self.assertNotEqual(payfast_sign(data1), payfast_sign(data2))

    @override_settings(PAYFAST_PASSPHRASE="ph")
    def test_values_are_php_url_encoded(self):
        data = {"item_name": "Brake pads & fluid", "amount": "100.00"}
        sig = payfast_sign(data)
        # PHP urlencode keeps spaces as '+' and ampersands are percent-encoded.
        self.assertNotIn("&amp;", sig)
        self.assertNotIn("Brake pads", sig)


class WhatsAppLinkTests(TestCase):
    @override_settings(WHATSAPP_NUMBER="27659017566")
    def test_wa_short_link(self):
        self.assertEqual(wa_short_link(), "https://wa.me/27659017566")

    @override_settings(WHATSAPP_NUMBER="0659017566")
    def test_wa_short_link_normalises_local_number(self):
        self.assertEqual(wa_short_link(), "https://wa.me/27659017566")

    @override_settings(WHATSAPP_NUMBER="")
    def test_wa_short_link_empty_fallback(self):
        self.assertEqual(wa_short_link(), "https://wa.me")

    @override_settings(WHATSAPP_NUMBER="27659017566")
    def test_wa_msg_link_encodes_message(self):
        link = wa_msg_link("Hi there & welcome")
        self.assertIn("text=Hi%20there%20%26%20welcome", link)

    @override_settings(WHATSAPP_NUMBER="27659017566")
    def test_product_whatsapp_message_includes_details(self):
        msg = product_whatsapp_message(product_name="Brake Pads", sku="BP-01", price=Decimal("250.00"), quantity=2)
        self.assertIn("Product: Brake Pads", msg)
        self.assertIn("SKU: BP-01", msg)
        self.assertIn("Price: R 250.00", msg)
        self.assertIn("Quantity required: 2", msg)