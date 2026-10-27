from django.urls import include, path

urlpatterns = [
    path("api/v1/accounts/", include("apps.accounts.urls")),
    path("api/v1/planner/", include("apps.planner.urls")),
]
