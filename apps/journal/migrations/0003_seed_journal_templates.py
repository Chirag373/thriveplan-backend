from django.db import migrations

TEMPLATES = [
    {
        "id": "my-day",
        "title": "My Day",
        "description": "Capture your\ndaily experience",
        "icon": "☀️",
        "colors": ["#FFF8E7", "#FFF2DC"],
        "prompt": "What made today meaningful?",
        "position": 0,
    },
    {
        "id": "gratitude",
        "title": "Gratitude",
        "description": "Focus on the\ngood things",
        "icon": "❤️",
        "colors": ["#FFF0F4", "#FFEAF0"],
        "prompt": "What are three things you feel grateful for today?",
        "position": 1,
    },
    {
        "id": "wins",
        "title": "Today’s Wins",
        "description": "Celebrate your\nprogress",
        "icon": "🏆",
        "colors": ["#EAF8FF", "#E1F3FF"],
        "prompt": "What small wins would you like to celebrate today?",
        "position": 2,
    },
    {
        "id": "mood",
        "title": "Mood Journal",
        "description": "Explore your\nfeelings",
        "icon": "🙂",
        "colors": ["#EAFDF4", "#DFF9EC"],
        "prompt": "How are you feeling, and what might be behind that feeling?",
        "position": 3,
    },
    {
        "id": "goals",
        "title": "Goals",
        "description": "Reflect on your\ngrowth and goals",
        "icon": "🎯",
        "colors": ["#F5ECFF", "#EEE5FC"],
        "prompt": "What is one step you can take toward a goal that matters to you?",
        "position": 4,
    },
    {
        "id": "reflection",
        "title": "Reflection",
        "description": "Look deeper\ninto your thoughts",
        "icon": "🌱",
        "colors": ["#E8F7FF", "#DEF1FF"],
        "prompt": "What did you learn about yourself today?",
        "position": 5,
    },
    {
        "id": "self-care",
        "title": "Self-Care",
        "description": "Track your\nwellbeing journey",
        "icon": "🪷",
        "colors": ["#F8EBFF", "#F0E5FC"],
        "prompt": "How did you care for yourself today, and what do you need next?",
        "position": 6,
    },
    {
        "id": "weekend",
        "title": "Weekend\nReflection",
        "description": "Look back and\nrecharge",
        "icon": "🏝️",
        "colors": ["#E8F7FF", "#DFF2FF"],
        "prompt": "What would you like to carry forward from this week, and what can you let go of?",
        "position": 7,
    },
]


def seed_templates(apps, schema_editor):
    template = apps.get_model("journal", "JournalTemplate")
    for values in TEMPLATES:
        template.objects.using(schema_editor.connection.alias).get_or_create(
            id=values["id"], defaults={key: value for key, value in values.items() if key != "id"}
        )


class Migration(migrations.Migration):
    dependencies = [("journal", "0002_journaltemplate")]
    # Preserve content on rollback; removing the model migration drops its table.
    operations = [migrations.RunPython(seed_templates, migrations.RunPython.noop)]
