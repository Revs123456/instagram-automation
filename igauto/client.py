"""Thin wrapper around the Instagram Graph API (Instagram Login flavour).

Docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import requests

BASE_URL = "https://graph.instagram.com"


class GraphAPIError(RuntimeError):
    def __init__(self, status: int, payload: dict[str, Any]):
        err = payload.get("error", {}) if isinstance(payload, dict) else {}
        self.status = status
        self.code = err.get("code")
        self.subcode = err.get("error_subcode")
        self.message = err.get("message", str(payload))
        super().__init__(f"[{status}] code={self.code} {self.message}")


class InstagramClient:
    def __init__(
        self,
        access_token: str,
        ig_user_id: str,
        graph_version: str = "v23.0",
        session: requests.Session | None = None,
        max_retries: int = 3,
    ):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self.base = f"{BASE_URL}/{graph_version}"
        self.session = session or requests.Session()
        self.max_retries = max_retries

    # -- low level -------------------------------------------------------
    def _request(self, method: str, path: str, *, params=None, json=None) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        params = dict(params or {})
        if "access_token=" not in url:
            params.setdefault("access_token", self.access_token)

        for attempt in range(self.max_retries + 1):
            resp = self.session.request(method, url, params=params, json=json, timeout=30)
            try:
                payload = resp.json()
            except ValueError:
                payload = {"error": {"message": resp.text}}
            if resp.status_code < 400:
                return payload
            # Retry on transient server errors / throttling.
            retryable = resp.status_code >= 500 or (
                isinstance(payload, dict) and payload.get("error", {}).get("code") in (4, 17, 32, 613)
            )
            if retryable and attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue
            raise GraphAPIError(resp.status_code, payload)
        raise AssertionError("unreachable")

    def get(self, path: str, **params) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None, **params) -> dict[str, Any]:
        return self._request("POST", path, params=params, json=json)

    def paginate(self, path: str, **params) -> Iterator[dict[str, Any]]:
        page = self.get(path, **params)
        while True:
            yield from page.get("data", [])
            nxt = page.get("paging", {}).get("next")
            if not nxt:
                return
            page = self._request("GET", nxt)

    # -- account ---------------------------------------------------------
    def me(self) -> dict[str, Any]:
        return self.get(
            "me", fields="user_id,username,account_type,followers_count,follows_count,media_count"
        )

    def account_insights(self, metrics: list[str], since: int, until: int, **extra) -> list[dict]:
        return self.get(
            f"{self.ig_user_id}/insights",
            metric=",".join(metrics),
            period="day",
            since=since,
            until=until,
            **extra,
        ).get("data", [])

    # -- media -----------------------------------------------------------
    def iter_media(self, limit: int = 50) -> Iterator[dict[str, Any]]:
        fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
        return self.paginate(f"{self.ig_user_id}/media", fields=fields, limit=limit)

    def media_insights(self, media_id: str, metrics: list[str]) -> list[dict]:
        return self.get(f"{media_id}/insights", metric=",".join(metrics)).get("data", [])

    # -- comments & messaging --------------------------------------------
    def reply_to_comment(self, comment_id: str, text: str) -> dict[str, Any]:
        """Public reply under a comment."""
        return self.post(f"{comment_id}/replies", message=text)

    def private_reply(self, comment_id: str, text: str) -> dict[str, Any]:
        """Send a DM to the person who left the comment.

        Instagram allows ONE private reply per comment, within 7 days of it.
        """
        return self.post(
            f"{self.ig_user_id}/messages",
            json={"recipient": {"comment_id": comment_id}, "message": {"text": text}},
        )

    def send_message(self, igsid: str, text: str) -> dict[str, Any]:
        """Regular DM; only allowed inside the 24h window after the user messaged you."""
        return self.post(
            f"{self.ig_user_id}/messages",
            json={"recipient": {"id": igsid}, "message": {"text": text}},
        )

    # -- token -----------------------------------------------------------
    def refresh_token(self) -> dict[str, Any]:
        """Extend a long-lived token by 60 days (token must be >24h old)."""
        return self._request(
            "GET",
            f"{BASE_URL}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": self.access_token},
        )
