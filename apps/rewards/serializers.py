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
