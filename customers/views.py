"""Customer account: registration, sign in, sign out and account overview.

Credentials are handled exclusively through Django's built-in authentication
(password hashing, sessions, CSRF) — we never weaken security to make the
async flow simpler. Registration/login errors are field-specific so only the
offending field is flagged and valid input is preserved.
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.urls import reverse

from .forms import LoginForm, RegistrationForm
from .models import Customer
from orders.models import Order


def _next_url(request):
    return request.POST.get("next", "") or request.GET.get("next", "")


def _auth_context(request, form, **extra):
    ctx = {"form": form, "next_url": _next_url(request), **extra}
    return ctx


def login_view(request):
    if request.user.is_authenticated:
        return redirect("customers:account")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.POST.get("next", "")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect("customers:account")
        if request.headers.get("HX-Request"):
            return render(
                request,
                "customers/login_form.html",
                _auth_context(request, form, is_partial=True),
                status=422,
            )
    return render(request, "customers/login.html", _auth_context(request, form))


@require_POST
def logout_view(request):
    logout(request)
    next_url = request.POST.get("next", "") or reverse("home")
    if request.headers.get("HX-Request"):
        return render(request, "components/logged_out.html", {"next": next_url})
    return redirect(next_url if next_url.startswith("/") else reverse("home"))


def register_view(request):
    if request.user.is_authenticated:
        return redirect("customers:account")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            data = form.cleaned_data
            base = data["email"].split("@")[0] or "member"
            username, n = base, 1
            while User.objects.filter(username__iexact=username).exists():
                username = f"{base}{n}"
                n += 1
            user = User.objects.create_user(
                username=username,
                email=data["email"],
                password=data["password1"],
                first_name=data["first_name"],
                last_name=data["last_name"],
            )

            Customer.objects.create(
                user=user,
                full_name=f"{data['first_name']} {data['last_name']}".strip(),
                email=data["email"],
                phone=data.get("phone", ""),
            )

            # Authenticate the new member automatically.
            login(request, user)
            messages.success(request, "Account created successfully. Welcome to Ratshie!")
            next_url = request.POST.get("next", "")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect("customers:account")
        if request.headers.get("HX-Request"):
            return render(
                request,
                "customers/register_form.html",
                _auth_context(request, form, is_partial=True),
                status=422,
            )
    return render(request, "customers/register.html", _auth_context(request, form))


@login_required
def account_view(request):
    customer = Customer.objects.filter(user=request.user).first()
    orders = Order.objects.filter(customer=customer).order_by("-created_at") if customer else []
    return render(
        request,
        "customers/account.html",
        {"profile": customer, "orders": orders},
    )
