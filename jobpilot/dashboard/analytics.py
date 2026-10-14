"""Application reporting with UTC storage and user-local calendar boundaries."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import csv
import io
import pytz


def utc_iso(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def applications(
    database, *, platform=None, search="", start=None, end=None, tz="Asia/Kolkata"
):
    zone = pytz.timezone(tz)
    for value in (start, end):
        if value:
            datetime.strptime(value, "%Y-%m-%d")
    if start and end and start > end:
        raise ValueError("Start date must precede end date")
    with closing(database._get_connection()) as conn:
        rows = conn.execute("""SELECT j.*, COALESCE(NULLIF(j.applied_at,''),
            (SELECT MAX(timestamp) FROM application_log WHERE job_id=j.id
             AND action IN ('applied','manual_applied','status_change:applied'))) AS event_time
            FROM jobs j WHERE status='applied' ORDER BY event_time DESC, j.id DESC""").fetchall()
    result = []
    for row in rows:
        data = dict(row)
        if platform and data["platform"] != platform:
            continue
        if search.lower() not in (data["title"] + " " + data["company"]).lower():
            continue
        stamp = utc_iso(data.pop("event_time"))
        local_date = (
            datetime.fromisoformat(stamp).astimezone(zone).date().isoformat()
            if stamp
            else None
        )
        if (start or end) and (
            not local_date
            or (start and local_date < start)
            or (end and local_date > end)
        ):
            continue
        result.append(
            {
                "id": data["id"],
                "title": data["title"],
                "company": data["company"],
                "platform": data["platform"],
                "url": data["url"],
                "applied_at": stamp,
                "local_date": local_date,
                "match_score": data["match_score"],
                "location": data["location"],
                "status": "applied",
                "date_unknown": stamp is None,
            }
        )
    return result


def overview(database, days=14, tz="Asia/Kolkata"):
    zone = pytz.timezone(tz)
    today = datetime.now(zone).date()
    dates = [(today - timedelta(days=days - i - 1)).isoformat() for i in range(days)]
    counts = dict.fromkeys(dates, 0)
    rows = applications(database, tz=tz)
    platform_counts = {}
    today_count = 0
    for row in rows:
        date = row["local_date"]
        if date in counts:
            counts[date] += 1
        today_count += date == today.isoformat()
        platform_counts[row["platform"]] = platform_counts.get(row["platform"], 0) + 1
    stats = database.get_stats()
    with closing(database._get_connection()) as conn:
        events = [
            dict(row)
            for row in conn.execute("""SELECT a.id, a.job_id, a.action, a.details, a.timestamp,
            j.title, j.company, j.platform FROM application_log a JOIN jobs j ON j.id=a.job_id
            ORDER BY a.id DESC LIMIT 20""")
        ]
    for event in events:
        event["timestamp"] = utc_iso(event["timestamp"])
        # Keep server filesystem paths out of UI responses.
        event["details"] = event["details"].split("; Screenshot:")[0]
    return {
        "total_applications": len(rows),
        "applied_today": today_count,
        "period_applications": sum(counts.values()),
        "total_jobs": stats["total_jobs"],
        "needs_review": stats["by_status"].get("review", 0),
        "shortlisted": stats["by_status"].get("shortlisted", 0),
        "matched": stats["by_status"].get("matched", 0),
        "average_match": stats["avg_match_score"],
        "by_status": stats["by_status"],
        "by_platform": platform_counts,
        "timezone": tz,
        "chart": [{"date": day, "count": count} for day, count in counts.items()],
        "recent": rows[:5],
        "activity": events,
        "undated_applications": sum(row["date_unknown"] for row in rows),
    }


def csv_export(rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Role",
            "Company",
            "Platform",
            "Applied at (UTC)",
            "Local date",
            "Match score",
            "URL",
        ]
    )

    def cell(value):
        text = str(value or "")
        return (
            "'" + text
            if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
            else text
        )

    for row in rows:
        writer.writerow(
            [
                cell(row[key])
                for key in (
                    "title",
                    "company",
                    "platform",
                    "applied_at",
                    "local_date",
                    "match_score",
                    "url",
                )
            ]
        )
    return buffer.getvalue()
