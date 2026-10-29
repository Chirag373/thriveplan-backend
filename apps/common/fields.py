from django.utils import timezone
from rest_framework import serializers


class AwareDateTimeField(serializers.DateTimeField):
    def enforce_timezone(self, value):
        if timezone.is_naive(value):
            raise serializers.ValidationError("Include a timezone offset or Z in the date.")
        return super().enforce_timezone(value)
