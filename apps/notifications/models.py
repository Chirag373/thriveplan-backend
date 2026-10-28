from typing import ClassVar

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        TASKS = "Tasks"
        MINDFULNESS = "Mindfulness"
        SYSTEM = "System"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices)
    icon = models.CharField(
        max_length=10,
        choices=[(value, value) for value in ("task", "leaves", "journal", "star", "flame")],
    )
    destination = models.CharField(
        max_length=20,
        choices=[(value, value) for value in ("task", "mindfulness", "journal", "rewards")],
    )
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes: ClassVar = [
            models.Index(fields=["owner", "-created_at", "-id"]),
            models.Index(fields=["owner", "read_at"]),
        ]

    @property
    def unread(self):
        return self.read_at is None
