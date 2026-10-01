"""WSGI entry point for Passenger (cPanel shared hosting).

Passenger imports this module and serves the ``application`` callable using
the virtualenv configured for the application.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('RATSHIE_ENV', 'prod')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.config.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
