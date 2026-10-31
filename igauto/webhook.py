"""Flask app receiving Instagram webhooks (comments) and triggering auto-DMs."""

from __future__ import annotations

import hashlib
import hmac
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, abort, request

from .autodm import handle_comment

log = logging.getLogger(__name__)


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not app_secret:
        return True  # signature check disabled (local testing only)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def iter_comment_events(payload: dict):
    if payload.get("object") != "instagram":
        return
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") in ("comments", "live_comments"):
                yield change.get("value") or {}


def create_app(config, client, conn, rules, executor: ThreadPoolExecutor | None = None) -> Flask:
    app = Flask(__name__)
    pool = executor or ThreadPoolExecutor(max_workers=4)

    def process(value):
        try:
            status = handle_comment(client, conn, rules, value)
            log.info("comment %s -> %s", value.get("id"), status)
        except Exception:  # never let one bad event kill the worker
            log.exception("error handling comment %s", value.get("id"))

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/webhook")
    def verify():
        if (request.args.get("hub.mode") == "subscribe"
                and config.verify_token
                and request.args.get("hub.verify_token") == config.verify_token):
            return request.args.get("hub.challenge", ""), 200
        abort(403)

    @app.post("/webhook")
    def receive():
        body = request.get_data()
        if not verify_signature(config.app_secret, body, request.headers.get("X-Hub-Signature-256")):
            abort(401)
        payload = request.get_json(silent=True) or {}
        for value in iter_comment_events(payload):
            pool.submit(process, value)  # reply 200 fast; Meta retries slow endpoints
        return "EVENT_RECEIVED", 200

    return app
