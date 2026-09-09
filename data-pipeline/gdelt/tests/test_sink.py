"""싱크 테스트. LocalSink 는 실제 파일로, WebHdfsSink 는 가짜 세션으로.

둘 다 네트워크·HDFS 없이 돈다. 실 HDFS 왕복은 compose 로 따로 검증한다
(docker/README §검증).
"""

from __future__ import annotations

import pytest

from gdelt.sink import LocalSink, WebHdfsError, WebHdfsSink

REL = "2026/09/09/20260909041500.gkg.csv.zip"


# --- LocalSink ---

def test_local_write_후_exists_참_내용일치(tmp_path):
    sink = LocalSink(str(tmp_path))
    assert sink.exists(REL) is False
    sink.write(REL, b"PK\x03\x04payload")
    assert sink.exists(REL) is True
    written = (tmp_path / "2026" / "09" / "09" / "20260909041500.gkg.csv.zip").read_bytes()
    assert written == b"PK\x03\x04payload"


def test_local_write_는_part_잔여물을_남기지_않는다(tmp_path):
    sink = LocalSink(str(tmp_path))
    sink.write(REL, b"x")
    leftovers = list(tmp_path.rglob("*.part"))
    assert leftovers == []


def test_local_write_덮어쓰기(tmp_path):
    sink = LocalSink(str(tmp_path))
    sink.write(REL, b"first")
    sink.write(REL, b"second")
    written = (tmp_path / "2026" / "09" / "09" / "20260909041500.gkg.csv.zip").read_bytes()
    assert written == b"second"


# --- WebHdfsSink (가짜 세션) ---

class FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """put/get 호출을 기록하고 미리 정해둔 응답을 순서대로 돌려준다."""

    def __init__(self, put_responses=None, get_responses=None):
        self.puts = []
        self.gets = []
        self._put_responses = list(put_responses or [])
        self._get_responses = list(get_responses or [])

    def put(self, url, **kwargs):
        self.puts.append((url, kwargs))
        return self._put_responses.pop(0)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self._get_responses.pop(0)


def test_webhdfs_exists_200이면_참():
    sess = FakeSession(get_responses=[FakeResponse(200)])
    sink = WebHdfsSink("http://hdfs-namenode:9870", "/gdelt/gkg", session=sess)
    assert sink.exists(REL) is True
    url, kwargs = sess.gets[0]
    assert url == "http://hdfs-namenode:9870/webhdfs/v1/gdelt/gkg/" + REL
    assert kwargs["params"]["op"] == "GETFILESTATUS"


def test_webhdfs_exists_404이면_거짓():
    sess = FakeSession(get_responses=[FakeResponse(404)])
    sink = WebHdfsSink("http://hdfs-namenode:9870", "gdelt/gkg", session=sess)
    assert sink.exists(REL) is False


def test_webhdfs_write_2단계_리다이렉트를_따라간다():
    dn = "http://hdfs-datanode:9864/webhdfs/v1/gdelt/gkg/x?op=CREATE&..."
    sess = FakeSession(
        put_responses=[
            FakeResponse(307, headers={"Location": dn}),  # namenode
            FakeResponse(201),  # datanode
        ]
    )
    sink = WebHdfsSink("http://hdfs-namenode:9870/", "/gdelt/gkg/", session=sess)
    sink.write(REL, b"PK\x03\x04data")

    # 1단계: namenode 로 CREATE, 리다이렉트 안 따라감
    nn_url, nn_kwargs = sess.puts[0]
    assert nn_url == "http://hdfs-namenode:9870/webhdfs/v1/gdelt/gkg/" + REL
    assert nn_kwargs["params"]["op"] == "CREATE"
    assert nn_kwargs["allow_redirects"] is False
    # 2단계: datanode Location 으로 실제 바디
    dn_url, dn_kwargs = sess.puts[1]
    assert dn_url == dn
    assert dn_kwargs["data"] == b"PK\x03\x04data"


def test_webhdfs_write_리다이렉트가_없으면_예외():
    sess = FakeSession(put_responses=[FakeResponse(200)])
    sink = WebHdfsSink("http://hdfs-namenode:9870", "/gdelt/gkg", session=sess)
    with pytest.raises(WebHdfsError):
        sink.write(REL, b"x")


def test_webhdfs_write_datanode가_201이_아니면_예외():
    sess = FakeSession(
        put_responses=[
            FakeResponse(307, headers={"Location": "http://dn/x"}),
            FakeResponse(500),
        ]
    )
    sink = WebHdfsSink("http://hdfs-namenode:9870", "/gdelt/gkg", session=sess)
    with pytest.raises((WebHdfsError, RuntimeError)):
        sink.write(REL, b"x")
