from threading import Lock

import firebase_admin
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_app_lock = Lock()


def get_firebase_app():
    if not settings.FIREBASE_PROJECT_ID:
        raise ImproperlyConfigured("FIREBASE_PROJECT_ID is required.")
    # A named app avoids silently reusing another Firebase project's default app.
    with _app_lock:
        try:
            return firebase_admin.get_app("thriveplan")
        except ValueError:
            return firebase_admin.initialize_app(
                options={"projectId": settings.FIREBASE_PROJECT_ID}, name="thriveplan"
            )
