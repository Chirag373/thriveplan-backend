from rest_framework import serializers

from .models import User, UserPreferences


class SignUpSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {
                        field: "Unexpected field. Send only name; identity comes from the Bearer token."
                        for field in sorted(unknown)
                    }
                )
        return super().to_internal_value(data)


class UserSerializer(serializers.ModelSerializer):
    onboarding_completed = serializers.BooleanField(
        source="preferences.onboarding_completed", default=False
    )

    class Meta:
        model = User
        fields = ("id", "name", "email", "email_verified", "phone_number", "onboarding_completed")
        read_only_fields = fields


class SignInSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        if data:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "Send an empty JSON object; identity comes from the Firebase Bearer token."
                    ]
                }
            )
        return validated


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        if set(data) - {"email"}:
            raise serializers.ValidationError({"non_field_errors": ["Send only email."]})
        return validated


class StrictUpdateSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "This field cannot be updated." for field in sorted(unknown)}
            )
        if not validated:
            raise serializers.ValidationError(
                {"non_field_errors": ["Provide at least one field to update."]}
            )
        return validated


class ProfileUpdateSerializer(StrictUpdateSerializer):
    name = serializers.CharField(max_length=150)


class PreferencesUpdateSerializer(StrictUpdateSerializer):
    profession = serializers.ChoiceField(
        choices=UserPreferences._meta.get_field("profession").choices, required=False
    )
    focus_areas = serializers.ListField(
        child=serializers.ChoiceField(choices=("planning", "journaling", "habits", "mindfulness")),
        allow_empty=False,
        max_length=4,
        required=False,
    )

    def validate_focus_areas(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Choose each focus area only once.")
        return value


class PreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = ("profession", "focus_areas", "onboarding_completed")
        read_only_fields = fields


class NotificationPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = ("daily_reminders", "weekly_summary")
        read_only_fields = fields


class NotificationPreferencesUpdateSerializer(StrictUpdateSerializer):
    daily_reminders = serializers.BooleanField(required=False)
    weekly_summary = serializers.BooleanField(required=False)
