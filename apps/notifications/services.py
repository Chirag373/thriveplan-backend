from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from apps.accounts.models import User

from .models import Device, Notification


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


class DeviceRegistrationConflict(APIException):
    status_code = 409
    default_detail = "Device registration conflicts with an existing registration. Unregister it before switching accounts."
    default_code = "device_registration_conflict"


def register_device(*, user, installation_id, push_token, platform):
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user.pk)
            if not user.is_active:
                raise PermissionDenied("This account has been deactivated.")
            device = (
                Device.objects.select_for_update().filter(installation_id=installation_id).first()
            )
            if device is not None and device.owner_id != user.pk:
                raise DeviceRegistrationConflict()
            if device is None:
                device = Device.objects.create(
                    owner=user,
                    installation_id=installation_id,
                    push_token=push_token,
                    platform=platform,
                )
                return device, True
            device.push_token = push_token
            device.platform = platform
            device.save(update_fields=["push_token", "platform", "updated_at"])
            return device, False
    except IntegrityError:
        # Unique constraints cover concurrent registration and token collisions.
        raise DeviceRegistrationConflict() from None


@transaction.atomic
def unregister_device(*, user, device_id):
    device = get_object_or_404(Device.objects.select_for_update(), pk=device_id, owner=user)
    device.delete()
