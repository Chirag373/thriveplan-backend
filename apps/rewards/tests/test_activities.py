from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.rewards.game_validation import CATALOG, validate_submission
from apps.rewards.models import ActivitySession, PointTransaction
from apps.wellness.models import WellnessContent


@override_settings(REWARDS_TIME_ZONE="UTC")
class ActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(firebase_uid="activity-user", name="Alex")
        self.other = User.objects.create_user(firebase_uid="other-user", name="Other")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        self.clock = patch("apps.rewards.services.timezone.now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def start(self, activity, target, request_id=None):
        return self.client.post(
            f"/api/v1/rewards/{activity}/sessions/",
            {
                "request_id": str(request_id or uuid4()),
                "target_id": target,
            },
            format="json",
        )

    def complete(self, activity, identifier, body=None):
        return self.client.post(
            f"/api/v1/rewards/{activity}/sessions/{identifier}/complete/",
            body or {"confirmed": True},
            format="json",
        )

    def age(self, session, seconds):
        ActivitySession.objects.filter(pk=session).update(
            started_at=self.now - timedelta(seconds=seconds),
        )

    def solve(self, target):
        session = self.start("puzzles", target).data["id"]
        return self.complete(
            "puzzles", session, {"answers": CATALOG[target]["definition"]["solution"]}
        )

    def quiz(self, target="quiz-v1-1"):
        session = self.start("quizzes", target).data["id"]
        return self.complete(
            "quizzes",
            session,
            {
                "answers": [q["answer"] for q in CATALOG[target]["definition"]],
            },
        )

    def test_breathing_duration_confirmation_retries_and_daily_limit(self):
        key = uuid4()
        response = self.start("breathing", "guided-breathing-v1", key)
        self.assertEqual(response.status_code, 201)
        identifier = response.data["id"]
        self.assertEqual(self.start("breathing", "guided-breathing-v1", key).status_code, 200)
        self.assertEqual(self.complete("breathing", identifier).status_code, 400)
        self.age(identifier, 60)
        self.assertEqual(
            self.complete("breathing", identifier, {"confirmed": False}).status_code, 400
        )
        response = self.complete("breathing", identifier)
        self.assertEqual(response.data["points_awarded"], 5)
        self.assertFalse(response.data["already_completed"])
        self.assertTrue(self.complete("breathing", identifier).data["already_completed"])
        second = self.start("breathing", "guided-breathing-v1").data["id"]
        self.age(second, 60)
        self.assertEqual(self.complete("breathing", second).data["reward_reason"], "daily_limit")
        self.assertEqual(PointTransaction.objects.count(), 1)
        self.assertEqual(self.client.get("/api/v1/rewards/summary/").data["total_points"], 5)

    def test_shared_games_limit_and_unique_puzzle_across_days(self):
        self.assertEqual(self.quiz().data["points_awarded"], 5)
        self.assertEqual(self.quiz("quiz-v1-2").data["points_awarded"], 0)
        self.assertEqual(self.solve("zip-v1-1").data["points_awarded"], 5)
        self.assertEqual(self.solve("queens-v1-1").data["reward_reason"], "daily_limit")
        self.assertEqual(self.solve("zip-v1-1").data["reward_reason"], "already_solved")
        with patch("apps.rewards.services.timezone.now", return_value=self.now + timedelta(days=1)):
            self.assertEqual(self.solve("zip-v1-1").data["points_awarded"], 0)
            self.assertEqual(self.solve("zip-v1-2").data["points_awarded"], 5)

    def test_quiz_requires_all_answers_but_not_perfect_score(self):
        identifier = self.start("quizzes", "quiz-v1-1").data["id"]
        self.assertEqual(self.complete("quizzes", identifier, {"answers": [0]}).status_code, 400)
        answers = [0] * len(CATALOG["quiz-v1-1"]["definition"])
        response = self.complete("quizzes", identifier, {"answers": answers})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["points_awarded"], 5)
        self.assertIsInstance(response.data["score"], int)

    def test_all_catalog_solutions_and_malformed_moves(self):
        for target, item in CATALOG.items():
            if item["game"] == "quiz":
                continue
            with self.subTest(target=target):
                self.assertTrue(validate_submission(target, item["definition"]["solution"])[0])
                self.assertFalse(validate_submission(target, [0] * 81)[0])
        identifier = self.start("puzzles", "zip-v1-1").data["id"]
        for answers in ([True], ["1"], [1.1], [999], [-1], [], [0] * 101):
            self.assertEqual(
                self.complete("puzzles", identifier, {"answers": answers}).status_code, 400
            )
        self.assertFalse(PointTransaction.objects.exists())

    def test_catalog_does_not_reveal_answers(self):
        for activity in ("puzzles", "quizzes"):
            response = self.client.get(f"/api/v1/rewards/{activity}/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('"solution"', response.content.decode())
            self.assertNotIn('"answer"', response.content.decode())
            self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_content_types_timers_and_rewards(self):
        book = WellnessContent.objects.create(kind="book", title="Read")
        workout = WellnessContent.objects.create(kind="workout", title="Move", duration_seconds=120)
        for activity, content, seconds, points in (
            ("reading", book, 300, 5),
            ("workouts", workout, 120, 10),
        ):
            response = self.start(activity, str(content.pk))
            self.assertEqual(response.status_code, 201)
            identifier = response.data["id"]
            self.assertEqual(response.data["minimum_seconds"], seconds)
            self.assertEqual(self.complete(activity, identifier).status_code, 400)
            self.age(identifier, seconds)
            self.assertEqual(self.complete(activity, identifier).data["points_awarded"], points)
            duplicate = self.start(activity, str(content.pk)).data["id"]
            self.age(duplicate, seconds)
            self.assertEqual(self.complete(activity, duplicate).data["points_awarded"], 0)
        self.assertEqual(self.start("reading", str(workout.pk)).status_code, 404)
        book.is_active = False
        book.save()
        self.assertEqual(self.start("reading", str(book.pk)).status_code, 404)
        self.assertEqual(self.start("reading", "99999999").status_code, 404)
        self.assertEqual(self.start("reading", "invalid").status_code, 400)

    def test_authentication_ownership_wrong_activity_and_unknown_fields(self):
        identifier = self.start("breathing", "guided-breathing-v1").data["id"]
        self.client.force_authenticate(self.other)
        self.assertEqual(self.complete("breathing", identifier).status_code, 404)
        self.assertEqual(
            self.start("breathing", "guided-breathing-v1", identifier).status_code, 400
        )
        self.client.force_authenticate(self.user)
        self.assertEqual(self.complete("reading", identifier).status_code, 404)
        self.assertEqual(self.complete("breathing", identifier, {"points": 999}).status_code, 400)
        self.assertEqual(self.start("puzzles", "made-up").status_code, 400)
        self.assertEqual(self.start("puzzles", "quiz-v1-1").status_code, 400)
        self.client = APIClient()
        self.assertEqual(self.start("breathing", "guided-breathing-v1").status_code, 401)
        self.assertEqual(self.complete("breathing", identifier).status_code, 401)

    def test_expired_sessions_and_server_reward_day(self):
        identifier = self.start("breathing", "guided-breathing-v1").data["id"]
        self.age(identifier, 86400)
        self.assertEqual(self.complete("breathing", identifier).status_code, 400)
        identifier = self.start("breathing", "guided-breathing-v1").data["id"]
        self.age(identifier, 60)
        with override_settings(REWARDS_TIME_ZONE="Pacific/Auckland"):
            response = self.complete("breathing", identifier)
        self.assertEqual(response.data["reward_date"].isoformat(), "2026-11-08")

    def test_ledger_failure_rolls_back_completion(self):
        identifier = self.start("breathing", "guided-breathing-v1").data["id"]
        self.age(identifier, 60)
        with (
            patch(
                "apps.rewards.services.PointTransaction.objects.create", side_effect=RuntimeError
            ),
            self.assertRaises(RuntimeError),
        ):
            self.complete("breathing", identifier)
        self.assertIsNone(ActivitySession.objects.get(pk=identifier).completed_at)
        self.assertEqual(self.complete("breathing", identifier).data["points_awarded"], 5)
