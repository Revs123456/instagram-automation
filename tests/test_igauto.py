import hashlib
import hmac
import json
from concurrent.futures import Executor, Future
from datetime import date

import pytest

from igauto import db, reports
from igauto.autodm import handle_comment, retry_pending
from igauto.client import GraphAPIError, InstagramClient
from igauto.config import Config
from igauto.insights import parse_follows_unfollows, sync_account, sync_media
from igauto.rules import Rule, RuleSet
from igauto.webhook import create_app, verify_signature

OWN_ID = "17840000000000001"


# --- fakes ---------------------------------------------------------------

class FakeResp:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append((method, url, params, json))
        return self.responses.pop(0)


class FakeClient:
    """Stands in for InstagramClient in autodm/insights tests."""

    def __init__(self, fail_private=False):
        self.ig_user_id = OWN_ID
        self.private, self.public = [], []
        self.fail_private = fail_private

    def private_reply(self, cid, text):
        if self.fail_private:
            raise GraphAPIError(400, {"error": {"code": 10, "message": "outside window"}})
        self.private.append((cid, text))

    def reply_to_comment(self, cid, text):
        self.public.append((cid, text))


class SyncExecutor(Executor):
    def submit(self, fn, *a, **kw):
        f = Future()
        f.set_result(fn(*a, **kw))
        return f


@pytest.fixture
def conn():
    return db.connect(":memory:")


@pytest.fixture
def rules():
    return RuleSet(rules=[
        Rule(keywords=["ROADMAP"], link="https://x/roadmap.pdf",
             dm="Hi {username}, here: {link}", public_replies=["Sent!"]),
        Rule(keywords=["SAP"], media_ids=["M2"], link="https://x/s4.pdf", dm="S4: {link}"),
        Rule(keywords=["SAP"], link="https://x/generic.pdf", dm="Generic: {link}"),
    ])


def comment(cid="C1", text="ROADMAP please", user="U1", media="M1", **kw):
    return {"id": cid, "text": text, "from": {"id": user, "username": "ravi"},
            "media": {"id": media}, **kw}


# --- client --------------------------------------------------------------

def test_client_adds_token_and_raises_graph_error():
    s = FakeSession([FakeResp(400, {"error": {"code": 100, "message": "bad metric"}})])
    c = InstagramClient("TOKEN", OWN_ID, session=s, max_retries=0)
    with pytest.raises(GraphAPIError) as e:
        c.media_insights("M1", ["views"])
    assert e.value.code == 100
    method, url, params, _ = s.calls[0]
    assert url == "https://graph.instagram.com/v23.0/M1/insights"
    assert params["access_token"] == "TOKEN" and params["metric"] == "views"


def test_client_paginates():
    s = FakeSession([
        FakeResp(200, {"data": [{"id": 1}], "paging": {"next": "https://graph.instagram.com/next?access_token=T"}}),
        FakeResp(200, {"data": [{"id": 2}]}),
    ])
    c = InstagramClient("T", OWN_ID, session=s)
    assert [m["id"] for m in c.iter_media()] == [1, 2]
    assert "access_token" not in s.calls[1][2]  # token already in the next URL


def test_private_reply_payload():
    s = FakeSession([FakeResp(200, {"recipient_id": "x"})])
    InstagramClient("T", OWN_ID, session=s).private_reply("C9", "hello")
    _, url, _, body = s.calls[0]
    assert url.endswith(f"/{OWN_ID}/messages")
    assert body == {"recipient": {"comment_id": "C9"}, "message": {"text": "hello"}}


# --- rules ---------------------------------------------------------------

def test_rule_matching_is_whole_word_case_insensitive(rules):
    assert rules.match("send the roadmap!", "M1")[1] == "ROADMAP"
    assert rules.match("roadmaps", "M1") is None
    assert rules.match("sapling", "M1") is None


def test_media_specific_rule_wins(rules):
    rule, _ = rules.match("SAP", "M2")
    assert rule.link.endswith("s4.pdf")
    rule, _ = rules.match("SAP", "M1")
    assert rule.link.endswith("generic.pdf")


# --- auto DM -------------------------------------------------------------

def test_sends_dm_and_public_reply_once(conn, rules):
    client = FakeClient()
    assert handle_comment(client, conn, rules, comment()) == "sent"
    assert client.private == [("C1", "Hi ravi, here: https://x/roadmap.pdf")]
    assert client.public == [("C1", "Sent!")]
    # Webhook retry of the same comment must not DM twice.
    assert handle_comment(client, conn, rules, comment()) == "duplicate"
    assert len(client.private) == 1


@pytest.mark.parametrize("c, expected", [
    (comment(user=OWN_ID), "ignored"),
    (comment(parent_id="P1"), "ignored"),
    (comment(text="nice video"), "no_match"),
])
def test_ignored_comments(conn, rules, c, expected):
    client = FakeClient()
    assert handle_comment(client, conn, rules, c) == expected
    assert client.private == []


def test_failed_dm_is_recorded_and_retried(conn, rules):
    assert handle_comment(FakeClient(fail_private=True), conn, rules, comment()) == "failed"
    client = FakeClient()
    assert retry_pending(client, conn, rules) == {"sent": 1}
    assert len(client.private) == 1


def test_hourly_cap(conn, rules):
    rules.hourly_dm_cap = 1
    client = FakeClient()
    assert handle_comment(client, conn, rules, comment("C1")) == "sent"
    assert handle_comment(client, conn, rules, comment("C2")) == "rate_limited"
    assert len(client.private) == 1


# --- webhook -------------------------------------------------------------

def make_app(conn, rules, client, secret="shh"):
    cfg = Config(access_token="T", ig_user_id=OWN_ID, app_secret=secret, verify_token="vt")
    return create_app(cfg, client, conn, rules, executor=SyncExecutor()).test_client()


def test_webhook_verification(conn, rules):
    app = make_app(conn, rules, FakeClient())
    ok = app.get("/webhook?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=123")
    assert ok.status_code == 200 and ok.data == b"123"
    assert app.get("/webhook?hub.mode=subscribe&hub.verify_token=no&hub.challenge=1").status_code == 403


def test_webhook_signature_and_dispatch(conn, rules):
    client = FakeClient()
    app = make_app(conn, rules, client)
    body = json.dumps({"object": "instagram", "entry": [
        {"id": OWN_ID, "changes": [{"field": "comments", "value": comment()}]}]}).encode()
    sig = "sha256=" + hmac.new(b"shh", body, hashlib.sha256).hexdigest()

    assert app.post("/webhook", data=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    r = app.post("/webhook", data=body, headers={"X-Hub-Signature-256": sig,
                                                  "Content-Type": "application/json"})
    assert r.status_code == 200
    assert client.private and client.private[0][0] == "C1"


def test_verify_signature_requires_header_when_secret_set():
    assert not verify_signature("s", b"x", None)
    assert verify_signature("", b"x", None)


# --- insights ------------------------------------------------------------

def test_parse_follows_unfollows():
    data = [{"name": "follows_and_unfollows", "total_value": {"breakdowns": [{"results": [
        {"dimension_values": ["FOLLOWER"], "value": 125},
        {"dimension_values": ["NON_FOLLOWER"], "value": 110},
    ]}]}}]
    assert parse_follows_unfollows(data) == (125, 110)
    assert parse_follows_unfollows([{"name": "follows_and_unfollows", "total_value": {}}]) == (0, 0)


class InsightsClient:
    def __init__(self):
        self.media_calls = []

    def account_insights(self, metrics, since, until, **extra):
        if metrics == ["follows_and_unfollows"]:
            return [{"name": "follows_and_unfollows", "total_value": {"breakdowns": [{"results": [
                {"dimension_values": ["FOLLOWER"], "value": 100},
                {"dimension_values": ["NON_FOLLOWER"], "value": 120}]}]}}]
        return [{"name": m, "total_value": {"value": 1000}} for m in metrics]

    def me(self):
        return {"followers_count": 93366}

    def iter_media(self):
        yield {"id": "R1", "timestamp": "2026-10-20T10:00:00+0000", "media_product_type": "REELS",
               "caption": "SAP roadmap", "permalink": "p"}
        yield {"id": "R2", "timestamp": "2026-10-19T10:00:00+0000", "media_product_type": "REELS",
               "caption": "Jobs", "permalink": "p"}
        yield {"id": "OLD", "timestamp": "2026-01-01T10:00:00+0000", "media_product_type": "REELS"}

    def media_insights(self, media_id, metrics):
        self.media_calls.append((media_id, tuple(metrics)))
        if "follows" in metrics:
            raise GraphAPIError(400, {"error": {"code": 100, "message": "unsupported metric"}})
        views = {"R1": 5000, "R2": 2000}[media_id]
        return [{"name": m, "values": [{"value": views if m == "views" else 50}]} for m in metrics]


def test_sync_and_reports(conn):
    client = InsightsClient()
    sync_account(client, conn, days=3, today=date(2026, 10, 31))
    assert sync_media(client, conn, days=60, today=date(2026, 10, 31)) == 2
    # The unsupported extra metrics are only attempted once per product type.
    assert sum("follows" in m for _, m in client.media_calls) == 1

    daily = reports.daily_report(conn)
    assert "2026-10-30" in daily and "net -60" in daily
    reels = reports.reels_report(conn, sort="views")
    assert reels.index("SAP roadmap") < reels.index("Jobs")
