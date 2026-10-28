from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class WellnessContent(models.Model):
    class Kind(models.TextChoices):
        QUOTE = "quote"
        SONG = "song"
        BOOK = "book"
        WORKOUT = "workout"
        JOKE = "joke"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    body = models.TextField(blank=True)
    creator = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    media_url = models.URLField(blank=True)
    image_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(kind__in=["quote", "song", "book", "workout", "joke"]),
                name="wellness_valid_kind",
            )
        ]


class DailyContent(models.Model):
    date = models.DateField()
    kind = models.CharField(max_length=10, choices=WellnessContent.Kind.choices)
    content = models.ForeignKey(
        WellnessContent, on_delete=models.CASCADE, related_name="daily_selections"
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["date", "kind", "position"], name="wellness_unique_daily_slot"
            ),
            models.UniqueConstraint(
                fields=["date", "content"], name="wellness_unique_daily_content"
            ),
            models.CheckConstraint(
                condition=models.Q(kind="book") | models.Q(position=0),
                name="wellness_single_nonbook_slot",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=["quote", "song", "book", "workout", "joke"]),
                name="wellness_daily_valid_kind",
            ),
        ]

    def clean(self):
        super().clean()
        if self.content_id and self.content.kind != self.kind:
            raise ValidationError({"content": "Content kind must match the daily slot."})


class Favorite(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wellness_favorites"
    )
    content = models.ForeignKey(WellnessContent, on_delete=models.CASCADE, related_name="favorites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["owner", "content"], name="wellness_unique_user_favorite"
            )
        ]
        indexes: ClassVar = [models.Index(fields=["owner", "-created_at", "-id"])]
