"""Handle a comment event: match keyword, send private-reply DM, optional public reply."""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from .client import GraphAPIError, InstagramClient
from .rules import RuleSet

log = logging.getLogger(__name__)
_lock = threading.Lock()


def _dms_last_hour(conn: sqlite3.Connection) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    return conn.execute(
        "SELECT COUNT(*) FROM processed_comments WHERE status='sent' AND created_at >= ?", (since,)
    ).fetchone()[0]


def _finish(conn, comment_id, status, detail=""):
    conn.execute("UPDATE processed_comments SET status=?, detail=? WHERE comment_id=?",
                 (status, detail[:500], comment_id))
    conn.commit()


def handle_comment(client: InstagramClient, conn: sqlite3.Connection, rules: RuleSet,
                   comment: dict) -> str:
    """Process one `comments` webhook value. Returns the resulting status."""
    comment_id = comment.get("id")
    text = comment.get("text") or ""
    sender = comment.get("from") or {}
    media_id = (comment.get("media") or {}).get("id")

    if not comment_id:
        return "ignored"
    if sender.get("id") == client.ig_user_id:
        return "ignored"  # our own comment / public reply
    if comment.get("parent_id"):
        return "ignored"  # replies inside a thread

    match = rules.match(text, media_id)
    if not match:
        return "no_match"
    rule, keyword = match

    with _lock:
        # Claim the comment first so webhook retries never double-DM.
        cur = conn.execute(
            "INSERT OR IGNORE INTO processed_comments (comment_id, media_id, user_id, username, keyword, status)"
            " VALUES (?,?,?,?,?, 'pending')",
            (comment_id, media_id, sender.get("id"), sender.get("username"), keyword),
        )
        conn.commit()
        if cur.rowcount == 0:
            return "duplicate"
        if _dms_last_hour(conn) >= rules.hourly_dm_cap:
            _finish(conn, comment_id, "rate_limited", "hourly cap reached; run `python -m igauto retry`")
            return "rate_limited"

    return send_for_comment(client, conn, rule, comment_id, sender.get("username", ""))


def send_for_comment(client, conn, rule, comment_id: str, username: str) -> str:
    try:
        client.private_reply(comment_id, rule.render_dm(username))
    except GraphAPIError as e:
        log.warning("private reply failed for %s: %s", comment_id, e)
        _finish(conn, comment_id, "failed", str(e))
        return "failed"

    _finish(conn, comment_id, "sent")
    public = rule.pick_public_reply(username)
    if public:
        try:
            client.reply_to_comment(comment_id, public)
        except GraphAPIError as e:  # the DM already went out; just log it
            log.warning("public reply failed for %s: %s", comment_id, e)
    return "sent"


def retry_pending(client: InstagramClient, conn: sqlite3.Connection, rules: RuleSet) -> dict[str, int]:
    """Re-send DMs that were rate limited or failed, if still inside the 7-day window."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT comment_id, keyword, username FROM processed_comments "
        "WHERE status IN ('rate_limited','failed') AND created_at >= ? ORDER BY created_at",
        (cutoff,),
    ).fetchall()
    results: dict[str, int] = {}
    for r in rows:
        if _dms_last_hour(conn) >= rules.hourly_dm_cap:
            results["still_capped"] = results.get("still_capped", 0) + 1
            continue
        rule = next((ru for ru in rules.rules if r["keyword"] in ru.keywords), None)
        if rule is None:
            continue
        status = send_for_comment(client, conn, rule, r["comment_id"], r["username"] or "")
        results[status] = results.get(status, 0) + 1
    return results
