"""Production settings.

Enable with:  RATSHIE_ENV=prod  (read from the OS environment, e.g. set inside cPanel's
Python App environment, NOT from the .env file).

Fails fast if a weak SECRET_KEY is present - running production with a
placeholder key is a security incident waiting to happen.
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env, BASE_DIR  # noqa: F401

DEBUG = False
SECRET_KEY = env("SECRET_KEY", default="")
if not SECRET_KEY or "change-me" in SECRET_KEY or len(SECRET_KEY) < 50:
    secret_related = [
        key for key in os.environ if "SECRET" in key.upper() or key.upper() == "RATSHIE_ENV"
    ]
    raise ValueError(
        "Production requires a strong SECRET_KEY (>=50 chars, no 'change-me'). "
        f"Received length={len(SECRET_KEY)}. "
        f"Relevant process env keys present: {secret_related}. "
        f"(.env.prod exists on disk: {os.path.exists(os.path.join(BASE_DIR, '.env.prod'))}). "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )

ALLOWED_HOSTS = env("ALLOWED_HOSTS", default=["ratshie.co.za", "www.ratshie.co.za"])
CSRF_TRUSTED_ORIGINS = env(
    "CSRF_TRUSTED_ORIGINS",
    default=["https://ratshie.co.za", "https://www.ratshie.co.za"],
)

# Production must never silently run on SQLite. base.py selects MySQL only when
# DB_USER is set; if it isn't, fail loudly instead of scattering migrations into
# db.sqlite3 while the live app keeps hitting an empty MariaDB.
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    raise ImproperlyConfigured(
        "Production cannot run on SQLite. Set DB_USER / DB_PASSWORD / DB_NAME "
        "(via .env.prod or the cPanel app env) so the MySQL/MariaDB backend is selected."
    )

# Security hardening
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = env.bool("CSRF_COOKIE_HTTPONLY", default=True)
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# Terminate SSL at the proxy / cPanel so Django can trust the forwarded scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Log to a file on the server (logs/ folder, gitignored) instead of stdout.
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "django.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler",
            "level": "ERROR",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["file", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["file", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# Django error emails go to the site admin mailbox when a 500 occurs.
ADMINS = [("Ratshie Admin", env("ADMIN_EMAIL", default="admin@ratshie.co.za"))]
SERVER_EMAIL = env("SERVER_EMAIL", default="admin@ratshie.co.za")

# SQLite is only suitable for local dev / low traffic. Production should use
# PostgreSQL via DATABASE_URL (see base.py). Nothing to do here otherwise.