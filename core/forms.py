"""Forms for the Ratshie application.

This module currently holds a single hardened authentication form used by the
Django admin login. The idea is a lightweight, dependency-free "honeypot":
authentic humans never see or fill the extra field we add, but naive bots that
blindly autofill every input almost always do. When a bot trips the trap we
silently refuse the login, ease nothing back, raise a bell notification so the
owner knows a scanner found the admin, and apply a short per-IP cooldown.
"""
from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.cache import cache
from django.utils.translation import gettext as _

from .models import Notification

# Honeypot tuning (cache lives in-process: LocMem in dev, memcacheable later).
HONEYPOT_FIELD = "website"            # dotted generic label bots happily fill
HONEYPOT_MAX_HITS = 3                 # hits allowed before a cooldown kicks in
HONEYPOT_WINDOW_SECONDS = 60 * 10     # remember hits for 10 minutes
HONEYPOT_COOLDOWN_SECONDS = 60 * 30   # block a flagged IP for 30 minutes
HONEYPOT_BELL_KEY_PREFIX = "security:admin-honeypot:"
_HONEYPOT_CACHE_PREFIX = "honeypot:admin:"


def cache_hits_key(remote_addr):
    return f"{_HONEYPOT_CACHE_PREFIX}hits:{remote_addr}"


def cache_cooldown_key(remote_addr):
    return f"{_HONEYPOT_CACHE_PREFIX}cooldown:{remote_addr}"


def _client_ip(request):
    """Best-effort client IP, honouring the same proxy header that runs prod."""
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    return ip or request.META.get("REMOTE_ADDR", "unknown")


class HoneypottedAdminAuthenticationForm(AdminAuthenticationForm):
    """AdminAuthenticationForm with a hidden honeypot + per-IP cooldown.

    - The honeypot is a normal-looking text field rendered with
      ``display:none`` so humans never see it but autofilling bots fill it.
    - When the honeypot is tripped: refuse with a message identical to a real
      login failure (no hints), raise a persistent bell card, and start a
      short per-IP cooldown after repeated hits. A legit login success clears
      the tally, so the site owner is never locked out.
    """

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields[HONEYPOT_FIELD] = forms.CharField(
            label="", required=False,
            widget=forms.TextInput(
                attrs={
                    "autocomplete": "off",
                    "tabindex": "-1",
                    "aria-hidden": "true",
                    "style": "position:absolute;left:-9999px;width:1px;height:1px;opacity:0;",
                }
            ),
        )

    def clean(self):
        """Reject honeypot bots; otherwise delegate to Django's normal auth."""
        remote_addr = _client_ip(self.request)
        website = self.cleaned_data.get(HONEYPOT_FIELD)

        if website:
            self._on_honeypot_tripped(remote_addr, website)
            # Same wording as Django's real failure so bots learn nothing here.
            raise forms.ValidationError(
                _("Please enter the correct username and password for a staff account."),
                code="invalid_login",
            )

        # A genuine human (or a right-behaving bot) got through: clear the tally.
        if remote_addr != "unknown":
            cache.delete(cache_hits_key(remote_addr))
            cache.delete(cache_cooldown_key(remote_addr))

        return super().clean()

    def _on_honeypot_tripped(self, remote_addr, website):
        """Record the hit, surface a bell card ceremony, then decide the cooldown."""
        hit_key = cache_hits_key(remote_addr)
        hits = (cache.get(hit_key) or 0) + 1
        cache.set(hit_key, hits, HONEYPOT_WINDOW_SECONDS)

        # Break the mobile-owner lock-in risk: a cooldown only applies to /this/
        # flagged IP, and a successful real login above always clears it.
        if hits >= HONEYPOT_MAX_HITS:
            cache.set(cache_cooldown_key(remote_addr), True, HONEYPOT_COOLDOWN_SECONDS)

        # Raise a persistent bell card (never pruned: only order/image/enquiry
        # prefixes are cleaned by the bell reconcile).
        title = "BOT detected on admin login"
        text = f'Admin honeypot triggered from {remote_addr or "unknown"}.'
        Notification.objects.update_or_create(
            key=f"{HONEYPOT_BELL_KEY_PREFIX}{remote_addr}",
            defaults={
                "title": title,
                "text": text[:300],
                "level": "error",
                "url": "/admin/",
                "is_read": False,
            },
        )
