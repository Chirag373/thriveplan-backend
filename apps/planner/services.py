from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Reminder, Subtask, Task


def list_tasks(*, user, filters):
    tasks = Task.objects.filter(owner=user).prefetch_related("subtasks")
    if "date" in filters:
        tasks = tasks.filter(date=filters["date"])
    if "status" in filters:
        tasks = tasks.filter(status=filters["status"])
    if "completed" in filters:
        if filters["completed"]:
            tasks = tasks.filter(status=Task.Status.COMPLETED)
        else:
            tasks = tasks.exclude(status=Task.Status.COMPLETED)
    return tasks


@transaction.atomic
def create_task(*, user, data):
    return Task.objects.create(owner=user, **data)


@transaction.atomic
def update_task(*, user, task_id, data):
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, owner=user)
    for field, value in data.items():
        setattr(task, field, value)
    if task.completed or data.get("reminder") is False:
        task.reminders.all().delete()
        task.reminder = False
        data = {**data, "reminder": False}
    task.save(update_fields=[*data, "updated_at"])
    return task


@transaction.atomic
def delete_task(*, user, task_id):
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, owner=user)
    task.delete()


@transaction.atomic
def create_subtask(*, user, task_id, data):
    # Lock the parent so concurrent additions append in a consistent order.
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, owner=user)
    last_position = task.subtasks.aggregate(last=Max("position"))["last"]
    position = 0 if last_position is None else last_position + 1
    return Subtask.objects.create(task=task, position=position, **data)


@transaction.atomic
def update_subtask(*, user, task_id, subtask_id, data):
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, owner=user)
    subtask = get_object_or_404(Subtask, pk=subtask_id, task=task)
    for field, value in data.items():
        setattr(subtask, field, value)
    subtask.save(update_fields=list(data))
    return subtask


@transaction.atomic
def delete_subtask(*, user, task_id, subtask_id):
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, owner=user)
    subtask = get_object_or_404(Subtask, pk=subtask_id, task=task)
    subtask.delete()


def list_reminders(*, user, task_id):
    task = get_object_or_404(Task, pk=task_id, owner=user)
    return task.reminders.all()


@transaction.atomic
def schedule_reminder(*, user, task_id, scheduled_at):
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, owner=user)
    if task.completed:
        raise ValidationError({"task": "Completed tasks cannot have reminders."})
    if scheduled_at <= timezone.now():
        raise ValidationError({"scheduled_at": "Choose a future reminder time."})
    existing = task.reminders.filter(scheduled_at=scheduled_at).first()
    if existing is not None:
        return existing, False
    if task.reminders.count() >= 20:
        raise ValidationError(
            {"task": "A task can have at most 20 reminders. Cancel one before adding another."}
        )
    reminder = Reminder.objects.create(task=task, scheduled_at=scheduled_at)
    task.reminder = True
    task.save(update_fields=["reminder", "updated_at"])
    return reminder, True


@transaction.atomic
def cancel_reminder(*, user, task_id, reminder_id):
    task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, owner=user)
    reminder = get_object_or_404(Reminder, pk=reminder_id, task=task)
    reminder.delete()
    task.reminder = task.reminders.exists()
    task.save(update_fields=["reminder", "updated_at"])
