from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.rewards.services import award_journal_entry

from .models import JournalEntry, JournalTemplate


def list_entries(*, user, filters):
    entries = JournalEntry.objects.filter(owner=user)
    if "mood" in filters:
        entries = entries.filter(mood=filters["mood"])
    return entries


@transaction.atomic
def create_entry(*, user, data):
    entry = JournalEntry.objects.create(owner=user, **data)
    entry.points_awarded = award_journal_entry(user=user)
    return entry


@transaction.atomic
def update_entry(*, user, entry_id, data):
    entry = get_object_or_404(JournalEntry.objects.select_for_update(), owner=user, pk=entry_id)
    for field, value in data.items():
        setattr(entry, field, value)
    entry.save(update_fields=[*data, "updated_at"])
    return entry


@transaction.atomic
def delete_entry(*, user, entry_id):
    entry = get_object_or_404(JournalEntry.objects.select_for_update(), owner=user, pk=entry_id)
    entry.delete()


def list_templates():
    return JournalTemplate.objects.filter(is_active=True)


def transcribe_entry_audio(*, data):
    from apps.common.whisper import transcribe

    return transcribe(audio=data["audio"], language=data.get("language"))
