from datetime import UTC, datetime
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.planner.models import Task


class ProductivityTests(TestCase):
    url = "/api/v1/insights/productivity/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="productivity-user", name="Alex")
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "productivity-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def get(self, **query):
        return self.client.get(
            self.url, {"start_date": "2026-10-26", "end_date": "2026-10-28", **query}
        )

    def task(self, day, status, owner=None):
        return Task.objects.create(
            owner=owner or self.user, title="Task", date=day, time="09:00", status=status
        )

    def test_daily_counts_zero_fill_and_weighted_percentage(self):
        self.task("2026-10-26", "Completed")
        for status in ["Completed", "Pending", "Overdue", "In Progress"]:
            self.task("2026-10-28", status)
        self.task("2026-10-29", "Completed")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.task("2026-10-26", "Completed", other)
        with self.assertNumQueries(2):
            response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["summary"],
            {"total": 5, "completed": 2, "pending": 3, "completion_percentage": 40.0},
        )
        self.assertEqual(
            [day["date"] for day in response.data["days"]],
            ["2026-10-26", "2026-10-27", "2026-10-28"],
        )
        self.assertEqual(response.data["days"][1]["total"], 0)
        self.assertEqual(response.data["days"][1]["completion_percentage"], 0.0)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_default_seven_local_days(self):
        with patch(
            "apps.insights.serializers.timezone.now",
            return_value=datetime(2026, 10, 27, 20, tzinfo=UTC),
        ):
            response = self.client.get(self.url, {"timezone": "Asia/Kolkata"})
        self.assertEqual(response.data["start_date"], "2026-10-22")
        self.assertEqual(response.data["end_date"], "2026-10-28")
        self.assertEqual(len(response.data["days"]), 7)
        self.assertEqual(response.data["summary"]["total"], 0)

    def test_current_status_is_used(self):
        task = self.task("2026-10-26", "Completed")
        self.assertEqual(self.get().data["summary"]["completed"], 1)
        task.status = "Pending"
        task.save()
        self.assertEqual(self.get().data["summary"]["completed"], 0)

    def test_invalid_filters_and_range_limit(self):
        for query in [
            {"start_date": "2026-10-28"},
            {"timezone": "invalid"},
            {"start_date": "2026-10-29", "end_date": "2026-10-28"},
            {"start_date": "2025-01-01", "end_date": "2026-01-02"},
            {"owner": 1},
        ]:
            self.assertEqual(self.client.get(self.url, query).status_code, 400)
        self.assertEqual(self.client.get(self.url + "?timezone=UTC&timezone=UTC").status_code, 400)
        response = self.client.get(self.url, {"start_date": "2024-01-01", "end_date": "2024-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["days"]), 366)

    def test_authentication_and_read_only(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.get().status_code, 401)
        self.verify.side_effect = None
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.get().status_code, 403)
