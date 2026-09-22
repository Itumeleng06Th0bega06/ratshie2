"""Development settings."""
from .base import *  # noqa: F401,F403
from .base import env, BASE_DIR  # noqa: F401

DEBUG = True
ALLOWED_HOSTS = env("ALLOWED_HOSTS", default=["*"])

INSTALLED_APPS += ["django_extensions"] if False else []  # keep light

# Simplest reliable SQLite by default for local dev.
# To switch to PostgreSQL locally set DATABASE_URL in .env
