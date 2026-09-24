"""Passenger WSGI entry point for cPanel Python App deployment.

cPanel's "Setup Python App" points at this file. It must live at the
application root next to manage.py.
Required: Python 3.13.7 (see .python-version) and RATSHIE_ENV=prod set in
the application's environment variables (cPanel GUI -> Setup Python App).
"""
import os
import sys
from pathlib import Path

# Ensure the project root is importable regardless of the invoked CWD.
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# config.wsgi.application is what Passenger serves.
from config.wsgi import application as app  # noqa: E402