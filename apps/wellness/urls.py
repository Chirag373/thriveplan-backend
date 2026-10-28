from django.urls import path

from .views import DailyWellnessEndpoint, FavoriteDetailEndpoint, FavoriteListEndpoint

urlpatterns = [
    path("daily/", DailyWellnessEndpoint.as_view(), name="wellness-daily"),
    path("favorites/", FavoriteListEndpoint.as_view(), name="favorite-list"),
    path("favorites/<int:favorite_id>/", FavoriteDetailEndpoint.as_view(), name="favorite-detail"),
]
