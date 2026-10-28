from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.journal.models import JournalEntry


class JournalTests(TestCase):
    url = "/api/v1/journal/entries/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="journal-user", name="Alex")
        other = User.objects.create_user(firebase_uid="other", name="Other")
        self.entry = JournalEntry.objects.create(
            owner=self.user, thoughts="Original", mood="Good", date="2026-10-26T10:00:00Z"
        )
        self.other = JournalEntry.objects.create(owner=other, thoughts="Private")
        self.detail = f"{self.url}{self.entry.pk}/"
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "journal-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_create_defaults_and_response(self):
        response = self.client.post(self.url, {"thoughts": " A calm day "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.data), {"id", "thoughts", "mood", "date"})
        self.assertEqual(response.data["thoughts"], "A calm day")
        self.assertIsNone(response.data["mood"])
        self.assertTrue(response.data["date"].endswith("Z"))
        self.assertEqual(JournalEntry.objects.get(pk=response.data["id"]).owner, self.user)

    def test_explicit_date_and_mood(self):
        response = self.client.post(
            self.url,
            {"thoughts": "Reflection", "mood": "Great", "date": "2026-10-27T10:00:00+05:30"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["date"], "2026-10-27T04:30:00Z")

    def test_list_owner_scope_order_pagination_and_filters(self):
        newest = JournalEntry.objects.create(
            owner=self.user, thoughts="Newest", mood="Great", date="2026-10-27T10:00:00Z"
        )
        response = self.client.get(self.url, {"page_size": 1})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["id"], newest.pk)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        response = self.client.get(self.url, {"mood": "Good"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.entry.pk)

    def test_partial_update_and_clear_mood(self):
        response = self.client.patch(self.detail, {"mood": None}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["thoughts"], "Original")
        self.assertIsNone(response.data["mood"])
        self.assertEqual(response.data["date"], "2026-10-26T10:00:00Z")

    def test_invalid_payloads_do_not_write(self):
        for data in [
            {},
            {"thoughts": " "},
            {"thoughts": "x" * 10001},
            {"mood": "invalid"},
            {"date": "2026-02-30T10:00:00Z"},
            {"date": "2026-10-27T10:00:00"},
            {"thoughts": "Changed", "owner": self.user.pk},
        ]:
            self.assertEqual(self.client.patch(self.detail, data, format="json").status_code, 400)
        self.assertEqual(
            self.client.post(self.url, {"mood": "Good"}, format="json").status_code, 400
        )
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.thoughts, "Original")
        self.assertEqual(JournalEntry.objects.count(), 2)

    def test_foreign_and_missing_entries_return_404(self):
        for entry_id in [self.other.pk, 99999]:
            url = f"{self.url}{entry_id}/"
            self.assertEqual(
                self.client.patch(url, {"thoughts": "Hack"}, format="json").status_code, 404
            )
            self.assertEqual(self.client.delete(url).status_code, 404)
        self.other.refresh_from_db()
        self.assertEqual(self.other.thoughts, "Private")

    def test_delete(self):
        response = self.client.delete(self.detail)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertTrue(JournalEntry.objects.filter(pk=self.other.pk).exists())
        self.assertEqual(self.client.delete(self.detail).status_code, 404)
        self.assertEqual(self.client.get(self.url).data["results"], [])

    def test_invalid_query(self):
        for params in [{"page": 0}, {"page_size": 101}, {"mood": "bad"}, {"owner": 1}]:
            self.assertEqual(self.client.get(self.url, params).status_code, 400)
        self.assertEqual(self.client.get(self.url + "?mood=Good&mood=Great").status_code, 400)
        self.assertEqual(self.client.get(self.url, {"page": 99}).status_code, 404)

    def test_authentication_and_deactivated_user(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 401)
        self.assertEqual(self.client.patch(self.detail, {}, format="json").status_code, 401)
        self.assertEqual(self.client.delete(self.detail).status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 403)
