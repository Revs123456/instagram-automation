"""Plain-text reports over the stored insights."""

from __future__ import annotations

import re
import sqlite3


def _fmt(v) -> str:
    return "-" if v is None else f"{v:,}" if isinstance(v, int) else str(v)


def _table(headers: list[str], rows: list[list]) -> str:
    cells = [headers] + [[_fmt(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    numeric = [all(re.fullmatch(r"[-+\d.,]+", r[i]) for r in cells[1:]) for i in range(len(headers))]
    lines = ["  ".join(c.rjust(w) if numeric[i] else c.ljust(w) for i, (c, w) in enumerate(zip(r, widths)))
             for r in cells]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def daily_report(conn: sqlite3.Connection, days: int = 30) -> str:
    rows = conn.execute(
        "SELECT day, follows, unfollows, reach, views, profile_views FROM daily_account "
        "WHERE follows IS NOT NULL OR unfollows IS NOT NULL ORDER BY day DESC LIMIT ?", (days,)
    ).fetchall()[::-1]
    if not rows:
        return "No daily data yet. Run: python -m igauto sync"

    out = []
    tf = tu = 0
    for r in rows:
        f, u = r["follows"] or 0, r["unfollows"] or 0
        tf, tu = tf + f, tu + u
        out.append([r["day"], f, u, f - u, r["reach"], r["views"], r["profile_views"]])
    text = _table(["day", "follows", "unfollows", "net", "reach", "views", "profile_views"], out)
    n = len(rows)
    text += (f"\n\nTotal over {n} days: +{tf:,} follows, -{tu:,} unfollows, net {tf - tu:+,}"
             f"  (avg {tf / n:.0f} in / {tu / n:.0f} out per day)")
    return text


def reels_report(conn: sqlite3.Connection, limit: int = 25, sort: str = "follows") -> str:
    sort_col = {"follows": "follows", "views": "views", "comments": "comments", "saves": "saved"}.get(sort, "follows")
    rows = conn.execute(
        f"""
        SELECT m.posted_at, m.caption, i.views, i.likes, i.comments, i.saved, i.shares, i.follows
        FROM media m
        JOIN media_insights i ON i.media_id = m.media_id
        WHERE i.fetched_day = (SELECT MAX(fetched_day) FROM media_insights WHERE media_id = m.media_id)
        ORDER BY COALESCE(i.{sort_col}, -1) DESC
        LIMIT ?
        """, (limit,)
    ).fetchall()
    if not rows:
        return "No reel data yet. Run: python -m igauto sync"

    out = []
    for r in rows:
        views = r["views"] or 0
        per_k = (lambda v: f"{1000 * v / views:.1f}" if views and v is not None else "-")
        caption = (r["caption"] or "").replace("\n", " ")[:38]
        out.append([r["posted_at"][:10], caption, views, r["likes"], r["comments"], r["saved"],
                    r["shares"], r["follows"], per_k(r["follows"]), per_k(r["comments"])])
    return _table(["posted", "caption", "views", "likes", "comments", "saves", "shares",
                   "follows", "fol/1K", "com/1K"], out)


def dm_report(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT keyword, status, COUNT(*) AS n FROM processed_comments GROUP BY keyword, status "
        "ORDER BY n DESC"
    ).fetchall()
    if not rows:
        return "No auto-DMs yet."
    return _table(["keyword", "status", "count"], [[r["keyword"] or "-", r["status"], r["n"]] for r in rows])
