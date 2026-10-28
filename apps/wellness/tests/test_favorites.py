from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.wellness.models import Favorite, WellnessContent


class FavoriteTests(TestCase):
    url = "/api/v1/wellness/favorites/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="favorites-user", name="Alex")
        self.other = User.objects.create_user(firebase_uid="other", name="Other")
        self.book = WellnessContent.objects.create(kind="book", title="Book")
        self.quote = WellnessContent.objects.create(kind="quote", title="Quote")
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "favorites-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_save_and_retry(self):
        first = self.client.post(self.url, {"content_id": self.book.pk}, format="json")
        second = self.client.post(self.url, {"content_id": self.book.pk}, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data, second.data)
        self.assertEqual(first.data["content"]["id"], self.book.pk)
        self.assertEqual(Favorite.objects.count(), 1)
        self.assertEqual(Favorite.objects.get().owner, self.user)

    def test_list_owned_active_content_pagination_and_kind(self):
        Favorite.objects.create(owner=self.other, content=self.book)
        Favorite.objects.create(owner=self.user, content=self.quote)
        newest = Favorite.objects.create(owner=self.user, content=self.book)
        with self.assertNumQueries(3):
            response = self.client.get(self.url, {"page_size": 1})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["id"], newest.pk)
        self.assertIsNotNone(response.data["next"])
        response = self.client.get(self.url, {"kind": "quote"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["content"]["id"], self.quote.pk)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_inactive_and_unknown_content_cannot_be_saved(self):
        self.book.is_active = False
        self.book.save()
        for content_id in [self.book.pk, 99999]:
            self.assertEqual(
                self.client.post(self.url, {"content_id": content_id}, format="json").status_code,
                404,
            )
        self.assertFalse(Favorite.objects.exists())

    def test_inactive_saved_content_hidden_but_can_be_removed(self):
        favorite = Favorite.objects.create(owner=self.user, content=self.book)
        WellnessContent.objects.filter(pk=self.book.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).data["results"], [])
        self.assertEqual(self.client.delete(f"{self.url}{favorite.pk}/").status_code, 204)

    def test_delete_ownership_and_content_preserved(self):
        own = Favorite.objects.create(owner=self.user, content=self.book)
        foreign = Favorite.objects.create(owner=self.other, content=self.book)
        for favorite_id in [foreign.pk, 99999]:
            self.assertEqual(self.client.delete(f"{self.url}{favorite_id}/").status_code, 404)
        response = self.client.delete(f"{self.url}{own.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertTrue(Favorite.objects.filter(pk=foreign.pk).exists())
        self.assertTrue(WellnessContent.objects.filter(pk=self.book.pk).exists())
        self.assertEqual(self.client.delete(f"{self.url}{own.pk}/").status_code, 404)

    def test_unique_user_content_constraint(self):
        Favorite.objects.create(owner=self.user, content=self.book)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Favorite.objects.create(owner=self.user, content=self.book)

    def test_invalid_input(self):
        for data in [
            {},
            {"content_id": -1},
            {"content_id": "bad"},
            {"content_id": self.book.pk, "owner": self.other.pk},
        ]:
            self.assertEqual(self.client.post(self.url, data, format="json").status_code, 400)
        for query in [{"page_size": 101}, {"kind": "invalid"}, {"owner": 1}, {"page": 0}]:
            self.assertEqual(self.client.get(self.url, query).status_code, 400)
        self.assertEqual(self.client.get(self.url + "?kind=book&kind=quote").status_code, 400)
        self.assertFalse(Favorite.objects.exists())

    def test_authentication_and_disabled_account(self):
        favorite = Favorite.objects.create(owner=self.user, content=self.book)
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 401)
        self.assertEqual(self.client.delete(f"{self.url}{favorite.pk}/").status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.delete(f"{self.url}{favorite.pk}/").status_code, 403)
