import os

os.environ.setdefault("DJANGO_SECRET_KEY", "local-development-only-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite:///db.sqlite3")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

os.environ.setdefault("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

from .base import *

DEBUG = True
