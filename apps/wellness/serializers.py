from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import Favorite, WellnessContent


class DailyQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    timezone = serializers.CharField(required=False, default="UTC", max_length=100)

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError(
                "Use a valid IANA timezone, such as Asia/Kolkata."
            ) from None
        return value

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


class WellnessContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WellnessContent
        fields = (
            "id",
            "kind",
            "title",
            "description",
            "body",
            "creator",
            "duration_seconds",
            "media_url",
            "image_url",
        )
        read_only_fields = fields


class FavoriteCreateSerializer(serializers.Serializer):
    content_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field cannot be written." for key in sorted(unknown)}
            )
        return validated


class FavoriteSerializer(serializers.ModelSerializer):
    content = WellnessContentSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ("id", "content", "created_at")
        read_only_fields = fields


class FavoriteQuerySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=WellnessContent.Kind.choices, required=False)
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
