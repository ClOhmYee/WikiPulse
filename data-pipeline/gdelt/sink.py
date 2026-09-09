"""적재 대상(싱크). 같은 인터페이스로 로컬 파일과 HDFS(WebHDFS)를 바꿔 낀다.

streaming 이 "콘솔 싱크 지금, PostgreSQL 나중"으로 간 것과 같은 패턴이다.
HDFS EC2(WP-28)가 아직 없으니 개발은 LocalSink 로 하고, 실제 HDFS 는
docker compose 의 단일노드(gdelt 프로필)에 WebHdfsSink 로 붙여 검증한다.

싱크는 "이미 받은 파일이 뭔가"의 정본이기도 하다 — 별도 매니페스트를 두지 않고
exists() 로 존재를 확인한다. 재시작에 강하고 이중관리 함정이 없다.

WebHDFS 쓰기가 2단계인 이유
    namenode(9870)에 CREATE 하면 307 로 datanode 를 가리킨다. 실제 바디는 그
    datanode URL 로 올린다. producer 를 compose 네트워크 안에서 돌리면 그 호스트명
    (hdfs-datanode)이 그대로 해석된다. 2026-09-09 에 이 왕복을 실측 검증했다.
"""

from __future__ import annotations

import os
from typing import Protocol


class Sink(Protocol):
    """적재 대상. relpath 는 catalog.GkgFile.relpath (YYYY/MM/DD/<ts>.gkg.csv.zip)."""

    def exists(self, relpath: str) -> bool: ...

    def write(self, relpath: str, data: bytes) -> None: ...


class LocalSink:
    """로컬 디렉터리. HDFS 와 같은 경로 레이아웃으로 쓴다.

    쓰기는 임시 파일에 다 쓴 뒤 원자적 rename 한다 — 도중에 죽어도 반쪽짜리가
    완성본처럼 남지 않는다. exists() 가 그 파일을 "이미 받음"으로 보기 때문에
    이 원자성이 중요하다.
    """

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir

    def _path(self, relpath: str) -> str:
        return os.path.join(self.base_dir, *relpath.split("/"))

    def exists(self, relpath: str) -> bool:
        return os.path.exists(self._path(relpath))

    def write(self, relpath: str, data: bytes) -> None:
        path = self._path(relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.part"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # 같은 디렉터리 내 rename 은 원자적


class WebHdfsError(RuntimeError):
    pass


class WebHdfsSink:
    """HDFS 에 WebHDFS REST 로 쓴다. Hadoop 자바 클라이언트가 필요 없다.

    session 을 주입하면(테스트) requests 없이도 돈다. 안 주면 requests 를 지연
    import 한다 — LocalSink 로만 개발하는 팀원은 requests 만 있으면 되고 HDFS
    관련 의존을 강제받지 않는다.
    """

    def __init__(
        self,
        base_url: str,
        base_path: str,
        *,
        user: str = "hadoop",
        session: object | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")  # http://hdfs-namenode:9870
        self.base_path = "/" + base_path.strip("/")  # /gdelt/gkg
        self.user = user
        self.timeout = timeout
        self._session = session

    def _sess(self):
        if self._session is None:
            import requests  # 지연 import

            self._session = requests.Session()
        return self._session

    def _url(self, relpath: str) -> str:
        return f"{self.base_url}/webhdfs/v1{self.base_path}/{relpath}"

    def exists(self, relpath: str) -> bool:
        resp = self._sess().get(
            self._url(relpath),
            params={"op": "GETFILESTATUS", "user.name": self.user},
            timeout=self.timeout,
        )
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        raise WebHdfsError(f"GETFILESTATUS 예상 밖 응답: {resp.status_code}")

    def write(self, relpath: str, data: bytes) -> None:
        """임시 경로(.part)에 올린 뒤 RENAME 으로 최종 경로에 확정한다.

        LocalSink 와 같은 원자성을 HDFS 에서도 지킨다. 업로드가 중간에 끊기면
        반쪽짜리가 <relpath>.part 로 남고 최종 경로엔 안 나타난다 — exists() 가
        그걸 완성본으로 오인하지 않는다. 다음 사이클의 CREATE overwrite 가 남은
        .part 를 덮는다.
        """
        tmp = relpath + ".part"
        self._upload(tmp, data)
        self._rename(tmp, relpath)

    def _upload(self, relpath: str, data: bytes) -> None:
        # 1) namenode 에 CREATE — 307 로 datanode 위치를 받는다. 부모 디렉터리는
        #    WebHDFS 가 자동 생성한다 (2026-09-09 실측: /gdelt/gkg 를 미리 안 만들어도 됨).
        create = self._sess().put(
            self._url(relpath),
            params={"op": "CREATE", "overwrite": "true", "user.name": self.user},
            allow_redirects=False,
            timeout=self.timeout,
        )
        if create.status_code not in (307, 308):
            create.raise_for_status()
            raise WebHdfsError(f"CREATE 가 리다이렉트를 주지 않음: {create.status_code}")
        location = create.headers.get("Location")
        if not location:
            raise WebHdfsError("CREATE 307 에 Location 헤더가 없음")

        # 2) datanode 로 실제 바디 전송 — 성공은 201.
        put = self._sess().put(
            location,
            data=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=self.timeout,
        )
        if put.status_code != 201:
            put.raise_for_status()
            raise WebHdfsError(f"datanode 쓰기 실패: {put.status_code}")

    def _rename(self, src_relpath: str, dst_relpath: str) -> None:
        # WebHDFS RENAME 은 200 + {"boolean": true}. 대상이 이미 있으면 false 다.
        # store_file 이 exists() 로 미리 걸러 최종 경로는 비어 있으므로 true 여야 한다.
        dst_abs = f"{self.base_path}/{dst_relpath}"
        resp = self._sess().put(
            self._url(src_relpath),
            params={"op": "RENAME", "destination": dst_abs, "user.name": self.user},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            resp.raise_for_status()
            raise WebHdfsError(f"RENAME 실패: {resp.status_code}")
        try:
            ok = bool(resp.json().get("boolean", False))
        except Exception:
            ok = True  # 본문 파싱 불가 시 상태코드만 신뢰
        if not ok:
            raise WebHdfsError(f"RENAME 거부됨: {src_relpath} -> {dst_relpath}")
