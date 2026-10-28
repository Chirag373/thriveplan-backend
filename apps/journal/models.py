from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone


class JournalEntry(models.Model):
    class Mood(models.TextChoices):
        GREAT = "Great"
        GOOD = "Good"
        OKAY = "Okay"
        LOW = "Low"
        STRESSED = "Stressed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal_entries"
    )
    mood = models.CharField(max_length=10, choices=Mood.choices, null=True, blank=True)
    thoughts = models.TextField()
    date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-id")
        indexes: ClassVar = [models.Index(fields=["owner", "-date", "-id"])]
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(mood__isnull=True)
                | models.Q(mood__in=["Great", "Good", "Okay", "Low", "Stressed"]),
                name="journal_valid_mood",
            )
        ]


class JournalTemplate(models.Model):
    id = models.SlugField(primary_key=True, max_length=50)
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    prompt = models.TextField()
    icon = models.CharField(max_length=20)
    colors = models.JSONField(default=list)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("position", "id")
