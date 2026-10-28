from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404

from .models import DailyContent, Favorite, WellnessContent


def get_daily_content(*, date):
    selections = DailyContent.objects.filter(
        date=date,
        content__is_active=True,
        content__kind=F("kind"),
    ).select_related("content")
    result = {"quote": None, "song": None, "books": [], "workout": None, "joke": None}
    for selection in selections:
        if selection.kind == "book":
            result["books"].append(selection.content)
        else:
            result[selection.kind] = selection.content
    return result


def list_favorites(*, user, filters):
    favorites = Favorite.objects.filter(owner=user, content__is_active=True).select_related(
        "content"
    )
    if "kind" in filters:
        favorites = favorites.filter(content__kind=filters["kind"])
    return favorites


@transaction.atomic
def save_favorite(*, user, content_id):
    content = get_object_or_404(
        WellnessContent.objects.select_for_update(), pk=content_id, is_active=True
    )
    # Database uniqueness also protects against concurrent duplicate saves.
    return Favorite.objects.get_or_create(owner=user, content=content)


@transaction.atomic
def delete_favorite(*, user, favorite_id):
    favorite = get_object_or_404(Favorite.objects.select_for_update(), pk=favorite_id, owner=user)
    favorite.delete()
