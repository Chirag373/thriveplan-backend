from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User, UserPreferences


class NotificationPreferencesTests(TestCase):
    url = "/api/v1/accounts/me/notification-preferences/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="preferences-user", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.other_preferences = UserPreferences.objects.create(user=other)
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "preferences-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_get_defaults_without_writes(self):
        with self.assertNumQueries(1):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"daily_reminders": True, "weekly_summary": False})
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertFalse(UserPreferences.objects.filter(user=self.user).exists())

    def test_patch_persists_and_preserves_omitted_fields(self):
        response = self.client.patch(self.url, {"daily_reminders": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"daily_reminders": False, "weekly_summary": False})
        response = self.client.patch(self.url, {"weekly_summary": True}, format="json")
        self.assertEqual(response.data, {"daily_reminders": False, "weekly_summary": True})
        self.assertEqual(self.client.get(self.url).data, response.data)
        self.other_preferences.refresh_from_db()
        self.assertTrue(self.other_preferences.daily_reminders)
        self.assertFalse(self.other_preferences.weekly_summary)

    def test_onboarding_untouched(self):
        preferences = UserPreferences.objects.create(
            user=self.user,
            profession="student",
            focus_areas=["planning"],
            onboarding_completed=True,
        )
        self.client.patch(self.url, {"daily_reminders": False}, format="json")
        preferences.refresh_from_db()
        self.assertTrue(preferences.onboarding_completed)
        self.assertEqual(preferences.profession, "student")
        self.assertEqual(preferences.focus_areas, ["planning"])

    def test_invalid_input_creates_nothing(self):
        for data in [
            {},
            {"daily_reminders": None},
            {"weekly_summary": "invalid"},
            {"daily_reminders": False, "owner": self.other_preferences.user_id},
            {"onboarding_completed": True},
        ]:
            self.assertEqual(self.client.patch(self.url, data, format="json").status_code, 400)
        self.assertFalse(UserPreferences.objects.filter(user=self.user).exists())

    def test_authentication_and_disabled_user(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(
            self.client.patch(self.url, {"weekly_summary": True}, format="json").status_code, 401
        )
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.patch(self.url, {"weekly_summary": True}, format="json").status_code, 403
        )

    def test_other_methods_not_enabled(self):
        for method in ["post", "put", "delete"]:
            self.assertEqual(
                getattr(self.client, method)(self.url, {}, format="json").status_code, 405
            )
