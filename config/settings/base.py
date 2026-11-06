from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "apps.accounts",
    "apps.planner",
    "apps.journal",
    "apps.wellness",
    "apps.notifications",
    "apps.rewards",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": env.db("DATABASE_URL")}
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
FIREBASE_PROJECT_ID = env("FIREBASE_PROJECT_ID", default="")
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {
        "signup": "10/min",
        "login": "10/min",
        "forgot_password": "5/min",
        "device_registration": "10/min",
        "journal_transcription": "5/min",
    },
    "NUM_PROXIES": 0,
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536

FIREBASE_WEB_API_KEY = env("FIREBASE_WEB_API_KEY", default="")

# Shared transactional email configuration; Firebase manages reset-email delivery separately.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="webmaster@localhost")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)

# Local speech recognition is opt-in; models must already be provisioned on the server.
WHISPER_ENABLED = env.bool("WHISPER_ENABLED", default=False)
WHISPER_MODEL = env("WHISPER_MODEL", default="base")
WHISPER_DEVICE = env("WHISPER_DEVICE", default="cpu")
WHISPER_COMPUTE_TYPE = env("WHISPER_COMPUTE_TYPE", default="int8")
WHISPER_CPU_THREADS = env.int("WHISPER_CPU_THREADS", default=2)
WHISPER_MAX_UPLOAD_BYTES = env.int("WHISPER_MAX_UPLOAD_BYTES", default=10 * 1024 * 1024)
WHISPER_MAX_SECONDS = env.int("WHISPER_MAX_SECONDS", default=300)
