from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import User, UserPreferences


def post_user_auth_workflow(*, user):
    UserPreferences.objects.get_or_create(user=user)


@transaction.atomic
def signup_user(*, identity, name):
    # The unique UID constraint makes get_or_create safe against concurrent retries.
    user, created = User.objects.get_or_create(
        firebase_uid=identity["uid"],
        defaults={
            "name": name,
            "email": identity.get("email", ""),
            "email_verified": identity.get("email_verified", False),
            "phone_number": identity.get("phone_number", ""),
        },
    )
    if not user.is_active:
        raise PermissionDenied("This account has been deactivated.")
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    post_user_auth_workflow(user=user)
    return user, created


class SignupRequired(NotFound):
    default_detail = "Complete signup before logging in."
    default_code = "signup_required"


@transaction.atomic
def login_user(*, identity):
    try:
        user = User.objects.select_for_update().get(firebase_uid=identity["uid"])
    except User.DoesNotExist:
        raise SignupRequired() from None
    if not user.is_active:
        raise PermissionDenied("This account has been deactivated.")
    post_user_auth_workflow(user=user)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    return user


@transaction.atomic
def update_profile(*, user, changes):
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active:
        raise PermissionDenied("This account has been deactivated.")
    user.name = changes["name"]
    user.save(update_fields=["name", "updated_at"])
    return user


@transaction.atomic
def update_preferences(*, user, changes):
    # Serialize updates on the user row even if preferences do not yet exist.
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active:
        raise PermissionDenied("This account has been deactivated.")
    preferences, _ = UserPreferences.objects.get_or_create(user=user)
    for field, value in changes.items():
        setattr(preferences, field, value)
    preferences.onboarding_completed = bool(
        user.name and preferences.profession and preferences.focus_areas
    )
    preferences.save(update_fields=[*changes, "onboarding_completed"])
    return preferences


def get_notification_preferences(*, user):
    # Return defaults for legacy accounts without creating records during GET.
    return getattr(user, "preferences", None) or UserPreferences(user=user)


@transaction.atomic
def update_notification_preferences(*, user, changes):
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_active:
        raise PermissionDenied("This account has been deactivated.")
    preferences, _ = UserPreferences.objects.get_or_create(user=user)
    for field, value in changes.items():
        setattr(preferences, field, value)
    preferences.save(update_fields=list(changes))
    return preferences
