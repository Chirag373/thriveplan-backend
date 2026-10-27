from rest_framework import serializers

from .models import Subtask, Task


class TaskListQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    status = serializers.ChoiceField(choices=Task.Status.choices, required=False)
    completed = serializers.BooleanField(required=False)
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


class SubtaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subtask
        fields = ("id", "title", "completed")
        read_only_fields = fields


class TaskSerializer(serializers.ModelSerializer):
    completed = serializers.BooleanField(read_only=True)
    time = serializers.SerializerMethodField()
    subtasks = SubtaskSerializer(many=True, read_only=True)

    def get_time(self, task):
        hour = task.time.hour
        return f"{hour % 12 or 12}:{task.time.minute:02d} {'AM' if hour < 12 else 'PM'}"

    class Meta:
        model = Task
        fields = (
            "id",
            "title",
            "notes",
            "status",
            "subtasks",
            "date",
            "time",
            "category",
            "reminder",
            "completed",
            "period",
            "dashboard",
        )
        read_only_fields = fields


class TaskWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    date = serializers.DateField(input_formats=["%Y-%m-%d"])
    time = serializers.TimeField(input_formats=["%H:%M", "%I:%M %p"])
    notes = serializers.CharField(allow_blank=True, max_length=10000, required=False)
    category = serializers.CharField(allow_blank=True, max_length=100, required=False)
    status = serializers.ChoiceField(choices=Task.Status.choices, required=False)
    completed = serializers.BooleanField(required=False)
    reminder = serializers.BooleanField(required=False)
    dashboard = serializers.BooleanField(required=False)
    period = serializers.ChoiceField(
        choices=("Morning", "Afternoon", "Evening"), allow_blank=True, required=False
    )

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field cannot be written." for key in sorted(unknown)}
            )
        if not validated:
            raise serializers.ValidationError(
                {"non_field_errors": ["Provide at least one task field."]}
            )
        return validated

    def validate(self, attrs):
        if "completed" in attrs:
            completed = attrs.pop("completed")
            if "status" in attrs and (attrs["status"] == Task.Status.COMPLETED) != completed:
                raise serializers.ValidationError({"completed": "Must agree with status."})
            if "status" not in attrs:
                attrs["status"] = Task.Status.COMPLETED if completed else Task.Status.PENDING
        return attrs


class SubtaskWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    completed = serializers.BooleanField(required=False)

    def to_internal_value(self, data):
        validated = super().to_internal_value(data)
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: "This field cannot be written." for key in sorted(unknown)}
            )
        if not validated:
            raise serializers.ValidationError({"non_field_errors": ["Provide title or completed."]})
        return validated
