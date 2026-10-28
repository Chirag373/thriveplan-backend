from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Q

from apps.journal.models import JournalEntry
from apps.planner.models import Task


def get_summary(*, user, filters):
    tasks = Task.objects.filter(owner=user)
    entries = JournalEntry.objects.filter(owner=user)
    start, end = filters.get("start_date"), filters.get("end_date")
    if start is not None:
        tasks = tasks.filter(date__range=(start, end))
        zone = ZoneInfo(filters["timezone"])
        # Local midnight boundaries preserve the requested calendar days across DST.
        lower = datetime.combine(start, time.min, tzinfo=zone)
        upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone)
        entries = entries.filter(date__gte=lower, date__lt=upper)

    task_counts = tasks.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=Task.Status.COMPLETED)),
        not_started=Count("id", filter=Q(status=Task.Status.PENDING)),
        in_progress=Count("id", filter=Q(status=Task.Status.IN_PROGRESS)),
        overdue=Count("id", filter=Q(status=Task.Status.OVERDUE)),
    )
    task_counts["pending"] = task_counts["total"] - task_counts["completed"]
    task_counts["completion_percentage"] = (
        round(task_counts["completed"] * 100 / task_counts["total"], 2)
        if task_counts["total"]
        else 0.0
    )
    journal_counts = entries.aggregate(
        total=Count("id"),
        unrecorded=Count("id", filter=Q(mood__isnull=True)),
        **{mood: Count("id", filter=Q(mood=mood)) for mood in JournalEntry.Mood.values},
    )
    return {
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "timezone": filters["timezone"],
        "tasks": task_counts,
        "journal": {
            "total_entries": journal_counts["total"],
            "moods": {mood: journal_counts[mood] for mood in JournalEntry.Mood.values},
            "unrecorded_mood": journal_counts["unrecorded"],
        },
    }


def get_productivity(*, user, filters):
    start, end = filters["start_date"], filters["end_date"]
    rows = (
        Task.objects.filter(owner=user, date__range=(start, end))
        .order_by()
        .values("date")
        .annotate(total=Count("id"), completed=Count("id", filter=Q(status=Task.Status.COMPLETED)))
    )
    by_date = {row["date"]: row for row in rows}
    days = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        counts = by_date.get(day, {"total": 0, "completed": 0})
        days.append(
            {"date": day.isoformat(), **_productivity_counts(counts["total"], counts["completed"])}
        )
    total = sum(day["total"] for day in days)
    completed = sum(day["completed"] for day in days)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": filters["timezone"],
        "summary": _productivity_counts(total, completed),
        "days": days,
    }


def _productivity_counts(total: int, completed: int) -> dict:
    return {
        "total": total,
        "completed": completed,
        "pending": total - completed,
        "completion_percentage": round(completed * 100 / total, 2) if total else 0.0,
    }
