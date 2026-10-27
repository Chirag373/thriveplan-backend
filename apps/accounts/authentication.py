"""Firebase identity verification and authentication for protected API endpoints."""

import logging
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from firebase_admin import auth, exceptions
from google.auth.exceptions import GoogleAuthError
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied
from rest_framework.request import Request

from .firebase import get_firebase_app
from .models import User

logger = logging.getLogger(__name__)

MAX_TOKEN_BYTES = 16_384


class AuthenticationUnavailable(APIException):
    status_code = 503
    default_detail = "Authentication is temporarily unavailable."
    default_code = "authentication_unavailable"


class FirebaseProvider:
    """Verify Firebase identity before running an account workflow."""

    def __init__(self, request: Request) -> None:
        self.request = request

    def authenticate(self) -> dict[str, Any]:
        token = _get_bearer_token(self.request)
        identity = _verify_token(token)
        if (
            not identity.get("uid")
            or identity.get("firebase", {}).get("sign_in_provider") == "anonymous"
        ):
            raise AuthenticationFailed("A non-anonymous Firebase account is required.")
        return identity


class FirebaseAuthentication(BaseAuthentication):
    """Resolve an active local user without creating or modifying account records."""

    def authenticate(self, request: Request) -> tuple[User, dict[str, Any]]:
        identity = FirebaseProvider(request=request).authenticate()
        user = _get_active_user(identity["uid"])
        return user, identity

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"


def _get_bearer_token(request: Request) -> str:
    parts = get_authorization_header(request).split()
    if len(parts) != 2 or parts[0].lower() != b"bearer":
        raise AuthenticationFailed("A Firebase Bearer ID token is required.")
    if len(parts[1]) > MAX_TOKEN_BYTES:
        raise AuthenticationFailed("Invalid Firebase ID token.")
    try:
        return parts[1].decode("ascii")
    except UnicodeDecodeError:
        raise AuthenticationFailed("Invalid Firebase ID token.") from None


def _verify_token(token: str) -> dict[str, Any]:
    try:
        app = get_firebase_app()
    except (ImproperlyConfigured, GoogleAuthError, ValueError, OSError):
        logger.error("Firebase initialization failed; check server configuration.")
        raise AuthenticationUnavailable() from None

    try:
        # Revocation must be checked for each token, never cached by user ID.
        return auth.verify_id_token(token, app=app, check_revoked=True)
    except auth.CertificateFetchError:
        # Certificate retrieval is a service failure, not an invalid credential.
        raise AuthenticationUnavailable() from None
    except (
        auth.InvalidIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
        ValueError,
    ):
        raise AuthenticationFailed("Invalid, expired, or revoked Firebase ID token.") from None
    except (exceptions.FirebaseError, GoogleAuthError):
        raise AuthenticationUnavailable() from None


def _get_active_user(uid: str) -> User:
    try:
        user = User.objects.select_related("preferences").get(firebase_uid=uid)
    except User.DoesNotExist:
        raise NotFound(
            "Complete signup before accessing your profile.", code="signup_required"
        ) from None
    if not user.is_active:
        raise PermissionDenied("This account has been deactivated.")
    return user
