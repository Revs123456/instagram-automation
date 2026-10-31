"""Fetch account- and reel-level insights into SQLite."""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone

from .client import GraphAPIError, InstagramClient
from .db import upsert

log = logging.getLogger(__name__)

# Account metrics that support metric_type=total_value for a single day.
ACCOUNT_TOTAL_METRICS = ["reach", "views", "profile_views", "accounts_engaged"]

# Reel/post metrics. "follows" and "profile_visits" are not available for
# every media type, so they are requested optimistically with a fallback.
MEDIA_BASE_METRICS = ["views", "reach", "likes", "comments", "shares", "saved"]
MEDIA_EXTRA_METRICS = ["follows", "profile_visits"]


def _day_bounds(day: date) -> tuple[int, int]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def _total_value(metric: dict) -> int | None:
    tv = metric.get("total_value")
    if tv is not None:
        return tv.get("value")
    values = metric.get("values") or []
    return values[0].get("value") if values else None


def parse_follows_unfollows(data: list[dict]) -> tuple[int | None, int | None]:
    """follows_and_unfollows broken down by follow_type.

    FOLLOWER     -> accounts that followed you that day
    NON_FOLLOWER -> accounts that unfollowed you that day
    """
    follows = unfollows = None
    for metric in data:
        if metric.get("name") != "follows_and_unfollows":
            continue
        for bd in (metric.get("total_value") or {}).get("breakdowns", []):
            for res in bd.get("results", []):
                dim = (res.get("dimension_values") or [""])[0]
                if dim == "FOLLOWER":
                    follows = res.get("value")
                elif dim == "NON_FOLLOWER":
                    unfollows = res.get("value")
        if follows is None and unfollows is None:
            # No breakdown rows: Instagram omits zero buckets.
            follows, unfollows = 0, 0
    return follows, unfollows


def sync_account_day(client: InstagramClient, conn: sqlite3.Connection, day: date) -> dict:
    since, until = _day_bounds(day)
    row: dict = {"day": day.isoformat()}

    try:
        data = client.account_insights(
            ["follows_and_unfollows"], since, until,
            metric_type="total_value", breakdown="follow_type",
        )
        row["follows"], row["unfollows"] = parse_follows_unfollows(data)
    except GraphAPIError as e:
        log.warning("follows_and_unfollows unavailable for %s: %s", day, e.message)

    try:
        data = client.account_insights(ACCOUNT_TOTAL_METRICS, since, until, metric_type="total_value")
        for m in data:
            row[m["name"]] = _total_value(m)
    except GraphAPIError as e:
        log.warning("account metrics unavailable for %s: %s", day, e.message)

    upsert(conn, "daily_account", row, keys=("day",))
    return row


def sync_account(client: InstagramClient, conn: sqlite3.Connection, days: int = 30,
                 today: date | None = None) -> list[dict]:
    """Fetch the last `days` complete days (yesterday backwards) plus a follower snapshot."""
    today = today or datetime.now(timezone.utc).date()
    rows = [sync_account_day(client, conn, today - timedelta(days=i)) for i in range(days, 0, -1)]
    me = client.me()
    upsert(conn, "daily_account", {"day": today.isoformat(), "followers": me.get("followers_count")},
           keys=("day",))
    conn.commit()
    return rows


def sync_media(client: InstagramClient, conn: sqlite3.Connection, days: int = 60,
               today: date | None = None) -> int:
    """Snapshot insights for every reel/post published in the last `days` days."""
    today = today or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=days)
    no_extras: set[str] = set()  # product types that rejected follows/profile_visits
    count = 0

    for m in client.iter_media():
        posted = datetime.strptime(m["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").date()
        if posted < cutoff:
            break  # media are returned newest first
        ptype = m.get("media_product_type", "")
        upsert(conn, "media", {
            "media_id": m["id"], "posted_at": m["timestamp"], "product_type": ptype,
            "caption": (m.get("caption") or "")[:500], "permalink": m.get("permalink"),
        }, keys=("media_id",))

        metrics = MEDIA_BASE_METRICS + ([] if ptype in no_extras else MEDIA_EXTRA_METRICS)
        try:
            data = client.media_insights(m["id"], metrics)
        except GraphAPIError as e:
            if metrics == MEDIA_BASE_METRICS:
                log.warning("insights unavailable for %s: %s", m["id"], e.message)
                continue
            no_extras.add(ptype)
            try:
                data = client.media_insights(m["id"], MEDIA_BASE_METRICS)
            except GraphAPIError as e2:
                log.warning("insights unavailable for %s: %s", m["id"], e2.message)
                continue

        row = {"media_id": m["id"], "fetched_day": today.isoformat()}
        row.update({d["name"]: _total_value(d) for d in data if d["name"] in MEDIA_BASE_METRICS + MEDIA_EXTRA_METRICS})
        upsert(conn, "media_insights", row, keys=("media_id", "fetched_day"))
        count += 1

    conn.commit()
    return count
