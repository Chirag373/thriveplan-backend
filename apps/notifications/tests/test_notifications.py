from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.notifications.models import Notification


class NotificationTests(TestCase):
    url = "/api/v1/notifications/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="notification-user", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.first = Notification.objects.create(
            owner=self.user,
            title="Task",
            message="Message",
            category="Tasks",
            icon="task",
            destination="task",
        )
        self.second = Notification.objects.create(
            owner=self.user,
            title="Breathe",
            message="Message",
            category="Mindfulness",
            icon="leaves",
            destination="mindfulness",
        )
        self.foreign = Notification.objects.create(
            owner=other,
            title="Private",
            message="Private",
            category="System",
            icon="star",
            destination="rewards",
        )
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "notification-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_list_owned_paginated_and_filtered(self):
        response = self.client.get(self.url, {"page_size": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["id"], self.second.pk)
        self.assertIsNotNone(response.data["next"])
        response = self.client.get(self.url, {"category": "Tasks"})
        self.assertEqual(response.data["count"], 1)
        self.assertTrue(response.data["results"][0]["unread"])
        self.assertNotIn("owner", response.data["results"][0])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_mark_read_preserves_first_timestamp(self):
        url = f"{self.url}{self.first.pk}/"
        response = self.client.patch(url, {"unread": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["unread"])
        timestamp = response.data["read_at"]
        self.assertIsNotNone(timestamp)
        self.assertEqual(
            self.client.patch(url, {"unread": False}, format="json").data["read_at"], timestamp
        )
        self.assertEqual(self.client.get(self.url, {"unread": "false"}).data["count"], 1)
        self.assertEqual(self.client.get(self.url, {"unread": "true"}).data["count"], 1)

    def test_read_all_is_owned_and_repeat_safe(self):
        response = self.client.post(self.url + "read-all/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated"], 2)
        self.assertEqual(
            self.client.post(self.url + "read-all/", {}, format="json").data["updated"], 0
        )
        self.foreign.refresh_from_db()
        self.assertIsNone(self.foreign.read_at)

    def test_foreign_and_missing_return_404(self):
        for notification_id in [self.foreign.pk, 99999]:
            self.assertEqual(
                self.client.patch(
                    f"{self.url}{notification_id}/", {"unread": False}, format="json"
                ).status_code,
                404,
            )

    def test_invalid_payloads_and_filters(self):
        for data in [
            {},
            {"unread": True},
            {"unread": False, "title": "Changed"},
            {"read_at": "2026-10-28T00:00:00Z"},
        ]:
            self.assertEqual(
                self.client.patch(f"{self.url}{self.first.pk}/", data, format="json").status_code,
                400,
            )
        self.assertEqual(
            self.client.post(self.url + "read-all/", {"owner": 2}, format="json").status_code, 400
        )
        for query in [
            {"category": "invalid"},
            {"page": 0},
            {"page_size": 101},
            {"unread": "invalid"},
            {"owner": 2},
        ]:
            self.assertEqual(self.client.get(self.url, query).status_code, 400)
        self.assertEqual(self.client.get(self.url + "?unread=true&unread=false").status_code, 400)
        self.first.refresh_from_db()
        self.assertIsNone(self.first.read_at)

    def test_authentication_disabled_user_and_no_public_creation(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(
            self.client.patch(
                f"{self.url}{self.first.pk}/", {"unread": False}, format="json"
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(self.url + "read-all/", {}, format="json").status_code, 401
        )
        self.verify.side_effect = None
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 403)
