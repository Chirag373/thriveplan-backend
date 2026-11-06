from django.urls import path

from .views import RewardsSummaryEndpoint

urlpatterns = [
    path("summary/", RewardsSummaryEndpoint.as_view(), name="rewards-summary"),
]
