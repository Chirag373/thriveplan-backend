from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.planner.models import Reminder, Task


class ReminderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="reminder-user", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.task = Task.objects.create(
            owner=self.user, title="Task", date="2026-10-28", time="09:00"
        )
        self.foreign = Task.objects.create(
            owner=other, title="Private", date="2026-10-28", time="09:00"
        )
        self.url = f"/api/v1/planner/tasks/{self.task.pk}/reminders/"
        self.when = timezone.now() + timedelta(days=1)
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "reminder-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def post(self, when=None):
        return self.client.post(
            self.url, {"scheduled_at": (when or self.when).isoformat()}, format="json"
        )

    def test_schedule_retry_and_ordered_list(self):
        first = self.post()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(Reminder.objects.count(), 1)
        earlier = self.post(self.when - timedelta(hours=1))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.data], [earlier.data["id"], first.data["id"]]
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.task.refresh_from_db()
        self.assertTrue(self.task.reminder)

    def test_cancel_syncs_flag(self):
        first = self.post().data["id"]
        second = self.post(self.when + timedelta(hours=1)).data["id"]
        self.assertEqual(self.client.delete(f"{self.url}{first}/").status_code, 204)
        self.task.refresh_from_db()
        self.assertTrue(self.task.reminder)
        response = self.client.delete(f"{self.url}{second}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.task.refresh_from_db()
        self.assertFalse(self.task.reminder)
        self.assertEqual(self.client.delete(f"{self.url}{second}/").status_code, 404)

    def test_invalid_or_past_time(self):
        for data in [
            {},
            {"scheduled_at": "bad"},
            {"scheduled_at": "2026-10-28T10:00:00"},
            {"scheduled_at": self.when.isoformat(), "task": self.foreign.pk},
        ]:
            self.assertEqual(self.client.post(self.url, data, format="json").status_code, 400)
        self.assertEqual(self.post(timezone.now() - timedelta(minutes=1)).status_code, 400)
        self.assertFalse(Reminder.objects.exists())

    def test_ownership_and_parent_mismatch(self):
        reminder = Reminder.objects.create(task=self.foreign, scheduled_at=self.when)
        for task_id in [self.foreign.pk, 99999]:
            url = f"/api/v1/planner/tasks/{task_id}/reminders/"
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(
                self.client.post(
                    url, {"scheduled_at": self.when.isoformat()}, format="json"
                ).status_code,
                404,
            )
            self.assertEqual(self.client.delete(f"{url}{reminder.pk}/").status_code, 404)
        self.assertEqual(self.client.delete(f"{self.url}{reminder.pk}/").status_code, 404)
        self.assertTrue(Reminder.objects.filter(pk=reminder.pk).exists())

    def test_completion_and_disabling_cancel_schedules(self):
        self.post()
        task_url = f"/api/v1/planner/tasks/{self.task.pk}/"
        self.assertEqual(
            self.client.patch(task_url, {"completed": True}, format="json").status_code, 200
        )
        self.assertFalse(Reminder.objects.exists())
        self.assertEqual(self.post().status_code, 400)
        self.client.patch(task_url, {"completed": False}, format="json")
        self.post()
        self.client.patch(task_url, {"reminder": False}, format="json")
        self.assertFalse(Reminder.objects.exists())

    def test_limit_and_task_deletion(self):
        Reminder.objects.bulk_create(
            [
                Reminder(task=self.task, scheduled_at=self.when + timedelta(minutes=i))
                for i in range(20)
            ]
        )
        self.assertEqual(self.post(self.when + timedelta(hours=1)).status_code, 400)
        self.assertEqual(self.post().status_code, 200)
        self.client.delete(f"/api/v1/planner/tasks/{self.task.pk}/")
        self.assertFalse(Reminder.objects.exists())

    def test_authentication_and_disabled_user(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.post().status_code, 401)
        self.assertEqual(self.client.delete(self.url + "1/").status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.post().status_code, 403)
