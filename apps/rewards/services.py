from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.journal.models import JournalEntry

from .models import PointTransaction
from .serializers import PointTransactionSerializer

MILESTONE_STEP = 300


def get_rewards_summary(*, user, filters):
    zone = ZoneInfo(filters["timezone"])
    today = timezone.localdate(timezone=zone)
    start = today - timedelta(days=6)
    lower = datetime.combine(start, time.min, tzinfo=zone)
    upper = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone)
    transactions = PointTransaction.objects.filter(owner=user, occurred_at__lt=upper)
    total = transactions.aggregate(total=Sum("points", default=0))["total"]
    daily = dict(
        transactions.filter(occurred_at__gte=lower)
        .order_by()
        .annotate(day=TruncDate("occurred_at", tzinfo=zone))
        .values("day")
        .annotate(points=Sum("points"))
        .values_list("day", "points")
    )
    # A journal streak remains current through yesterday until today's entry is written.
    journal_days = (
        JournalEntry.objects.filter(owner=user, date__lt=upper)
        .annotate(day=TruncDate("date", tzinfo=zone))
        .values_list("day", flat=True)
        .order_by("-day")
        .distinct()
    )
    streak = 0
    expected = today
    for day in journal_days.iterator():
        if not streak and day == today - timedelta(days=1):
            expected = day
        if day != expected:
            break
        streak += 1
        expected -= timedelta(days=1)
    target = (max(total, 0) // MILESTONE_STEP + 1) * MILESTONE_STEP
    return {
        "timezone": filters["timezone"],
        "date": today.isoformat(),
        "total_points": total,
        "today_points": daily.get(today, 0),
        "weekly_points": [
            {
                "date": (day := start + timedelta(days=index)).isoformat(),
                "points": daily.get(day, 0),
            }
            for index in range(7)
        ],
        "history": PointTransactionSerializer(transactions[:10], many=True).data,
        "current_streak": {"days": streak, "activity": "journal"},
        "next_milestone": {
            "target_points": target,
            "remaining_points": target - total,
            "progress_percentage": round(max(total, 0) * 100 / target, 2),
        },
    }
