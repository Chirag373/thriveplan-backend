from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Notification


def list_notifications(*, user, filters):
    notifications = Notification.objects.filter(owner=user)
    if "category" in filters:
        notifications = notifications.filter(category=filters["category"])
    if "unread" in filters:
        notifications = notifications.filter(read_at__isnull=filters["unread"])
    return notifications


@transaction.atomic
def mark_read(*, user, notification_id):
    notification = get_object_or_404(
        Notification.objects.select_for_update(), owner=user, pk=notification_id
    )
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification


def mark_all_read(*, user):
    cutoff = timezone.now()
    return Notification.objects.filter(
        owner=user, read_at__isnull=True, created_at__lte=cutoff
    ).update(read_at=cutoff)
