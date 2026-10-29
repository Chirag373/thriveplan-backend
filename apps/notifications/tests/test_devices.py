from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.notifications.models import Device


class DeviceTests(TestCase):
    url = "/api/v1/notifications/devices/"

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="device-user", name="Alex")
        self.other = User.objects.create_user(firebase_uid="other", name="Other")
        self.data = {
            "installation_id": str(uuid4()),
            "push_token": "ExpoPushToken[test-token]",
            "platform": "android",
        }
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "device-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def post(self, data=None):
        return self.client.post(self.url, self.data if data is None else data, format="json")

    def test_register_retry_and_token_refresh(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        device_id = response.data["id"]
        self.assertNotIn("push_token", response.data)
        self.assertNotIn("owner", response.data)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(self.post().status_code, 200)
        self.data["push_token"] = "ExponentPushToken[new-token]"
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], device_id)
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(Device.objects.get().push_token, self.data["push_token"])

    def test_multiple_installations(self):
        self.post()
        self.data.update(
            installation_id=str(uuid4()), push_token="ExpoPushToken[second]", platform="ios"
        )
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(Device.objects.filter(owner=self.user).count(), 2)

    def test_foreign_installation_and_token_cannot_be_claimed(self):
        foreign = Device.objects.create(owner=self.other, **self.data)
        self.assertEqual(self.post().status_code, 409)
        self.data["installation_id"] = str(uuid4())
        self.assertEqual(self.post().status_code, 409)
        foreign.refresh_from_db()
        self.assertEqual(foreign.owner, self.other)
        self.assertEqual(Device.objects.count(), 1)

    def test_token_collision_rolls_back_update(self):
        self.post()
        Device.objects.create(
            owner=self.other,
            installation_id=uuid4(),
            push_token="ExpoPushToken[other]",
            platform="ios",
        )
        self.data["push_token"] = "ExpoPushToken[other]"
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(
            Device.objects.get(owner=self.user).push_token, "ExpoPushToken[test-token]"
        )

    def test_delete_only_own_device(self):
        own = self.post().data["id"]
        foreign = Device.objects.create(
            owner=self.other,
            installation_id=uuid4(),
            push_token="ExpoPushToken[other]",
            platform="ios",
        )
        for device_id in [foreign.pk, 99999]:
            self.assertEqual(self.client.delete(f"{self.url}{device_id}/").status_code, 404)
        response = self.client.delete(f"{self.url}{own}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(self.client.delete(f"{self.url}{own}/").status_code, 404)
        self.assertTrue(Device.objects.filter(pk=foreign.pk).exists())

    def test_invalid_payloads(self):
        for changes in [
            {"push_token": "native-fcm-token"},
            {"push_token": "ExpoPushToken[]"},
            {"push_token": "ExpoPushToken[a]\n"},
            {"platform": "web"},
            {"installation_id": "bad"},
            {"owner": self.other.pk},
        ]:
            self.assertEqual(self.post({**self.data, **changes}).status_code, 400)
        self.assertEqual(self.post({}).status_code, 400)
        self.assertFalse(Device.objects.exists())

    def test_authentication_and_disabled_account(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.post().status_code, 401)
        self.assertEqual(self.client.delete(self.url + "1/").status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.post().status_code, 403)

    def test_registration_throttle(self):
        for _ in range(10):
            self.assertIn(self.post().status_code, [200, 201])
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(Device.objects.count(), 1)
