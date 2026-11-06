from datetime import UTC, datetime
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.journal.models import JournalEntry
from apps.rewards.models import PointTransaction


class RewardsSummaryTests(TestCase):
    url = "/api/v1/rewards/summary/"

    def setUp(self):
        self.user = User.objects.create_user(firebase_uid="rewards-user", name="Alex")
        self.other = User.objects.create_user(firebase_uid="other", name="Other")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        clock = patch(
            "apps.rewards.services.timezone.now", return_value=datetime(2026, 11, 6, 8, tzinfo=UTC)
        )
        clock.start()
        self.addCleanup(clock.stop)

    def award(self, points, when, owner=None, source="event"):
        return PointTransaction.objects.create(
            owner=owner or self.user,
            points=points,
            description="Completed a task",
            source_key=source,
            occurred_at=when,
        )

    def test_empty_and_private(self):
        self.award(250, "2026-11-06T00:00:00Z", owner=self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response.data["total_points"], 0)
        self.assertEqual(response.data["history"], [])
        self.assertEqual(len(response.data["weekly_points"]), 7)
        self.assertEqual(response.data["next_milestone"]["target_points"], 300)
        self.assertEqual(response.data["current_streak"]["days"], 0)

    def test_timezone_totals_history_and_adjustments(self):
        self.award(100, "2026-10-01T00:00:00Z", source="old")
        self.award(10, "2026-11-05T18:29:59Z", source="yesterday")
        self.award(20, "2026-11-05T18:30:00Z", source="today")
        self.award(-5, "2026-11-06T00:00:00Z", source="adjustment")
        self.award(999, "2026-11-06T18:30:00Z", source="future")
        data = self.client.get(self.url, {"timezone": "Asia/Kolkata"}).data
        self.assertEqual(data["total_points"], 125)
        self.assertEqual(data["today_points"], 15)
        self.assertEqual(data["weekly_points"][-1], {"date": "2026-11-06", "points": 15})
        self.assertEqual(data["history"][0]["points"], -5)
        self.assertEqual(data["next_milestone"]["remaining_points"], 175)

    def test_streak_counts_distinct_local_journal_days(self):
        for date in [
            "2026-11-06T00:00:00Z",
            "2026-11-05T20:00:00Z",
            "2026-11-04T20:00:00Z",
            "2026-11-03T20:00:00Z",
        ]:
            JournalEntry.objects.create(owner=self.user, thoughts="Entry", date=date)
        data = self.client.get(self.url, {"timezone": "Asia/Kolkata"}).data
        self.assertEqual(data["current_streak"]["days"], 3)

    def test_yesterday_streak_and_broken_streak(self):
        entry = JournalEntry.objects.create(
            owner=self.user, thoughts="Entry", date="2026-11-05T00:00:00Z"
        )
        self.assertEqual(self.client.get(self.url).data["current_streak"]["days"], 1)
        entry.date = "2026-11-04T00:00:00Z"
        entry.save()
        self.assertEqual(self.client.get(self.url).data["current_streak"]["days"], 0)

    def test_milestone_and_history_limit(self):
        for index in range(12):
            self.award(25, "2026-11-06T00:00:00Z", source=str(index))
        data = self.client.get(self.url).data
        self.assertEqual(len(data["history"]), 10)
        self.assertEqual(data["next_milestone"]["target_points"], 600)
        self.assertEqual(data["next_milestone"]["progress_percentage"], 50)

    def test_invalid_queries(self):
        for query in ["?timezone=invalid", "?timezone=UTC&timezone=UTC", "?owner=1"]:
            self.assertEqual(self.client.get(self.url + query).status_code, 400)

    def test_read_only_and_authentication(self):
        self.assertEqual(self.client.post(self.url, {"points": 999}).status_code, 405)
        self.client = APIClient()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_duplicate_event_is_rejected(self):
        self.award(10, "2026-11-06T00:00:00Z")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.award(10, "2026-11-06T00:00:00Z")
