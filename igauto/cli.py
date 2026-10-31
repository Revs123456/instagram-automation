"""Command line entry point: python -m igauto <command>."""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, reports
from .client import InstagramClient
from .config import Config


def _setup(cfg: Config):
    client = InstagramClient(cfg.access_token, cfg.ig_user_id, cfg.graph_version)
    conn = db.connect(cfg.db_path)
    return client, conn


def cmd_whoami(cfg, args):
    client, _ = _setup(cfg)
    for k, v in client.me().items():
        print(f"{k:16} {v}")


def cmd_sync(cfg, args):
    from .insights import sync_account, sync_media
    client, conn = _setup(cfg)
    print(f"Syncing last {args.days} days of account insights...")
    sync_account(client, conn, days=args.days)
    print(f"Syncing reels/posts from the last {args.media_days} days...")
    n = sync_media(client, conn, days=args.media_days)
    print(f"Done: {n} media updated. Try: python -m igauto report daily")


def cmd_report(cfg, args):
    conn = db.connect(cfg.db_path)
    if args.kind == "daily":
        print(reports.daily_report(conn, days=args.days))
    elif args.kind == "reels":
        print(reports.reels_report(conn, limit=args.limit, sort=args.sort))
    else:
        print(reports.dm_report(conn))


def cmd_serve(cfg, args):
    from .rules import RuleSet
    from .webhook import create_app
    if not cfg.app_secret:
        print("WARNING: IG_APP_SECRET not set - webhook signatures are NOT verified.")
    client, conn = _setup(cfg)
    rules = RuleSet.load(cfg.rules_path)
    print(f"Loaded {len(rules.rules)} rule(s) from {cfg.rules_path}")
    create_app(cfg, client, conn, rules).run(host=args.host, port=args.port)


def cmd_retry(cfg, args):
    from .autodm import retry_pending
    from .rules import RuleSet
    client, conn = _setup(cfg)
    print(retry_pending(client, conn, RuleSet.load(cfg.rules_path)) or "Nothing to retry.")


def cmd_refresh_token(cfg, args):
    client, _ = _setup(cfg)
    res = client.refresh_token()
    token = res["access_token"]
    expires = datetime.now(timezone.utc) + timedelta(seconds=res.get("expires_in", 0))
    env = Path(".env")
    if env.is_file():
        text = env.read_text()
        new = re.sub(r"^IG_ACCESS_TOKEN=.*$", f"IG_ACCESS_TOKEN={token}", text, flags=re.M)
        env.write_text(new)
        print(f"Token refreshed and saved to .env (expires {expires:%Y-%m-%d}).")
    else:
        print(f"New token (expires {expires:%Y-%m-%d}):\n{token}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="igauto", description="Instagram insights + comment auto-DM")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="check the token and show account info").set_defaults(func=cmd_whoami)

    s = sub.add_parser("sync", help="fetch insights into the local database")
    s.add_argument("--days", type=int, default=30, help="days of follows/unfollows (max 30)")
    s.add_argument("--media-days", type=int, default=60, help="reels posted within N days")
    s.set_defaults(func=cmd_sync)

    r = sub.add_parser("report", help="print a report")
    r.add_argument("kind", choices=["daily", "reels", "dms"])
    r.add_argument("--days", type=int, default=30)
    r.add_argument("--limit", type=int, default=25)
    r.add_argument("--sort", choices=["follows", "views", "comments", "saves"], default="follows")
    r.set_defaults(func=cmd_report)

    sv = sub.add_parser("serve", help="run the webhook server for comment auto-DMs")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(func=cmd_serve)

    sub.add_parser("retry", help="resend rate-limited/failed DMs (within 7 days)").set_defaults(func=cmd_retry)
    sub.add_parser("refresh-token", help="extend the long-lived token by 60 days").set_defaults(
        func=cmd_refresh_token)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose or args.cmd == "serve" else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args.func(Config.from_env(), args)


if __name__ == "__main__":
    main()
