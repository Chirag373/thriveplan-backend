from django.urls import path

from .views import (
    DeviceRegistrationEndpoint,
    DeviceUnregisterEndpoint,
    NotificationListEndpoint,
    NotificationReadAllEndpoint,
    NotificationReadEndpoint,
)

urlpatterns = [
    path("devices/", DeviceRegistrationEndpoint.as_view(), name="device-registration"),
    path("devices/<int:device_id>/", DeviceUnregisterEndpoint.as_view(), name="device-unregister"),
    path("", NotificationListEndpoint.as_view(), name="notification-list"),
    path("read-all/", NotificationReadAllEndpoint.as_view(), name="notification-read-all"),
    path("<int:notification_id>/", NotificationReadEndpoint.as_view(), name="notification-read"),
]
