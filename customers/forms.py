"""Customer account forms.

Validation is intentionally field-specific: each Django form field only
reports problems about itself so the UI can flag exactly the field that needs
correction (never marking every field invalid at once).
"""
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email


class LoginForm(AuthenticationForm):
    """Login that accepts either a username or an email address.

    ``AuthenticationForm.username`` is re-labelled and cleaned so a visitor can
    sign in with their registered email address. Username/password mismatches
    are surfaced as a single generic credential error (placed on the
    username/email field as per the specs, since Django cannot safely tell
    whether the account exists without leaking account existence).
    """

    username = forms.CharField(
        label="Username or email",
        widget=forms.TextInput(
            attrs={
                "placeholder": "you@example.com or username",
                "autocomplete": "username",
                "autocapitalize": "none",
                "autocorrect": "off",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"placeholder": "Your password", "autocomplete": "current-password"}
        ),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "We could not find an account with those details.",
    }

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        # Allow email-or-username authentication.
        user = User.objects.filter(email__iexact=username).first()
        if user is not None:
            return user.get_username()
        return username


class RegistrationForm(forms.Form):
    first_name = forms.CharField(
        label="First name",
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "First name", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        label="Last name",
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Last name", "autocomplete": "family-name"}),
    )
    phone = forms.CharField(
        label="Phone number",
        required=False,
        max_length=32,
        widget=forms.TextInput(
            attrs={"placeholder": "+27 ...", "autocomplete": "tel", "inputmode": "tel"}
        ),
        help_text="Optional, used for order updates.",
    )
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={"placeholder": "you@example.com", "autocomplete": "email"}
        ),
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"placeholder": "Create a password", "autocomplete": "new-password"}
        ),
        help_text="At least 8 characters, not entirely numeric and not a common password.",
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"placeholder": "Repeat your password", "autocomplete": "new-password"}
        ),
    )
    terms = forms.BooleanField(
        label="I accept the Terms & Conditions",
        widget=forms.CheckboxInput(),
    )

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        try:
            validate_email(email)
        except forms.ValidationError:
            raise forms.ValidationError("Enter a valid email address.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1")
        try:
            validate_password(password1)
        except forms.ValidationError as exc:
            raise forms.ValidationError(" ".join(exc.messages))
        return password1

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if not cleaned.get("terms"):
            self.add_error("terms", "You must accept the Terms & Conditions to register.")
        return cleaned
