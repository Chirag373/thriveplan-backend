from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    unread = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "message",
            "category",
            "icon",
            "destination",
            "target_id",
            "created_at",
            "read_at",
            "unread",
        )
        read_only_fields = fields


class NotificationQuerySerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Notification.Category.choices, required=False)
    unread = serializers.BooleanField(required=False)
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


class MarkReadSerializer(serializers.Serializer):
    unread = serializers.BooleanField()

    def validate_unread(self, value):
        if value:
            raise serializers.ValidationError("Use false to mark this notification as read.")
        return value

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        if set(data) - {"unread"}:
            raise serializers.ValidationError({"non_field_errors": ["Send only unread."]})
        return validated


class ReadAllSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        if data:
            raise serializers.ValidationError({"non_field_errors": ["Send an empty JSON object."]})
        return validated
