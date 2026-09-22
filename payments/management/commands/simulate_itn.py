"""Simulate a PayFast ITN against /payments/itn/ without a public tunnel.

Builds a correctly-signed ITN payload (real merchant key + passphrase) for a
chosen Payment and POSTs it in-process through the real URL/view, so signature
verification, amount matching and status transitions all run for real.

PayFast's external validate endpoint (sandbox.payfast.co.za/eng/query/validate)
only answers VALID for transactions PayFast itself generated, so synthetic ITNs
fail that gate. The command therefore skips that external re-validation BY
DEFAULT (--verify-external opts back in, expecting INVALID for fabricated data).
"""
import random
import sys
import unittest.mock
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from core.utils import amount_str, payfast_sign
from orders.models import Order, OrderItem
from payments import views as payment_views
from payments.models import Payment


class Command(BaseCommand):
    help = (
        "Send a signed PayFast ITN to /payments/itn/ to exercise the full "
        "server-to-server path locally."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reference", default="", help="Payment.reference to target."
        )
        parser.add_argument(
            "--create-sample",
            action="store_true",
            help="Create a sample Order + Payment to simulate against.",
        )
        parser.add_argument(
            "--amount",
            default="100.00",
            help="Amount for a created sample payment (default 100.00).",
        )
        parser.add_argument(
            "--pf-payment-id",
            default="",
            help="PayFast transaction id to send (defaults to a random id).",
        )
        parser.add_argument(
            "--status",
            default="complete",
            choices=["complete", "pending", "failed", "cancelled", "denied"],
            help="payment_status to announce (default complete).",
        )
        parser.add_argument(
            "--tamper-amount",
            default="",
            help="Send a DIFFERENT amount than stored (tests mismatch rejection).",
        )
        parser.add_argument(
            "--bad-signature",
            action="store_true",
            help="Send a garbage signature (expect 400).",
        )
        parser.add_argument(
            "--verify-external",
            action="store_true",
            help="Call PayFast's real validate endpoint (INVALID for synthetic ITNs).",
        )

    def handle(self, *args, **opts):
        if opts["reference"]:
            payment = Payment.objects.filter(reference=opts["reference"]).first()
            if not payment:
                raise CommandError(f"No Payment with reference {opts['reference']!r}.")
        elif opts["create_sample"]:
            payment = self._create_sample(Decimal(opts["amount"]))
        else:
            raise CommandError("Pass --reference <ref> or --create-sample.")

        data = {
            "m_payment_id": payment.reference,
            "pf_payment_id": opts["pf_payment_id"]
            or f"SIM{random.randint(10**7, 10**8 - 1)}",
            "payment_status": opts["status"],
            "item_name": payment.description or f"Payment {payment.reference}",
            "amount": amount_str(opts["tamper_amount"])
            if opts["tamper_amount"]
            else amount_str(payment.amount),
        }
        data["signature"] = "0" * 32 if opts["bad_signature"] else payfast_sign(data)

        self.stdout.write(self.style.HTTP_INFO("Simulating ITN (sandbox=%s)" % settings.PAYFAST_SANDBOX))
        for k, v in data.items():
            self.stdout.write(f"  {k}: {v}")

        self._print_state("BEFORE", payment)

        # Synthetic ITNs are not VALID at PayFast's validate endpoint, so keep
        # the external re-validation OFF unless the caller explicitly opts in.
        with unittest.mock.patch.object(
            payment_views, "_validated_by_payfast", return_value=not opts["verify_external"]
        ):
            client = Client(enforce_csrf_checks=False)
            host = (settings.ALLOWED_HOSTS or ["testserver"])[0]
            response = client.post(reverse("payments:itn"), data, HTTP_HOST=host)

        payment.refresh_from_db()
        self.stdout.write(self.style.HTTP_INFO(f"=> HTTP {response.status_code}"))
        if response.status_code != 200:
            self.stdout.write(self.style.WARNING(f"   body: {response.content.decode()[:120]}"))
        self._print_state("AFTER ", payment)

    def _create_sample(self, amount: Decimal) -> Payment:
        order = Order.objects.create(
            customer_name="ITN Simulator",
            email="simulator@example.com",
            phone="000 000 0000",
            delivery_option=Order.DeliveryChoice.COLLECTION,
            status=Order.Status.PAYMENT_PENDING,
            payment_status=Order.Status.PAYMENT_PENDING,
            payment_reference=Order._generate_reference(),
        )
        OrderItem.objects.create(
            order=order,
            product_name="Simulated part (ITN test)",
            quantity=1,
            unit_price=amount,
        )
        order.recalc_totals()
        payment = Payment.objects.create(
            reference=order.payment_reference,
            order=order,
            amount=order.total,
            description=f"Order {order.reference}",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created sample Payment {payment.reference} "
                f"(amount {amount_str(payment.amount)}, order {order.reference})."
            )
        )
        return payment

    @staticmethod
    def _print_state(label: str, payment: Payment) -> None:
        order = payment.order
        order_bit = (
            f"order={order.status!r} order_payment={order.payment_status!r}"
            if order
            else "no order"
        )
        print(
            f"{label} payment={payment.status!r} "
            f"pf_txn={payment.payfast_transaction_id or '-'} {order_bit}",
            file=sys.stderr,
        )