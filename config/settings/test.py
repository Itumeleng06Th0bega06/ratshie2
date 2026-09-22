"""Test settings.

The Django test runner forces DEBUG=False, which makes the compressed
ManifestStaticFilesStorage demand a real collegate staticfiles.json
manifest. Tests that render templates (payments/checkout pages) would then
fail with "Missing staticfiles manifest entry". Use the plain
StaticFilesStorage so template tests are hermetic.
"""
from .base import *  # noqa: F401,F403
from .base import env, BASE_DIR  # noqa: F401

DEBUG = False
ALLOWED_HOSTS = ["testserver", "127.0.0.1"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}