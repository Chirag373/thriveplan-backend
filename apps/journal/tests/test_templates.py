from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.journal.models import JournalTemplate


class JournalTemplateTests(TestCase):
    url = "/api/v1/journal/templates/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(firebase_uid="template-user", name="Alex")
        self.provider = patch(
            "apps.accounts.authentication.FirebaseProvider.authenticate",
            return_value={"uid": "template-user"},
        )
        self.verify = self.provider.start()
        self.addCleanup(self.provider.stop)

    def test_seeded_catalog_matches_frontend_and_is_read_only(self):
        with self.assertNumQueries(2):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data],
            ["my-day", "gratitude", "wins", "mood", "goals", "reflection", "self-care", "weekend"],
        )
        self.assertEqual(
            set(response.data[0]), {"id", "title", "description", "prompt", "icon", "colors"}
        )
        self.assertEqual(response.data[0]["prompt"], "What made today meaningful?")
        self.assertEqual(response.data[0]["colors"], ["#FFF8E7", "#FFF2DC"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        for method in ["post", "patch", "delete"]:
            self.assertEqual(
                getattr(self.client, method)(self.url, {}, format="json").status_code, 405
            )

    def test_only_active_templates_and_stable_order(self):
        JournalTemplate.objects.filter(pk="my-day").update(is_active=False)
        JournalTemplate.objects.filter(pk="weekend").update(position=0)
        response = self.client.get(self.url)
        self.assertEqual(response.data[0]["id"], "weekend")
        self.assertNotIn("my-day", [row["id"] for row in response.data])

    def test_empty_catalog(self):
        JournalTemplate.objects.update(is_active=False)
        self.assertEqual(self.client.get(self.url).data, [])

    def test_authentication_and_disabled_user(self):
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_detail_matches_catalog_item(self):
        catalog = self.client.get(self.url).data
        for item in catalog:
            with self.subTest(template=item["id"]), self.assertNumQueries(2):
                response = self.client.get(f"{self.url}{item['id']}/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, item)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_missing_and_inactive_detail_return_404(self):
        JournalTemplate.objects.filter(pk="gratitude").update(is_active=False)
        for template_id in ["gratitude", "does-not-exist"]:
            self.assertEqual(self.client.get(f"{self.url}{template_id}/").status_code, 404)

    def test_detail_authentication_and_disabled_user(self):
        url = f"{self.url}gratitude/"
        self.verify.side_effect = AuthenticationFailed()
        self.assertEqual(self.client.get(url).status_code, 401)
        self.verify.side_effect = None
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_detail_does_not_allow_mutations(self):
        url = f"{self.url}gratitude/"
        for method in ["post", "put", "patch", "delete"]:
            self.assertEqual(getattr(self.client, method)(url, {}, format="json").status_code, 405)
        self.assertTrue(JournalTemplate.objects.filter(pk="gratitude").exists())
