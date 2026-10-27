from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.planner.models import Subtask, Task


class SubtaskTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="subtask-user", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.task = Task.objects.create(
            owner=self.user, title="Task", date="2026-10-27", time="09:00"
        )
        self.other_task = Task.objects.create(
            owner=other, title="Private", date="2026-10-27", time="09:00"
        )
        self.subtask = Subtask.objects.create(task=self.task, title="Original")
        self.foreign = Subtask.objects.create(task=self.other_task, title="Private child")
        self.base = f"/api/v1/planner/tasks/{self.task.pk}/subtasks/"
        self.detail = f"{self.base}{self.subtask.pk}/"
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "subtask-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_create_appends_and_is_visible_in_task_list(self):
        response = self.client.post(self.base, {"title": " New child "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "New child")
        self.assertFalse(response.data["completed"])
        self.assertEqual(Subtask.objects.get(pk=response.data["id"]).position, 1)
        tasks = self.client.get("/api/v1/planner/tasks/").data["results"]
        self.assertEqual([s["title"] for s in tasks[0]["subtasks"]], ["Original", "New child"])

    def test_patch_preserves_omitted_fields_and_parent_status(self):
        response = self.client.patch(self.detail, {"completed": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Original")
        self.assertTrue(response.data["completed"])
        response = self.client.patch(self.detail, {"title": "Renamed"}, format="json")
        self.assertTrue(response.data["completed"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_delete_does_not_delete_parent_or_other_subtasks(self):
        response = self.client.delete(self.detail)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())
        self.assertTrue(Subtask.objects.filter(pk=self.foreign.pk).exists())
        self.assertEqual(self.client.delete(self.detail).status_code, 404)

    def test_invalid_payloads_never_write(self):
        for data in [
            {},
            {"title": " "},
            {"title": "a" * 256},
            {"completed": None},
            {"title": "Changed", "task": self.other_task.pk},
            {"position": 100},
        ]:
            self.assertEqual(self.client.patch(self.detail, data, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(self.base, {"completed": True}, format="json").status_code, 400
        )
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.title, "Original")
        self.assertEqual(Subtask.objects.count(), 2)

    def test_foreign_or_missing_parent(self):
        for parent in [self.other_task.pk, 99999]:
            base = f"/api/v1/planner/tasks/{parent}/subtasks/"
            self.assertEqual(
                self.client.post(base, {"title": "New"}, format="json").status_code, 404
            )
            self.assertEqual(
                self.client.patch(
                    f"{base}{self.foreign.pk}/", {"completed": True}, format="json"
                ).status_code,
                404,
            )
            self.assertEqual(self.client.delete(f"{base}{self.foreign.pk}/").status_code, 404)

    def test_mismatched_parent_even_for_same_owner(self):
        second = Task.objects.create(
            owner=self.user, title="Second", date="2026-10-27", time="10:00"
        )
        child = Subtask.objects.create(task=second, title="Second child")
        for child_id in [child.pk, self.foreign.pk, 99999]:
            url = f"{self.base}{child_id}/"
            self.assertEqual(
                self.client.patch(url, {"title": "Hack"}, format="json").status_code, 404
            )
            self.assertEqual(self.client.delete(url).status_code, 404)

    def test_authentication_and_disabled_account(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(
            self.client.post(self.base, {"title": "New"}, format="json").status_code, 401
        )
        self.assertEqual(
            self.client.patch(self.detail, {"completed": True}, format="json").status_code, 401
        )
        self.assertEqual(self.client.delete(self.detail).status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.delete(self.detail).status_code, 403)
        self.assertTrue(Subtask.objects.filter(pk=self.subtask.pk).exists())
