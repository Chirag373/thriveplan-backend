from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone


class PointTransaction(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="point_transactions"
    )
    points = models.IntegerField()
    description = models.CharField(max_length=255)
    # A stable event identifier prevents a retried award from being recorded twice.
    source_key = models.CharField(max_length=150)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes: ClassVar = [models.Index(fields=["owner", "-occurred_at", "-id"])]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["owner", "source_key"], name="rewards_unique_event"),
            models.CheckConstraint(condition=~models.Q(points=0), name="rewards_nonzero_points"),
        ]


class ActivitySession(models.Model):
    class Activity(models.TextChoices):
        BREATHING = "breathing"
        PUZZLES = "puzzles"
        QUIZZES = "quizzes"
        WORKOUTS = "workouts"
        READING = "reading"

    # Client-generated UUID makes session creation safe to retry.
    id = models.UUIDField(primary_key=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    activity = models.CharField(max_length=12, choices=Activity.choices)
    target_id = models.CharField(max_length=100)
    minimum_seconds = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    reward_date = models.DateField(null=True, blank=True)
    points_awarded = models.PositiveSmallIntegerField(default=0)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    reward_reason = models.CharField(max_length=30, blank=True)

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["owner", "reward_date", "activity"]),
            models.Index(fields=["owner", "activity", "target_id"]),
        ]
