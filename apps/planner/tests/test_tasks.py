from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.planner.models import Subtask, Task


class TaskListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="tasks-user", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.task = Task.objects.create(
            owner=self.user, title="My task", date="2026-10-27", time="09:00"
        )
        self.done = Task.objects.create(
            owner=self.user,
            title="Done",
            date="2026-10-28",
            time="13:30",
            status=Task.Status.COMPLETED,
        )
        hidden = Task.objects.create(owner=other, title="Private", date="2026-10-27", time="08:00")
        Subtask.objects.create(task=self.task, title="Own subtask")
        Subtask.objects.create(task=hidden, title="Private subtask")
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "tasks-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def get(self, params=None):
        return self.client.get("/api/v1/planner/tasks/", params or {})

    def test_owner_scope_nested_subtasks_and_bounded_queries(self):
        with self.assertNumQueries(4):
            response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(
            [item["id"] for item in response.data["results"]], [self.task.pk, self.done.pk]
        )
        self.assertEqual(response.data["results"][0]["subtasks"][0]["title"], "Own subtask")
        self.assertEqual(response.data["results"][0]["time"], "9:00 AM")
        self.assertEqual(response.data["results"][1]["time"], "1:30 PM")
        self.assertTrue(response.data["results"][1]["completed"])
        self.assertNotIn("owner", response.data["results"][0])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_filters(self):
        for params, expected in [
            ({"date": "2026-10-27"}, self.task.pk),
            ({"status": "Completed"}, self.done.pk),
            ({"completed": "false"}, self.task.pk),
        ]:
            response = self.get(params)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(response.data["results"][0]["id"], expected)
        self.assertEqual(self.get({"status": "Completed", "completed": "false"}).data["count"], 0)

    def test_pagination(self):
        response = self.get({"page_size": 1})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])
        response = self.get({"page_size": 1, "page": 2})
        self.assertEqual(response.data["results"][0]["id"], self.done.pk)
        self.assertEqual(self.get({"page": 100}).status_code, 404)

    def test_invalid_filters(self):
        for params in [
            {"date": "2026-02-30"},
            {"status": "invalid"},
            {"completed": "invalid"},
            {"page": 0},
            {"page_size": 101},
            {"owner": 2},
        ]:
            self.assertEqual(self.get(params).status_code, 400)
        self.assertEqual(
            self.client.get("/api/v1/planner/tasks/?date=2026-10-27&date=2026-10-28").status_code,
            400,
        )

    def test_empty_results(self):
        Task.objects.filter(owner=self.user).delete()
        self.assertEqual(self.get().data["results"], [])

    def test_unauthorized_and_disabled(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.get().status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.get().status_code, 403)

    def test_put_not_available(self):
        self.assertEqual(
            self.client.put("/api/v1/planner/tasks/", {}, format="json").status_code, 405
        )


class TaskMutationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="writer", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.task = Task.objects.create(
            owner=self.user, title="Original", date="2026-10-27", time="09:00"
        )
        self.other = Task.objects.create(
            owner=other, title="Private", date="2026-10-27", time="09:00"
        )
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "writer"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)
        self.url = f"/api/v1/planner/tasks/{self.task.pk}/"

    def test_create_and_list(self):
        response = self.client.post(
            "/api/v1/planner/tasks/",
            {"title": " New task ", "date": "2026-10-28", "time": "1:30 PM", "reminder": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        task = Task.objects.get(pk=response.data["id"])
        self.assertEqual(task.owner, self.user)
        self.assertEqual(task.title, "New task")
        self.assertEqual(response.data["status"], "Pending")
        self.assertFalse(response.data["completed"])
        self.assertEqual(response.data["subtasks"], [])

    def test_partial_update_preserves_fields(self):
        response = self.client.patch(self.url, {"notes": "Updated", "time": "23:15"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Original")
        self.assertEqual(response.data["time"], "11:15 PM")

    def test_completion_consistency(self):
        response = self.client.patch(self.url, {"completed": True}, format="json")
        self.assertEqual(response.data["status"], "Completed")
        response = self.client.patch(self.url, {"completed": False}, format="json")
        self.assertEqual(response.data["status"], "Pending")
        response = self.client.patch(
            self.url, {"status": "Completed", "completed": False}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "Pending")

    def test_invalid_create_and_patch(self):
        for body in [
            {},
            {"title": " "},
            {"date": "2026-02-30"},
            {"time": "25:00"},
            {"status": "unknown"},
            {"owner": self.user.pk},
            {"subtasks": []},
            {"title": "Changed", "id": 100},
        ]:
            self.assertEqual(self.client.patch(self.url, body, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(
                "/api/v1/planner/tasks/", {"title": "Missing schedule"}, format="json"
            ).status_code,
            400,
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Original")
        self.assertEqual(Task.objects.count(), 2)

    def test_ownership_and_missing_tasks(self):
        for task_id in [self.other.pk, 99999]:
            url = f"/api/v1/planner/tasks/{task_id}/"
            self.assertEqual(
                self.client.patch(url, {"title": "Hack"}, format="json").status_code, 404
            )
            self.assertEqual(self.client.delete(url).status_code, 404)
        self.other.refresh_from_db()
        self.assertEqual(self.other.title, "Private")

    def test_delete_cascades_only_owned_subtasks(self):
        Subtask.objects.create(task=self.task, title="Child")
        Subtask.objects.create(task=self.other, title="Other child")
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertEqual(Subtask.objects.get().task_id, self.other.pk)
        self.assertEqual(self.client.delete(self.url).status_code, 404)

    def test_auth_required_for_all_mutations(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(
            self.client.post("/api/v1/planner/tasks/", {}, format="json").status_code, 401
        )
        self.assertEqual(self.client.patch(self.url, {}, format="json").status_code, 401)
        self.assertEqual(self.client.delete(self.url).status_code, 401)
        self.assertEqual(Task.objects.count(), 2)
