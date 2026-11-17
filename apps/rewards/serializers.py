from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from .models import PointTransaction


class RewardsSummaryQuerySerializer(serializers.Serializer):
    timezone = serializers.CharField(required=False, default="UTC", max_length=100)

    def to_internal_value(self, data):
        for key in data:
            if key not in self.fields:
                raise serializers.ValidationError({key: "Unsupported filter."})
            if len(data.getlist(key)) != 1:
                raise serializers.ValidationError({key: "Provide this filter only once."})
        return super().to_internal_value(data.dict())

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Use a valid IANA timezone.") from None
        return value


class PointTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointTransaction
        fields = ("id", "points", "description", "occurred_at")


class StrictActivitySerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {key: "Unsupported field." for key in sorted(unknown)}
                )
        return super().to_internal_value(data)


class ActivitySessionSerializer(StrictActivitySerializer):
    request_id = serializers.UUIDField()
    target_id = serializers.CharField(max_length=100)


class ActivityCompletionSerializer(StrictActivitySerializer):
    confirmed = serializers.BooleanField(required=False, default=False)
    answers = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=100),
        max_length=100,
        required=False,
    )

    def validate_answers(self, value):
        # Do not silently coerce booleans, decimal values, or strings into game moves.
        raw = self.initial_data.get("answers", [])
        if any(type(answer) is not int for answer in raw):
            raise serializers.ValidationError("Answers must be integers.")
        return value
