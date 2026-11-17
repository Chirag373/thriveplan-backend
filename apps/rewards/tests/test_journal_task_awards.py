from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.planner.models import Task
from apps.rewards.models import PointTransaction


@override_settings(REWARDS_TIME_ZONE="UTC")
class JournalTaskAwardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(firebase_uid="reward-owner", name="Alex")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        clock = patch("apps.rewards.services.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def entry(self, **fields):
        return self.client.post(
            "/api/v1/journal/entries/", {"thoughts": "Today", **fields}, format="json"
        )

    def task(self):
        return Task.objects.create(owner=self.user, title="Task", date="2026-11-07", time="12:00")

    def update(self, task, **fields):
        return self.client.patch(f"/api/v1/planner/tasks/{task.pk}/", fields, format="json")

    def test_journal_daily_award_edits_deletes_and_client_dates(self):
        first = self.entry(date="2000-01-01T00:00:00Z")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data["points_awarded"], 10)
        self.assertEqual(self.entry().data["points_awarded"], 0)
        url = f"/api/v1/journal/entries/{first.data['id']}/"
        self.assertEqual(
            self.client.patch(url, {"thoughts": "Edit"}, format="json").data["points_awarded"], 0
        )
        self.client.delete(url)
        self.assertEqual(self.entry().data["points_awarded"], 0)
        with patch("apps.rewards.services.timezone.now", return_value=self.now + timedelta(days=1)):
            self.assertEqual(self.entry().data["points_awarded"], 10)
        self.assertEqual(PointTransaction.objects.count(), 2)

    def test_task_retries_reopening_cap_and_next_day(self):
        tasks = [self.task() for _ in range(6)]
        for index, task in enumerate(tasks):
            response = self.update(task, completed=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["points_awarded"], 5 if index < 5 else 0)
        self.assertEqual(self.update(tasks[0], completed=True).data["points_awarded"], 0)
        with patch("apps.rewards.services.timezone.now", return_value=self.now + timedelta(days=1)):
            for task in (tasks[0], tasks[-1]):
                self.update(task, completed=False)
                self.assertEqual(self.update(task, status="Completed").data["points_awarded"], 0)
            self.assertEqual(self.update(self.task(), status="Completed").data["points_awarded"], 5)
        self.assertEqual(PointTransaction.objects.count(), 6)

    def test_task_creation_completed_has_no_reward_and_cannot_be_reopened_for_one(self):
        response = self.client.post(
            "/api/v1/planner/tasks/",
            {
                "title": "Already done",
                "date": "2026-11-07",
                "time": "12:00",
                "completed": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["points_awarded"], 0)
        task = Task.objects.get(pk=response.data["id"])
        self.update(task, completed=False)
        self.assertEqual(self.update(task, completed=True).data["points_awarded"], 0)

    def test_ownership_failed_validation_and_rollback(self):
        other = User.objects.create_user(firebase_uid="other-reward", name="Other")
        task = self.task()
        self.client.force_authenticate(other)
        self.assertEqual(self.update(task, completed=True).status_code, 404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.entry(thoughts="").status_code, 400)
        with (
            patch(
                "apps.rewards.services.PointTransaction.objects.get_or_create",
                side_effect=RuntimeError,
            ),
            self.assertRaises(RuntimeError),
        ):
            self.update(task, completed=True)
        task.refresh_from_db()
        self.assertIsNone(task.first_completed_at)
        self.assertFalse(task.completed)
        self.assertEqual(PointTransaction.objects.count(), 0)

    @override_settings(REWARDS_TIME_ZONE="Asia/Kolkata")
    def test_server_timezone_boundary(self):
        before = datetime(2026, 11, 7, 18, 29, 59, tzinfo=UTC)
        with patch("apps.rewards.services.timezone.now", return_value=before):
            self.assertEqual(self.entry().data["points_awarded"], 10)
        with patch(
            "apps.rewards.services.timezone.now", return_value=before + timedelta(seconds=1)
        ):
            self.assertEqual(self.entry().data["points_awarded"], 10)
