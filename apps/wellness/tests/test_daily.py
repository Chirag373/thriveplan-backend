from datetime import UTC, datetime
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.wellness.models import DailyContent, WellnessContent


class DailyWellnessTests(TestCase):
    url = "/api/v1/wellness/daily/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="wellness-user", name="Alex")
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "wellness-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def publish(self, kind, position=0, active=True):
        content = WellnessContent.objects.create(
            kind=kind, title=f"Test {kind} {position}", is_active=active
        )
        DailyContent.objects.create(
            date="2026-10-28", kind=kind, content=content, position=position
        )
        return content

    def get(self, **query):
        return self.client.get(self.url, {"date": "2026-10-28", **query})

    def test_complete_daily_response_and_query_count(self):
        for kind in ["quote", "song", "workout", "joke"]:
            self.publish(kind)
        second = self.publish("book", position=2)
        first = self.publish("book", position=1)
        with self.assertNumQueries(2):
            response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data), {"date", "timezone", "quote", "song", "books", "workout", "joke"}
        )
        self.assertEqual([book["id"] for book in response.data["books"]], [first.pk, second.pk])
        self.assertEqual(response.data["song"]["kind"], "song")
        self.assertNotIn("is_active", response.data["song"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_empty_date_and_inactive_content(self):
        self.publish("quote", active=False)
        self.publish("book", active=False)
        response = self.get()
        self.assertIsNone(response.data["quote"])
        self.assertEqual(response.data["books"], [])
        self.assertEqual(DailyContent.objects.count(), 2)
        self.assertIsNone(self.get(date="2026-10-29").data["quote"])

    def test_local_day_at_utc_boundary(self):
        with patch(
            "apps.wellness.views.timezone.now",
            return_value=datetime(2026, 10, 27, 20, 0, tzinfo=UTC),
        ):
            response = self.client.get(self.url, {"timezone": "Asia/Kolkata"})
            self.assertEqual(response.data["date"], "2026-10-28")
            self.assertEqual(self.client.get(self.url).data["date"], "2026-10-27")

    def test_invalid_queries(self):
        for query in [
            {"date": "2026-02-30"},
            {"timezone": "not/a/zone"},
            {"timezone": "/etc/passwd"},
            {"owner": 1},
        ]:
            self.assertEqual(self.get(**query).status_code, 400)
        self.assertEqual(
            self.client.get(self.url + "?date=2026-10-28&date=2026-10-29").status_code, 400
        )

    def test_mismatched_content_is_not_exposed(self):
        book = WellnessContent.objects.create(kind="book", title="Book")
        selection = DailyContent(date="2026-10-28", kind="quote", content=book)
        with self.assertRaises(ValidationError):
            selection.full_clean()
        selection.save()
        self.assertIsNone(self.get().data["quote"])

    def test_singleton_slot_constraint(self):
        self.publish("quote")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.publish("quote", position=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.publish("quote")

    def test_authentication_and_read_only(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.get().status_code, 401)
        self.verify.side_effect = None
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.get().status_code, 403)
