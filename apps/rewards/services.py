from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.journal.models import JournalEntry
from apps.wellness.models import WellnessContent

from .game_validation import CATALOG, validate_submission
from .models import ActivitySession, PointTransaction
from .serializers import PointTransactionSerializer

MILESTONE_STEP = 300


def get_rewards_summary(*, user, filters):
    zone = ZoneInfo(filters["timezone"])
    today = timezone.localdate(timezone=zone)
    start = today - timedelta(days=6)
    lower = datetime.combine(start, time.min, tzinfo=zone)
    upper = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone)
    transactions = PointTransaction.objects.filter(owner=user, occurred_at__lt=upper)
    total = transactions.aggregate(total=Sum("points", default=0))["total"]
    daily = dict(
        transactions.filter(occurred_at__gte=lower)
        .order_by()
        .annotate(day=TruncDate("occurred_at", tzinfo=zone))
        .values("day")
        .annotate(points=Sum("points"))
        .values_list("day", "points")
    )
    # A journal streak remains current through yesterday until today's entry is written.
    journal_days = (
        JournalEntry.objects.filter(owner=user, date__lt=upper)
        .annotate(day=TruncDate("date", tzinfo=zone))
        .values_list("day", flat=True)
        .order_by("-day")
        .distinct()
    )
    streak = 0
    expected = today
    for day in journal_days.iterator():
        if not streak and day == today - timedelta(days=1):
            expected = day
        if day != expected:
            break
        streak += 1
        expected -= timedelta(days=1)
    target = (max(total, 0) // MILESTONE_STEP + 1) * MILESTONE_STEP
    return {
        "timezone": filters["timezone"],
        "date": today.isoformat(),
        "total_points": total,
        "today_points": daily.get(today, 0),
        "weekly_points": [
            {
                "date": (day := start + timedelta(days=index)).isoformat(),
                "points": daily.get(day, 0),
            }
            for index in range(7)
        ],
        "history": PointTransactionSerializer(transactions[:10], many=True).data,
        "current_streak": {"days": streak, "activity": "journal"},
        "next_milestone": {
            "target_points": target,
            "remaining_points": target - total,
            "progress_percentage": round(max(total, 0) * 100 / target, 2),
        },
    }


ACTIVITY_POINTS = {"breathing": 5, "puzzles": 5, "quizzes": 5, "workouts": 10, "reading": 5}


def session_data(session, *, already_completed=False):
    return {
        "id": str(session.id),
        "activity": session.activity,
        "target_id": session.target_id,
        "started_at": session.started_at,
        "minimum_seconds": session.minimum_seconds,
        "completed_at": session.completed_at,
        "reward_date": session.reward_date,
        "reward_timezone": settings.REWARDS_TIME_ZONE,
        "points_awarded": session.points_awarded,
        "reward_reason": session.reward_reason,
        "score": session.score,
        "already_completed": already_completed,
    }


@transaction.atomic
def start_activity_session(*, user, activity, data):
    # Serialize awards for this account, including requests using different session IDs.
    User.objects.select_for_update().get(pk=user.pk)
    existing = ActivitySession.objects.filter(pk=data["request_id"]).first()
    if existing:
        if (
            existing.owner_id != user.pk
            or existing.activity != activity
            or existing.target_id != data["target_id"]
        ):
            raise ValidationError({"request_id": "Request ID is already in use."})
        return existing, False
    target = data["target_id"]
    minimum = 0
    if activity in ("puzzles", "quizzes"):
        item = CATALOG.get(target)
        if not item or (item["game"] == "quiz") != (activity == "quizzes"):
            raise ValidationError({"target_id": "Unknown puzzle or quiz round."})
    elif activity == "breathing":
        if target != "guided-breathing-v1":
            raise ValidationError({"target_id": "Use guided-breathing-v1."})
        minimum = 60
    else:
        if (
            not target.isascii()
            or not target.isdecimal()
            or len(target) > 18
            or target != str(int(target))
        ):
            raise ValidationError({"target_id": "Use a wellness content ID."})
        content = get_object_or_404(
            WellnessContent,
            pk=int(target),
            is_active=True,
            kind="workout" if activity == "workouts" else "book",
        )
        target = str(content.pk)
        minimum = (content.duration_seconds or 600) if activity == "workouts" else 300
        if minimum >= 86400:
            raise ValidationError({"target_id": "Content duration exceeds the session limit."})
    try:
        with transaction.atomic():
            session = ActivitySession.objects.create(
                id=data["request_id"],
                owner=user,
                activity=activity,
                target_id=target,
                minimum_seconds=minimum,
                started_at=timezone.now(),
            )
    except IntegrityError:
        raise ValidationError({"request_id": "Request ID is already in use."}) from None
    return session, True


@transaction.atomic
def complete_activity_session(*, user, activity, session_id, data):
    User.objects.select_for_update().get(pk=user.pk)
    session = get_object_or_404(ActivitySession, pk=session_id, owner=user, activity=activity)
    if session.completed_at:
        return session_data(session, already_completed=True)
    now = timezone.now()
    elapsed = (now - session.started_at).total_seconds()
    if elapsed >= 86400:
        raise ValidationError({"session": "Session expired. Start a new session."})
    if elapsed < session.minimum_seconds:
        raise ValidationError({"session": "The session's required duration has not elapsed."})
    if activity in ("puzzles", "quizzes"):
        valid, score = validate_submission(session.target_id, data.get("answers", []))
        if not valid:
            raise ValidationError({"answers": "Submit a valid solution or a complete quiz round."})
        session.score = score
    elif not data["confirmed"]:
        raise ValidationError({"confirmed": "Confirm that you completed the session."})
    elif "answers" in data:
        raise ValidationError({"answers": "Answers apply only to games."})

    day = timezone.localdate(now, timezone=ZoneInfo(settings.REWARDS_TIME_ZONE))
    completed = ActivitySession.objects.filter(owner=user, completed_at__isnull=False)
    today = completed.filter(reward_date=day)
    reason = "awarded"
    if (
        activity == "puzzles"
        and completed.filter(
            activity=activity,
            target_id=session.target_id,
        ).exists()
    ):
        reason = "already_solved"
    elif (
        activity != "puzzles"
        and today.filter(activity=activity, points_awarded__gt=0).exists()
        or activity in ("puzzles", "quizzes")
        and today.filter(
            activity__in=("puzzles", "quizzes"),
        ).aggregate(total=Sum("points_awarded", default=0))["total"]
        >= 10
    ):
        reason = "daily_limit"
    points = ACTIVITY_POINTS[activity] if reason == "awarded" else 0
    session.completed_at = now
    session.reward_date = day
    session.points_awarded = points
    session.reward_reason = reason
    session.save(
        update_fields=[
            "completed_at",
            "reward_date",
            "points_awarded",
            "reward_reason",
            "score",
        ]
    )
    if points:
        PointTransaction.objects.create(
            owner=user,
            points=points,
            description=f"Completed {activity} session",
            source_key=f"activity:{session.id}",
            occurred_at=now,
        )
    return session_data(session)


@transaction.atomic
def award_journal_entry(*, user):
    User.objects.select_for_update().get(pk=user.pk)
    now = timezone.now()
    day = timezone.localdate(now, timezone=ZoneInfo(settings.REWARDS_TIME_ZONE))
    _, created = PointTransaction.objects.get_or_create(
        owner=user,
        source_key=f"journal:{day.isoformat()}",
        defaults={"points": 10, "description": "Saved a journal entry", "occurred_at": now},
    )
    return 10 if created else 0


@transaction.atomic
def award_task_completion(*, user, task, completed_at):
    # Caller locks the user before the task and persists its first completion even at the cap.
    User.objects.select_for_update().get(pk=user.pk)
    zone = ZoneInfo(settings.REWARDS_TIME_ZONE)
    day = timezone.localdate(completed_at, timezone=zone)
    lower = datetime.combine(day, time.min, tzinfo=zone)
    upper = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    awarded = PointTransaction.objects.filter(
        owner=user,
        source_key__startswith="task:",
        occurred_at__gte=lower,
        occurred_at__lt=upper,
    ).aggregate(total=Sum("points", default=0))["total"]
    if awarded >= 25:
        return 0
    _, created = PointTransaction.objects.get_or_create(
        owner=user,
        source_key=f"task:{task.pk}",
        defaults={"points": 5, "description": "Completed a task", "occurred_at": completed_at},
    )
    return 5 if created else 0
