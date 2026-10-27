from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404

from .models import Subtask, Task


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
