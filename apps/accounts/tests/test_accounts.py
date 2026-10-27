from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from firebase_admin import auth
from rest_framework.test import APIClient

from apps.accounts.models import User, UserPreferences


class SignupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer test-token")
        self.identity = {
            "uid": "firebase-user-1",
            "email": "test@example.com",
            "email_verified": False,
            "firebase": {"sign_in_provider": "password"},
        }
        self.app = patch("apps.accounts.authentication.get_firebase_app", return_value=object())
        self.app.start()
        self.addCleanup(self.app.stop)
        self.verifier = patch(
            "apps.accounts.authentication.auth.verify_id_token", return_value=self.identity
        )
        self.verify = self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def post(self, data=None):
        return self.client.post(
            "/api/v1/accounts/signup/", data or {"name": "Alex Smith"}, format="json"
        )

    def test_creates_user_and_preferences_without_password(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        user = User.objects.get()
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.firebase_uid, self.identity["uid"])
        self.assertFalse(user.email_verified)
        self.assertEqual(UserPreferences.objects.count(), 1)
        self.assertEqual(response.data["next_step"], "preferences")
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("firebase_uid", response.data["user"])
        self.assertTrue(self.verify.call_args.kwargs["check_revoked"])

    def test_retry_does_not_overwrite_profile(self):
        self.post()
        response = self.post({"name": "Different name"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])
        self.assertEqual(User.objects.get().name, "Alex Smith")
        self.assertEqual(UserPreferences.objects.count(), 1)

    def test_completed_onboarding_returns_home(self):
        self.post()
        UserPreferences.objects.update(onboarding_completed=True)
        self.assertEqual(self.post().data["next_step"], "home")

    def test_same_email_never_links_different_uids(self):
        self.post()
        self.identity["uid"] = "other-firebase-uid"
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(User.objects.count(), 2)

    def test_phone_identity(self):
        self.identity.pop("email")
        self.identity["phone_number"] = "+919876543210"
        self.identity["firebase"]["sign_in_provider"] = "phone"
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(User.objects.get().phone_number, "+919876543210")

    def test_missing_and_malformed_authorization(self):
        for header in ["", "Basic test", "Bearer", "Bearer a b"]:
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                response = self.post()
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["WWW-Authenticate"], "Bearer")
        self.verify.assert_not_called()
        self.assertFalse(User.objects.exists())

    def test_invalid_expired_revoked_and_disabled_tokens(self):
        for exception in [
            auth.InvalidIdTokenError,
            auth.ExpiredIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
        ]:
            with self.subTest(exception=exception):
                self.verify.side_effect = (
                    exception("Rejected", cause=None)
                    if exception is auth.ExpiredIdTokenError
                    else exception("Rejected")
                )
                self.assertEqual(self.post().status_code, 401)
        self.assertFalse(User.objects.exists())

    def test_revocation_is_checked_on_every_request_for_same_uid(self):
        self.post()
        self.verify.side_effect = auth.RevokedIdTokenError("Revoked")
        self.assertEqual(self.post().status_code, 401)
        self.assertEqual(self.verify.call_count, 2)

    def test_anonymous_rejected(self):
        self.identity["firebase"]["sign_in_provider"] = "anonymous"
        self.assertEqual(self.post().status_code, 401)
        self.assertFalse(User.objects.exists())

    def test_disabled_local_account_rejected(self):
        self.post()
        User.objects.update(is_active=False)
        self.assertEqual(self.post().status_code, 403)

    def test_invalid_name(self):
        for name in ["", "   ", "a" * 151, None]:
            with self.subTest(name=name):
                self.assertEqual(self.post({"name": name}).status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_missing_name(self):
        response = self.client.post("/api/v1/accounts/signup/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_untrusted_identity_and_password_fields_rejected(self):
        for field in ["email", "firebase_uid", "is_active", "password", "contact", "confirmation"]:
            with self.subTest(field=field):
                self.assertEqual(self.post({"name": "Alex", field: "spoof"}).status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_workflow_failure_rolls_back_user(self):
        with (
            patch("apps.accounts.services.post_user_auth_workflow", side_effect=RuntimeError),
            self.assertRaises(RuntimeError),
        ):
            self.post()
        self.assertFalse(User.objects.exists())

    def test_auth_service_failure(self):
        self.verify.side_effect = auth.CertificateFetchError("Unavailable", cause=None)
        self.assertEqual(self.post().status_code, 503)
        self.assertFalse(User.objects.exists())

    def test_rate_limit(self):
        for _ in range(10):
            self.post()
        response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertEqual(self.verify.call_count, 10)


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer login-token")
        self.user = User.objects.create_user(firebase_uid="uid-1", name="Alex")
        UserPreferences.objects.create(user=self.user)
        self.app = patch("apps.accounts.authentication.get_firebase_app", return_value=object())
        self.app.start()
        self.addCleanup(self.app.stop)
        self.verifier = patch(
            "apps.accounts.authentication.auth.verify_id_token",
            return_value={
                "uid": "uid-1",
                "firebase": {"sign_in_provider": "password"},
            },
        )
        self.verify = self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def post(self, data=None):
        return self.client.post(
            "/api/v1/accounts/login/", {} if data is None else data, format="json"
        )

    def test_login_returns_profile_and_updates_last_login(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], self.user.pk)
        self.assertEqual(response.data["next_step"], "preferences")
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)
        self.assertFalse(self.user.has_usable_password())
        self.assertTrue(self.verify.call_args.kwargs["check_revoked"])
        self.assertNotIn("password", response.data["user"])

    def test_completed_onboarding(self):
        UserPreferences.objects.update(onboarding_completed=True)
        self.assertEqual(self.post().data["next_step"], "home")

    def test_unknown_uid_requires_signup_without_creating_user(self):
        self.verify.return_value = {"uid": "unknown", "email": "alex@example.com"}
        response = self.post()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"].code, "signup_required")
        self.assertEqual(User.objects.count(), 1)

    def test_disabled_user_is_not_logged_in(self):
        User.objects.update(is_active=False)
        self.assertEqual(self.post().status_code, 403)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_login)

    def test_missing_token(self):
        self.client.credentials()
        response = self.post()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")
        self.verify.assert_not_called()

    def test_revoked_token_rejected_even_after_success(self):
        self.post()
        self.user.refresh_from_db()
        previous_login = self.user.last_login
        self.verify.side_effect = auth.RevokedIdTokenError("Revoked")
        self.assertEqual(self.post().status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_login, previous_login)

    def test_invalid_body_and_password_rejected(self):
        for body in [{"password": "secret"}, {"firebase_uid": "other"}, [], "text"]:
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_login)

    def test_missing_preferences_repaired(self):
        UserPreferences.objects.all().delete()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(UserPreferences.objects.count(), 1)

    def test_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(self.verify.call_count, 10)

    def test_firebase_unavailable(self):
        self.verify.side_effect = auth.CertificateFetchError("Unavailable", cause=None)
        self.assertEqual(self.post().status_code, 503)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_login)


@override_settings(FIREBASE_WEB_API_KEY="test-key")
class ForgotPasswordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.sender = patch("apps.common.mail.requests.post")
        self.send = self.sender.start()
        self.addCleanup(self.sender.stop)
        self.send.return_value.status_code = 200

    def post(self, data=None):
        return self.client.post(
            "/api/v1/accounts/forgot-password/",
            {"email": "alex@example.com"} if data is None else data,
            format="json",
        )

    def test_requests_firebase_email_without_auth_or_local_user(self):
        response = self.post({"email": " alex@example.com "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.send.call_args.kwargs["json"],
            {
                "requestType": "PASSWORD_RESET",
                "email": "alex@example.com",
            },
        )
        self.assertEqual(self.send.call_args.kwargs["params"], {"key": "test-key"})
        self.assertFalse(self.send.call_args.kwargs["allow_redirects"])
        self.assertFalse(User.objects.exists())
        self.send.return_value.close.assert_called_once()
        self.assertNotIn("alex@example.com", str(response.data))

    def test_account_specific_errors_have_identical_response(self):
        expected = self.post().data
        for code in ["EMAIL_NOT_FOUND", "USER_DISABLED", "TOO_MANY_ATTEMPTS_TRY_LATER"]:
            self.send.return_value.status_code = 400
            self.send.return_value.json.return_value = {"error": {"message": code}}
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, expected)

    def test_invalid_input_does_not_send_email(self):
        for body in [
            {},
            {"email": "bad"},
            {"email": ""},
            {"email": "a@b.com", "continueUrl": "https://evil.test"},
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)
        self.send.assert_not_called()

    def test_timeout_returns_service_unavailable(self):
        import requests

        self.send.side_effect = requests.Timeout("private upstream data")
        response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", str(response.data))

    def test_upstream_errors_are_sanitized(self):
        for status in [400, 403, 500, 302]:
            self.send.return_value.status_code = status
            self.send.return_value.json.return_value = {"error": {"message": "API_KEY_INVALID"}}
            response = self.post()
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("API_KEY_INVALID", str(response.data))

    def test_malformed_upstream_response(self):
        self.send.return_value.status_code = 500
        self.send.return_value.json.side_effect = ValueError()
        self.assertEqual(self.post().status_code, 503)
        self.send.return_value.close.assert_called_once()

    def test_missing_api_key(self):
        with self.settings(FIREBASE_WEB_API_KEY=""):
            self.assertEqual(self.post().status_code, 503)
        self.send.assert_not_called()

    def test_throttle_prevents_sending_more_emails(self):
        for _ in range(5):
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(self.send.call_count, 5)


class MeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer profile-token")
        self.user = User.objects.create_user(firebase_uid="profile-uid", name="Alex")
        UserPreferences.objects.create(user=self.user)
        self.app = patch("apps.accounts.authentication.get_firebase_app", return_value=object())
        self.app.start()
        self.addCleanup(self.app.stop)
        self.verifier = patch(
            "apps.accounts.authentication.auth.verify_id_token",
            return_value={
                "uid": "profile-uid",
                "firebase": {"sign_in_provider": "password"},
            },
        )
        self.verify = self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def test_returns_own_profile_without_writes(self):
        User.objects.create_user(firebase_uid="other", name="Other")
        with self.assertNumQueries(1):
            response = self.client.get("/api/v1/accounts/me/?user_id=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], self.user.pk)
        self.assertEqual(response.data["next_step"], "preferences")
        self.assertEqual(
            set(response.data["user"]),
            {
                "id",
                "name",
                "email",
                "email_verified",
                "phone_number",
                "onboarding_completed",
            },
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_login)
        self.assertTrue(self.verify.call_args.kwargs["check_revoked"])

    def test_completed_onboarding(self):
        UserPreferences.objects.update(onboarding_completed=True)
        response = self.client.get("/api/v1/accounts/me/")
        self.assertTrue(response.data["user"]["onboarding_completed"])
        self.assertEqual(response.data["next_step"], "home")

    def test_missing_preferences_returns_incomplete_without_creating(self):
        UserPreferences.objects.all().delete()
        response = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["user"]["onboarding_completed"])
        self.assertFalse(UserPreferences.objects.exists())

    def test_missing_token(self):
        self.client.credentials()
        response = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")
        self.verify.assert_not_called()

    def test_revoked_token_rejected_after_success(self):
        self.assertEqual(self.client.get("/api/v1/accounts/me/").status_code, 200)
        self.verify.side_effect = auth.RevokedIdTokenError("Revoked")
        self.assertEqual(self.client.get("/api/v1/accounts/me/").status_code, 401)

    def test_unknown_uid_does_not_create_user(self):
        self.verify.return_value = {"uid": "unknown"}
        self.assertEqual(self.client.get("/api/v1/accounts/me/").status_code, 404)
        self.assertEqual(User.objects.count(), 1)

    def test_disabled_local_user(self):
        User.objects.update(is_active=False)
        self.assertEqual(self.client.get("/api/v1/accounts/me/").status_code, 403)

    def test_write_methods_are_not_enabled(self):
        for method in ["post", "put", "delete"]:
            self.assertEqual(getattr(self.client, method)("/api/v1/accounts/me/").status_code, 405)

    def test_firebase_failure(self):
        self.verify.side_effect = auth.CertificateFetchError("Unavailable", cause=None)
        self.assertEqual(self.client.get("/api/v1/accounts/me/").status_code, 503)


class AccountPatchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer token")
        self.user = User.objects.create_user(firebase_uid="patch-uid", name="Alex")
        self.other = User.objects.create_user(firebase_uid="other-uid", name="Other")
        UserPreferences.objects.create(user=self.user)
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "patch-uid"},
        )
        self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_updates_only_own_name(self):
        response = self.client.patch(
            "/api/v1/accounts/me/?user_id=" + str(self.other.pk),
            {"name": " New name "},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.user.name, "New name")
        self.assertEqual(self.other.name, "Other")
        self.assertIsNone(self.user.last_login)

    def test_invalid_profile_changes_are_atomic(self):
        for body in [
            {},
            {"name": " "},
            {"name": "x" * 151},
            {"name": "Changed", "email": "spoof@example.com"},
            {"is_active": True},
        ]:
            self.assertEqual(
                self.client.patch("/api/v1/accounts/me/", body, format="json").status_code, 400
            )
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Alex")

    def test_partial_preferences_complete_only_when_ready(self):
        url = "/api/v1/accounts/me/preferences/"
        response = self.client.patch(url, {"profession": "student"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["preferences"]["onboarding_completed"])
        response = self.client.patch(url, {"focus_areas": ["planning", "habits"]}, format="json")
        self.assertTrue(response.data["preferences"]["onboarding_completed"])
        self.assertEqual(response.data["preferences"]["profession"], "student")
        self.assertEqual(response.data["next_step"], "home")
        self.assertTrue(
            self.client.get("/api/v1/accounts/me/").data["user"]["onboarding_completed"]
        )
        self.assertFalse(UserPreferences.objects.filter(user=self.other).exists())

    def test_invalid_preferences_do_not_write(self):
        for body in [
            {},
            {"profession": "invalid"},
            {"profession": ""},
            {"focus_areas": []},
            {"focus_areas": ["unknown"]},
            {"focus_areas": ["planning", "planning"]},
            {"profession": "student", "onboarding_completed": True},
            {"focus_areas": None},
        ]:
            self.assertEqual(
                self.client.patch(
                    "/api/v1/accounts/me/preferences/", body, format="json"
                ).status_code,
                400,
            )
        preferences = UserPreferences.objects.get(user=self.user)
        self.assertEqual(preferences.profession, "")
        self.assertFalse(preferences.onboarding_completed)

    def test_missing_preferences_can_be_created(self):
        UserPreferences.objects.all().delete()
        response = self.client.patch(
            "/api/v1/accounts/me/preferences/",
            {"profession": "personal", "focus_areas": ["mindfulness"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["preferences"]["onboarding_completed"])
        self.assertEqual(UserPreferences.objects.count(), 1)

    def test_disabled_user_cannot_patch(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        for url, body in [
            ("/api/v1/accounts/me/", {"name": "Changed"}),
            ("/api/v1/accounts/me/preferences/", {"profession": "student"}),
        ]:
            self.assertEqual(self.client.patch(url, body, format="json").status_code, 403)

    def test_invalid_token_cannot_patch(self):
        from rest_framework.exceptions import AuthenticationFailed

        with patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            side_effect=AuthenticationFailed(),
        ):
            for url in ["/api/v1/accounts/me/", "/api/v1/accounts/me/preferences/"]:
                self.assertEqual(self.client.patch(url, {}, format="json").status_code, 401)
