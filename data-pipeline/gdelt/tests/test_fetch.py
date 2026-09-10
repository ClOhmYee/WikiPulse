"""fetch 테스트. 가짜 세션으로 네트워크 없이 돈다."""

from __future__ import annotations

import hashlib

import pytest
import requests

from gdelt import fetch

GOOD = b"PK\x03\x04" + b"payload-bytes"
GOOD_MD5 = hashlib.md5(GOOD).hexdigest()


class FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """get() 호출마다 미리 정해둔 응답/예외를 순서대로 낸다."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        item = self._outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _no_sleep(_):
    pass


def test_정상_다운로드_md5_size_검증_통과():
    sess = FakeSession([FakeResponse(200, GOOD)])
    data = fetch.download(
        "http://x/f.gkg.csv.zip",
        expected_size=len(GOOD),
        expected_md5=GOOD_MD5,
        session=sess,
        sleep=_no_sleep,
    )
    assert data == GOOD
    assert sess.calls == 1


def test_404는_GdeltNotFound_재시도안함():
    sess = FakeSession([FakeResponse(404, b"")])
    with pytest.raises(fetch.GdeltNotFound):
        fetch.download("http://x/f.gkg.csv.zip", session=sess, sleep=_no_sleep)
    assert sess.calls == 1  # 한 번만


def test_md5_불일치는_재시도후_IntegrityError():
    sess = FakeSession([FakeResponse(200, GOOD)] * 3)
    with pytest.raises(fetch.IntegrityError):
        fetch.download(
            "http://x/f.gkg.csv.zip",
            expected_md5="deadbeef" * 4,
            session=sess,
            retries=3,
            sleep=_no_sleep,
        )
    assert sess.calls == 3  # 재시도 다 소진


def test_zip매직_아니면_IntegrityError():
    sess = FakeSession([FakeResponse(200, b"<html>error</html>")] * 2)
    with pytest.raises(fetch.IntegrityError):
        fetch.download("http://x/f.gkg.csv.zip", session=sess, retries=2, sleep=_no_sleep)


def test_transient_에러후_성공():
    sess = FakeSession([requests.ConnectionError("끊김"), FakeResponse(200, GOOD)])
    data = fetch.download("http://x/f.gkg.csv.zip", session=sess, retries=3, sleep=_no_sleep)
    assert data == GOOD
    assert sess.calls == 2  # 첫 실패, 둘째 성공


def test_5xx는_재시도():
    sess = FakeSession([FakeResponse(503, b""), FakeResponse(200, GOOD)])
    data = fetch.download("http://x/f.gkg.csv.zip", session=sess, retries=3, sleep=_no_sleep)
    assert data == GOOD
    assert sess.calls == 2


def test_size만_알아도_검증():
    sess = FakeSession([FakeResponse(200, GOOD)])
    data = fetch.download(
        "http://x/f.gkg.csv.zip", expected_size=len(GOOD), session=sess, sleep=_no_sleep
    )
    assert data == GOOD


def test_size_불일치_IntegrityError():
    sess = FakeSession([FakeResponse(200, GOOD)])
    with pytest.raises(fetch.IntegrityError):
        fetch.download(
            "http://x/f.gkg.csv.zip",
            expected_size=len(GOOD) + 1,
            session=sess,
            retries=1,
            sleep=_no_sleep,
        )
