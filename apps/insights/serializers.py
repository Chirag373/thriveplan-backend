from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone
from rest_framework import serializers


class SummaryQuerySerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    end_date = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    timezone = serializers.CharField(required=False, default="UTC", max_length=100)

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Use a valid IANA timezone.") from None
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

    def validate(self, attrs):
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if (start is None) != (end is None):
            raise serializers.ValidationError("Provide both start_date and end_date.")
        if start and start > end:
            raise serializers.ValidationError("start_date must not be after end_date.")
        if end == date.max or start == date.min:
            raise serializers.ValidationError("Date range is outside supported boundaries.")
        return attrs


class ProductivityQuerySerializer(SummaryQuerySerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "start_date" not in attrs:
            end = timezone.localdate(timezone=ZoneInfo(attrs["timezone"]))
            attrs.update(start_date=end - timedelta(days=6), end_date=end)
        if (attrs["end_date"] - attrs["start_date"]).days >= 366:
            raise serializers.ValidationError("Select a range of at most 366 days.")
        return attrs
