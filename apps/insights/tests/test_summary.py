from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.journal.models import JournalEntry
from apps.planner.models import Task


class SummaryTests(TestCase):
    url = "/api/v1/insights/summary/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="insights-user", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        Task.objects.create(owner=other, title="Private", date="2026-10-28", time="09:00")
        JournalEntry.objects.create(owner=other, thoughts="Private", mood="Low")
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "insights-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_empty_user_and_no_other_user_leakage(self):
        with self.assertNumQueries(3):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tasks"]["total"], 0)
        self.assertEqual(response.data["tasks"]["completion_percentage"], 0.0)
        self.assertEqual(response.data["journal"]["total_entries"], 0)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_counts_and_status_semantics(self):
        for status in Task.Status.values:
            Task.objects.create(
                owner=self.user, title=status, date="2026-10-28", time="09:00", status=status
            )
        for mood in ["Great", "Great", "Good", None]:
            JournalEntry.objects.create(owner=self.user, thoughts="Entry", mood=mood)
        data = self.client.get(self.url).data
        self.assertEqual(data["tasks"]["total"], 4)
        self.assertEqual(data["tasks"]["completed"], 1)
        self.assertEqual(data["tasks"]["pending"], 3)
        self.assertEqual(data["tasks"]["not_started"], 1)
        self.assertEqual(data["tasks"]["completion_percentage"], 25.0)
        self.assertEqual(data["journal"]["moods"]["Great"], 2)
        self.assertEqual(data["journal"]["unrecorded_mood"], 1)

    def test_date_range_and_timezone_boundaries(self):
        for date in ["2026-10-27", "2026-10-28", "2026-10-29"]:
            Task.objects.create(owner=self.user, title="Task", date=date, time="09:00")
        for timestamp in [
            "2026-10-27T18:29:59Z",
            "2026-10-27T18:30:00Z",
            "2026-10-28T18:29:59Z",
            "2026-10-28T18:30:00Z",
        ]:
            JournalEntry.objects.create(owner=self.user, thoughts="Entry", date=timestamp)
        data = self.client.get(
            self.url,
            {"start_date": "2026-10-28", "end_date": "2026-10-28", "timezone": "Asia/Kolkata"},
        ).data
        self.assertEqual(data["tasks"]["total"], 1)
        self.assertEqual(data["journal"]["total_entries"], 2)

    def test_dst_day(self):
        for timestamp in ["2026-03-08T05:00:00Z", "2026-03-09T03:59:59Z", "2026-03-09T04:00:00Z"]:
            JournalEntry.objects.create(owner=self.user, thoughts="Entry", date=timestamp)
        data = self.client.get(
            self.url,
            {"start_date": "2026-03-08", "end_date": "2026-03-08", "timezone": "America/New_York"},
        ).data
        self.assertEqual(data["journal"]["total_entries"], 2)

    def test_invalid_filters(self):
        for query in [
            {"start_date": "2026-10-28"},
            {"end_date": "bad"},
            {"start_date": "2026-10-29", "end_date": "2026-10-28"},
            {"timezone": "invalid"},
            {"owner": 2},
        ]:
            self.assertEqual(self.client.get(self.url, query).status_code, 400)
        self.assertEqual(self.client.get(self.url + "?timezone=UTC&timezone=UTC").status_code, 400)

    def test_authentication_and_read_only(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.verify.side_effect = None
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 403)
