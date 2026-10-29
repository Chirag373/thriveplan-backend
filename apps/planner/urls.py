from django.urls import path

from .views import (
    ReminderCancelEndpoint,
    ReminderListEndpoint,
    SubtaskCreateEndpoint,
    SubtaskDetailEndpoint,
    TaskDetailEndpoint,
    TaskListEndpoint,
)

urlpatterns = [
    path("tasks/<int:task_id>/reminders/", ReminderListEndpoint.as_view(), name="reminder-list"),
    path(
        "tasks/<int:task_id>/reminders/<int:reminder_id>/",
        ReminderCancelEndpoint.as_view(),
        name="reminder-cancel",
    ),
    path("tasks/<int:task_id>/subtasks/", SubtaskCreateEndpoint.as_view(), name="subtask-create"),
    path(
        "tasks/<int:task_id>/subtasks/<int:subtask_id>/",
        SubtaskDetailEndpoint.as_view(),
        name="subtask-detail",
    ),
    path("tasks/", TaskListEndpoint.as_view(), name="task-list"),
    path("tasks/<int:task_id>/", TaskDetailEndpoint.as_view(), name="task-detail"),
]
