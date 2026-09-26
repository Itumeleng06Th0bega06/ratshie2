"""
Base Django settings for the Ratshie (Pty) Ltd premium automotive website.

Environment-managed configuration. Never commit real secrets.
"""
from pathlib import Path
import os
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, []),
    DATABASE_URL=(str, ""),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
# Load the environment file (never committed to version control).
# Local/development uses .env; production (RATSHIE_ENV=prod) uses .env.prod so
# live credentials never leak into the local/dev environment.
if os.environ.get("RATSHIE_ENV", "").lower() == "prod":
    environ.Env.read_env(os.path.join(BASE_DIR, ".env.prod"))
else:
    environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DEBUG", default=True if os.environ.get("RATSHIE_ENV") != "prod" else False)

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "django_htmx",
]

LOCAL_APPS = [
    "core",
    "services",
    "products",
    "quotes",
    "bookings",
    "orders",
    "payments",
    "customers",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_globals",
                "core.context_processors.admin_command_bar",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# Universal database URL takes precedence (e.g. PostgreSQL via dj-database-url).
try:
    import dj_database_url

    _db_url = env("DATABASE_URL", default="")
    if _db_url:
        DATABASES["default"] = dj_database_url.parse(_db_url)
        # Default safety: keep transactional DB checks in production
        DATABASES["default"]["CONN_MAX_AGE"] = 60
except ImportError:  # pragma: no cover
    pass

# MariaDB / MySQL (cPanel): when DB_USER is set, use Django's MySQL backend.
# Credentials come from environment variables / the environment file. PyMySQL
# (pure Python) is used as the MySQLdb driver - no native build required.
_db_user = env("DB_USER", default="")
if not env("DATABASE_URL", default="") and _db_user:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", default="ratshiec_ratshie_db"),
        "USER": _db_user,
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="3306"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"charset": "utf8mb4"},
    }

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-za"
TIME_ZONE = "Africa/Johannesburg"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "customers:login"
LOGIN_REDIRECT_URL = "customers:account"

# ---------------------------------------------------------------------------
# Business settings (configurable; override via .env for production)
# ---------------------------------------------------------------------------
SITE_NAME = "Ratshie (Pty) Ltd"
SITE_TAGLINE = "Vehicle repairs, diagnostics & mobile spares delivery in the Northern Cape"

# Contact details - sourced from the official business summary
BUSINESS_PHONE = env("BUSINESS_PHONE", default="+27614884254")
BUSINESS_PHONE_DISPLAY = env("BUSINESS_PHONE_DISPLAY", default="061 488 4254")
BUSINESS_EMAIL = env("BUSINESS_EMAIL", default="admin@ratshie.co.za")
WHATSAPP_NUMBER = env("WHATSAPP_NUMBER", default="27659017566")
WHATSAPP_DISPLAY = env("WHATSAPP_DISPLAY", default="065 901 7566")
CONTACT_NAME = env("CONTACT_NAME", default="Livhuwani")
BUSINESS_ADDRESS = env(
    "BUSINESS_ADDRESS", default="Seoding Village, Kuruman, Northern Cape, South Africa"
)
SERVICE_RADIUS_KM = env("SERVICE_RADIUS_KM", default=50)

# Google Maps Embed API key (optional). When empty, the contact page shows a
# keyless "Get Directions" link instead of the map embed (no fake keys shipped).
GOOGLE_MAPS_API_KEY = env("GOOGLE_MAPS_API_KEY", default="")

# Cart behaviour: quote/enquiry-based purchasing by default. Set ENABLE_CART=False
# to disable direct cart entirely, or configure real product prices to enable checkout.
ENABLE_CART = env.bool("ENABLE_CART", default=True)

# ---------------------------------------------------------------------------
# PayFast (sandbox by default - configure for production with real credentials)
# ---------------------------------------------------------------------------
PAYFAST_MERCHANT_ID = env("PAYFAST_MERCHANT_ID", default="")
PAYFAST_MERCHANT_KEY = env("PAYFAST_MERCHANT_KEY", default="")
PAYFAST_PASSPHRASE = env("PAYFAST_PASSPHRASE", default="")
PAYFAST_SANDBOX = env.bool("PAYFAST_SANDBOX", default=True)
PAYFAST_RETURN_URL_PREFIX = env(
    "PAYFAST_RETURN_URL_PREFIX", default="http://127.0.0.1:8000"
)

# PayFast is only considered enabled (blongs to a real merchant) once credentials
# are supplied via environment variables. The payment UI stays visible either way;
# only the actual payment submission is gated on this flag.
PAYFAST_ENABLED = bool(PAYFAST_MERCHANT_ID and PAYFAST_MERCHANT_KEY)
# Human friendly environment label shown where configuration details are surfaced.
PAYFAST_MODE = "sandbox" if PAYFAST_SANDBOX else "live"

# ---------------------------------------------------------------------------
# Email (cPanel SMTP on ratshie.co.za - credentials via .env, never committed)
# ---------------------------------------------------------------------------
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=BUSINESS_EMAIL)
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="ratshie.co.za")
EMAIL_PORT = env.int("EMAIL_PORT", default=465)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default=BUSINESS_EMAIL)
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
# Used purely for the test-send notification to the site owner, not customers.
ADMIN_EMAIL = env("ADMIN_EMAIL", default=BUSINESS_EMAIL)

# ---------------------------------------------------------------------------
# SMS (configurable provider; credentials via .env, never committed)
# ---------------------------------------------------------------------------
SMS_API_URL = env("SMS_API_URL", default="")
SMS_API_KEY = env("SMS_API_KEY", default="")
SMS_SENDER = env("SMS_SENDER", default="")
