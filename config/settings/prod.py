"""Production settings.

Enable with:  RATSHIE_ENV=prod  (or set DJANGO_SETTINGS_MODULE).
"""
from .base import *  # noqa: F401,F403
from .base import env  # noqa: F401

DEBUG = False
ALLOWED_HOSTS = env("ALLOWED_HOSTS", default=["*"])
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS", default=["https://example.com"])

# Security hardening
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
