"""GKG 기관명 lift 배치 — Spark 배선 + CLI (WP-65).

    spark-submit gkg/driver.py \
        --cluster-id 42 \
        --start 20241010000000 --end 20241010234500 \
        --theme HURRICANE --location florida \
        --min-issue-count 5

이슈(cluster_id) 하나에 대해, [start, end] 15분 격자의 GKG 원본을 읽어 이슈 술어
(테마 ∧ 지역)로 이슈 기사를 고르고, 기관명 lift 를 계산해 cluster_org_mention 에
적재한다. 명세 §6.2 (b)·§6.3·§11.

왜 이슈 술어를 인자로 받나
    실 파이프라인에서 이슈 클러스터는 위키 문서들의 묶음이지 GKG 기사 필터가
    아니다. "클러스터 → GKG 술어" 변환은 아직 정의되지 않았다(별도 과제). 지금은
    driver.py 를 골격으로 두는 cluster/driver.py 처럼, 이슈 정의를 §11 이 쓴
    테마·지역 술어로 받아 배선한다. Milton = `--theme HURRICANE --location florida`.

결손 내성 (인수 조건 4)
    plan_slots 가 존재하는 슬롯만 골라 넘긴다 — GDELT 결손(404, 예 2025-06-13~
    07-04)으로 빠진 슬롯은 missing 으로 세고 배치는 멈추지 않는다. 손상된 zip 도
    from_zip_bytes 가 빈 결과로 흘려 한 파일이 잡 전체를 죽이지 않는다.

Spark 로 zip 을 읽는 법
    GKG 는 15분마다 zip 하나다. Spark 는 zip 을 직접 못 읽으므로 binaryFiles 로
    (경로, 바이트)를 파일 단위 분산해 받아, 파티션에서 풀고 파싱해 파일별 부분합
    (Aggregate)을 내고 reduce 로 합친다. 기관 수가 수백이라 결과는 드라이버로
    모아 psycopg 로 쓴다(cluster/writer.py 와 같은 방식).
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile
from collections.abc import Callable, Iterator

from gdelt.catalog import GkgFile, iter_slots, parse_ts

from .lift import Aggregate, IssuePredicate, OrgLift, aggregate, rank
from .match import build_ticker_index, match_ticker
from .parse import Record, parse_text
from .writer import persist_org_mentions


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# --- 슬롯 계획 (순수, 결손 내성) ------------------------------------------


def plan_slots(
    start: str, end: str, exists: Callable[[str], bool]
) -> tuple[list[str], list[str]]:
    """[start, end] 격자에서 (존재하는 relpath, 결손 relpath) 를 가른다.

    exists 는 relpath -> bool (LocalSink.exists / WebHdfsSink.exists). 결손은
    버리지 않고 돌려줘 호출자가 세고 로그한다 — "며칠 통째로 404" 여도 있는 것만
    집계하고 멈추지 않는다.
    """
    present: list[str] = []
    missing: list[str] = []
    for ts in iter_slots(parse_ts(start), parse_ts(end)):
        relpath = GkgFile(timestamp=ts, url="").relpath
        (present if exists(relpath) else missing).append(relpath)
    return present, missing


# --- zip 파싱 (순수, 손상 내성) -------------------------------------------


def from_zip_bytes(data: bytes) -> Iterator[Record]:
    """.gkg.csv.zip 바이트 → Record 이터레이터. 손상 zip 은 빈 결과.

    HTML 오류 페이지·잘린 다운로드·빈 zip 이 와도 예외를 삼켜 [] 로 흘린다 —
    한 파일이 배치를 죽이지 않는다(인수 조건 4). Spark flatMap 에서 파일마다 돈다.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if not names:
                return iter(())
            text = zf.read(names[0]).decode("utf-8", "replace")
    except (zipfile.BadZipFile, OSError, EOFError):
        return iter(())
    return parse_text(text)


# --- 로컬 파일 접근 --------------------------------------------------------


def local_exists(base_dir: str) -> Callable[[str], bool]:
    def _exists(relpath: str) -> bool:
        return os.path.exists(os.path.join(base_dir, *relpath.split("/")))
    return _exists


def local_uri(base_dir: str, relpath: str) -> str:
    """binaryFiles 용 file:// URI. Spark 는 스킴 없는 경로를 HDFS 로 볼 수 있어 명시."""
    abspath = os.path.abspath(os.path.join(base_dir, *relpath.split("/")))
    return "file:///" + abspath.replace("\\", "/").lstrip("/")


# --- Spark 집계 ------------------------------------------------------------


def spark_aggregate(spark, uris: list[str], predicate: IssuePredicate) -> Aggregate:
    """binaryFiles 로 zip 들을 분산 파싱해 한 Aggregate 로 접는다.

    파일별로 풀고 파싱해 부분합을 내고 reduce 로 병합한다 — 원본을 드라이버로
    모으지 않는다(하루치 1.9 GB). predicate 는 클로저로 실려 executor 로 간다.
    """
    def fold(_key_bytes) -> Aggregate:
        _, data = _key_bytes
        return aggregate(from_zip_bytes(data), predicate)

    rdd = spark.sparkContext.binaryFiles(",".join(uris))
    return rdd.map(fold).reduce(lambda a, b: a.merge(b))


# --- ticker 매칭 -----------------------------------------------------------


def load_ticker_index(database_url: str) -> dict[str, str]:
    """stock 마스터에서 (ticker, name) 을 읽어 정규화 색인으로."""
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT ticker, name FROM stock ORDER BY ticker")
        rows = cur.fetchall()
    return build_ticker_index(rows)


def attach_tickers(
    lifts: list[OrgLift], index: dict[str, str]
) -> list[tuple[OrgLift, str | None]]:
    return [(lift, match_ticker(lift.org_name, index)) for lift in lifts]


# --- CLI -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cluster-id", type=int, required=True,
                   help="적재 대상 issue_cluster.id")
    p.add_argument("--start", required=True, help="시작 슬롯 14자리 YYYYMMDDHHMMSS (UTC)")
    p.add_argument("--end", required=True, help="끝 슬롯 14자리 YYYYMMDDHHMMSS (UTC)")
    p.add_argument("--theme", action="append", default=[],
                   help="이슈 테마 부분일치(반복 가능). 예: HURRICANE")
    p.add_argument("--location", action="append", default=[],
                   help="이슈 지역 부분일치(반복 가능). 예: florida")
    p.add_argument("--min-issue-count", type=int, default=int(env("GKG_MIN_ISSUE_COUNT", "3")),
                   help="이 미만 이슈 기사에 나온 기관은 버린다(잡음 컷, 기본 3)")
    p.add_argument("--top", type=int, default=None, help="상위 N 만 저장(기본: 전부)")
    p.add_argument("--base-dir", default=env("GDELT_LOCAL_DIR", "gdelt-data"),
                   help="GKG 원본 로컬 루트(gdelt 싱크 레이아웃)")
    p.add_argument("--database-url", default=env("DATABASE_URL", ""),
                   help="PostgreSQL DSN. 없으면 ticker 미부착·저장 생략")
    p.add_argument("--dry-run", action="store_true",
                   help="집계·랭킹만 하고 DB 에 쓰지 않는다")
    return p


def run(args) -> int:
    predicate = IssuePredicate(themes=tuple(args.theme), locations=tuple(args.location))

    present, missing = plan_slots(args.start, args.end, local_exists(args.base_dir))
    print(f"슬롯: 존재 {len(present)} / 결손 {len(missing)} "
          f"(구간 {args.start}~{args.end})")
    if not present:
        print("존재하는 GKG 파일이 없다 — 집계할 것이 없다.", file=sys.stderr)
        return 1

    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName(f"wikipulse-gkg-lift-{args.cluster_id}")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(env("SPARK_LOG_LEVEL", "WARN"))
    try:
        uris = [local_uri(args.base_dir, rp) for rp in present]
        agg = spark_aggregate(spark, uris, predicate)
    finally:
        spark.stop()

    lifts = rank(agg, min_issue_count=args.min_issue_count, top=args.top)
    print(f"이슈 기사 {agg.n_issue:,} / 코퍼스 {agg.n_corpus:,} / 기관 {len(lifts):,}건")

    index = load_ticker_index(args.database_url) if args.database_url else {}
    if not index:
        print("종목 색인 없음 — ticker 전부 NULL 로 둔다(DATABASE_URL 미지정).")
    mentions = attach_tickers(lifts, index)

    for lift, ticker in mentions[:20]:
        tag = ticker or "-"
        print(f"  {lift.lift:7.2f}  {tag:8}  {lift.org_name} "
              f"(이슈 {lift.issue_count}/코퍼스 {lift.corpus_count})")

    if args.dry_run:
        print("dry-run — 저장하지 않음.")
        return 0
    if not args.database_url:
        print("DATABASE_URL 이 없어 저장을 건너뛴다.", file=sys.stderr)
        return 1

    import psycopg

    with psycopg.connect(args.database_url) as conn:
        n = persist_org_mentions(conn, args.cluster_id, mentions)
        conn.commit()
    print(f"cluster_org_mention 에 {n:,}건 저장(cluster_id={args.cluster_id}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
