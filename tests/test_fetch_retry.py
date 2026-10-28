"""Retry / backoff behaviour of scraper.fetch (backoff collapses to ~ms under pytest)."""

import requests

from scraper import fetch


class FakeResp:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.ok = status_code < 400
        self.text = f"body {status_code}"


class FakeSession:
    """Records calls and replays a scripted list of results (a status int, or an
    exception instance to raise)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        item = self.script.pop(0) if self.script else self.script_default
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)

    script_default = 200


def test_success_first_try_makes_one_call():
    sess = FakeSession([200])
    resp = fetch.request("GET", "http://x", session=sess)
    assert resp.status_code == 200
    assert sess.calls == 1


def test_retries_a_503_then_succeeds():
    sess = FakeSession([503, 200])
    resp = fetch.request("GET", "http://x", session=sess, label="jobs query")
    assert resp.status_code == 200
    assert sess.calls == 2


def test_retries_a_connection_error_then_succeeds():
    sess = FakeSession([requests.ConnectionError("boom"), 200])
    resp = fetch.request("GET", "http://x", session=sess)
    assert resp.status_code == 200
    assert sess.calls == 2


def test_does_not_retry_a_404():
    sess = FakeSession([404, 200])
    resp = fetch.request("GET", "http://x", session=sess)
    assert resp.status_code == 404
    assert sess.calls == 1


def test_gives_up_after_max_attempts_and_returns_the_last_5xx():
    # under pytest MAX_ATTEMPTS == 3
    sess = FakeSession([500, 500, 500])
    resp = fetch.request("GET", "http://x", session=sess)
    assert resp.status_code == 500
    assert sess.calls == fetch.MAX_ATTEMPTS


def test_raises_the_last_exception_when_every_attempt_errors():
    sess = FakeSession([requests.Timeout("t1"), requests.Timeout("t2"), requests.Timeout("t3")])
    try:
        fetch.request("GET", "http://x", session=sess)
    except requests.Timeout as exc:
        assert "t3" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a Timeout")
    assert sess.calls == fetch.MAX_ATTEMPTS


def test_backoff_delay_honours_retry_after_and_is_bounded():
    assert fetch.backoff_delay(0, "0") == 0.0
    # numeric Retry-After is clamped to MAX_DELAY
    assert fetch.backoff_delay(0, "9999") == fetch.MAX_DELAY
    # full jitter: within [0, ceiling]
    for attempt in range(4):
        d = fetch.backoff_delay(attempt)
        assert 0.0 <= d <= fetch.MAX_DELAY
