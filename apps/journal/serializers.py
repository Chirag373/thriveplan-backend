from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from .models import JournalEntry, JournalTemplate


class JournalEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = ("id", "mood", "thoughts", "date")
        read_only_fields = fields


class AwareDateTimeField(serializers.DateTimeField):
    def enforce_timezone(self, value):
        if isinstance(value, datetime) and timezone.is_naive(value):
            raise serializers.ValidationError("Include a timezone offset or Z in the date.")
        return super().enforce_timezone(value)


class JournalEntryWriteSerializer(serializers.Serializer):
    thoughts = serializers.CharField(max_length=10000)
    mood = serializers.ChoiceField(
        choices=JournalEntry.Mood.choices, allow_null=True, required=False
    )
    date = AwareDateTimeField(required=False)

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field cannot be written." for key in sorted(unknown)}
            )
        if not validated:
            raise serializers.ValidationError(
                {"non_field_errors": ["Provide at least one entry field."]}
            )
        return validated


class JournalQuerySerializer(serializers.Serializer):
    mood = serializers.ChoiceField(choices=JournalEntry.Mood.choices, required=False)
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)

    def to_internal_value(self, data):
        validated = super().to_internal_value(data.dict())
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "Unsupported filter." for key in sorted(unknown)}
            )
        for key in data:
            if len(data.getlist(key)) != 1:
                raise serializers.ValidationError({key: "Provide this filter only once."})
        return validated


class JournalTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalTemplate
        fields = ("id", "title", "description", "prompt", "icon", "colors")
        read_only_fields = fields


class JournalTranscriptionSerializer(serializers.Serializer):
    audio = serializers.FileField(allow_empty_file=False)
    language = serializers.RegexField(r"^[a-z]{2,3}$", required=False)

    def to_internal_value(self, data):
        for field in data:
            if field not in self.fields:
                raise serializers.ValidationError({field: "Unsupported field."})
            if hasattr(data, "getlist") and len(data.getlist(field)) != 1:
                raise serializers.ValidationError({field: "Provide this field only once."})
        return super().to_internal_value(data)

    def validate_audio(self, value):
        from pathlib import Path

        from django.conf import settings

        if value.size > settings.WHISPER_MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("The recording exceeds the upload size limit.")
        if Path(value.name).suffix.lower() not in {
            ".wav",
            ".mp3",
            ".m4a",
            ".mp4",
            ".webm",
            ".ogg",
            ".flac",
        }:
            raise serializers.ValidationError("Use WAV, MP3, M4A, MP4, WebM, OGG or FLAC audio.")
        return value
