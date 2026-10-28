from django.urls import include, path

urlpatterns = [
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/insights/", include("apps.insights.urls")),
    path("api/v1/wellness/", include("apps.wellness.urls")),
    path("api/v1/journal/", include("apps.journal.urls")),
    path("api/v1/accounts/", include("apps.accounts.urls")),
    path("api/v1/planner/", include("apps.planner.urls")),
]
