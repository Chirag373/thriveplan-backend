from django.urls import path

from .views import (
    JournalEntryDetailEndpoint,
    JournalEntryListEndpoint,
    JournalTemplateDetailEndpoint,
    JournalTemplateListEndpoint,
)

urlpatterns = [
    path(
        "templates/<slug:template_id>/",
        JournalTemplateDetailEndpoint.as_view(),
        name="journal-template-detail",
    ),
    path("templates/", JournalTemplateListEndpoint.as_view(), name="journal-template-list"),
    path("entries/", JournalEntryListEndpoint.as_view(), name="journal-entry-list"),
    path(
        "entries/<int:entry_id>/", JournalEntryDetailEndpoint.as_view(), name="journal-entry-detail"
    ),
]
