from django.urls import path

from .views import (
    ActivityCompletionEndpoint,
    ActivitySessionEndpoint,
    GameCatalogEndpoint,
    RewardsSummaryEndpoint,
)

urlpatterns = [
    path("summary/", RewardsSummaryEndpoint.as_view(), name="rewards-summary"),
]


for activity in ("breathing", "puzzles", "quizzes", "workouts", "reading"):
    urlpatterns += [
        path(
            f"{activity}/sessions/",
            ActivitySessionEndpoint.as_view(),
            {"activity": activity},
            name=f"rewards-{activity}-sessions",
        ),
        path(
            f"{activity}/sessions/<uuid:session_id>/complete/",
            ActivityCompletionEndpoint.as_view(),
            {"activity": activity},
            name=f"rewards-{activity}-complete",
        ),
    ]
for activity in ("puzzles", "quizzes"):
    urlpatterns.append(
        path(
            f"{activity}/",
            GameCatalogEndpoint.as_view(),
            {"activity": activity},
            name=f"rewards-{activity}-catalog",
        )
    )
