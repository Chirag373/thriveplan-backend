from django.urls import path

from .views import NotificationListEndpoint, NotificationReadAllEndpoint, NotificationReadEndpoint

urlpatterns = [
    path("", NotificationListEndpoint.as_view(), name="notification-list"),
    path("read-all/", NotificationReadAllEndpoint.as_view(), name="notification-read-all"),
    path("<int:notification_id>/", NotificationReadEndpoint.as_view(), name="notification-read"),
]
