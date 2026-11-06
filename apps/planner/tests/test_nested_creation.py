from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.planner.models import Subtask, Task


class NestedTaskCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(firebase_uid="nested-task-user", name="Alex")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.data = {
            "title": "Prepare presentation",
            "date": "2026-11-06",
            "time": "10:00",
            "subtasks": [{"title": "Research"}, {"title": "Make slides"}],
        }

    def test_subtasks_belong_to_created_task_in_order(self):
        response = self.client.post("/api/v1/planner/tasks/", self.data, format="json")
        self.assertEqual(response.status_code, 201)
        task = Task.objects.get(pk=response.data["id"], owner=self.user)
        self.assertEqual(
            list(task.subtasks.values_list("title", "position")),
            [("Research", 0), ("Make slides", 1)],
        )
        self.assertEqual(len(response.data["subtasks"]), 2)

    def test_invalid_subtask_does_not_create_parent(self):
        self.data["subtasks"] = [{"title": ""}]
        response = self.client.post("/api/v1/planner/tasks/", self.data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Task.objects.exists())

    def test_child_failure_rolls_back_parent(self):
        with (
            patch(
                "apps.planner.services.Subtask.objects.bulk_create",
                side_effect=RuntimeError("failure"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.client.post("/api/v1/planner/tasks/", self.data, format="json")
        self.assertFalse(Task.objects.exists())
        self.assertFalse(Subtask.objects.exists())

    def test_nested_subtasks_cannot_override_parent(self):
        self.data["subtasks"] = [{"title": "Hidden", "task_id": 123}]
        self.assertEqual(
            self.client.post("/api/v1/planner/tasks/", self.data, format="json").status_code, 400
        )
