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
