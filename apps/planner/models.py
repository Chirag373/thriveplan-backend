from typing import ClassVar

from django.conf import settings
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending"
        IN_PROGRESS = "In Progress"
        COMPLETED = "Completed"
        OVERDUE = "Overdue"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    date = models.DateField()
    time = models.TimeField()
    category = models.CharField(max_length=100, blank=True)
    reminder = models.BooleanField(default=False)
    period = models.CharField(
        max_length=10,
        blank=True,
        choices=[("Morning", "Morning"), ("Afternoon", "Afternoon"), ("Evening", "Evening")],
    )
    dashboard = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("date", "time", "id")
        indexes: ClassVar = [models.Index(fields=["owner", "date", "time", "id"])]
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(status__in=["Pending", "In Progress", "Completed", "Overdue"]),
                name="task_valid_status",
            )
        ]

    @property
    def completed(self):
        return self.status == self.Status.COMPLETED


class Subtask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=255)
    completed = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
