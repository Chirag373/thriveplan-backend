from django.urls import path

from .views import InsightsSummaryEndpoint, ProductivityEndpoint

urlpatterns = [
    path("summary/", InsightsSummaryEndpoint.as_view(), name="insights-summary"),
    path("productivity/", ProductivityEndpoint.as_view(), name="insights-productivity"),
]
