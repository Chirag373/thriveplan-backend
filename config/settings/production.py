import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
    raise ImproperlyConfigured("Firebase Auth emulator must not be enabled in production.")
if not FIREBASE_PROJECT_ID or not ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set FIREBASE_PROJECT_ID and DJANGO_ALLOWED_HOSTS.")
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Production requires PostgreSQL.")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
