"""GKG 기관명 lift 배치 — Spark 배선 + CLI (WP-65).

    spark-submit gkg/driver.py \
        --cluster-id 42 \
        --start 20241010000000 --end 20241010234500 \
        --theme HURRICANE --location florida \
        --min-issue-count 5

이슈(cluster_id) 하나에 대해, [start, end] 15분 격자의 GKG 원본을 읽어 이슈 술어
(테마 ∧ 지역)로 이슈 기사를 고르고, 기관명 lift 를 계산해 cluster_org_mention 에
적재한다. 명세 §6.2 (b)·§6.3·§11.

이슈 술어는 어디서 오나
    실 파이프라인에서 이슈 클러스터는 위키 문서들의 묶음이지 GKG 기사 필터가 아니다.
    ~~"클러스터 → GKG 술어" 변환은 아직 정의되지 않았다(별도 과제)~~ → **구현됨**
    (2026-09-20, WP-148). `--theme`·`--location` 을 생략하면 `cluster_member`
    를 읽어 `gkg/predicate.py` 가 술어를 뽑는다. 직접 주면 그 값이 우선이다(override).

    ⚠️ **자동 생성은 코퍼스를 한 번 더 훑는다.** 술어를 알아야 집계하는데 술어는 관측
    어휘를 알아야 뽑는 순환이라 그렇다. 수동으로 주면 그 패스는 안 돈다.
    Milton = `--theme HURRICANE --location florida` (§11).

결손 내성 (인수 조건 4)
    plan_slots 가 존재하는 슬롯만 골라 넘긴다 — GDELT 결손(404, 예 2025-06-14 18:00~
    07-02 02:00 UTC, 2026-09-16 경계 재확인)으로 빠진 슬롯은 missing 으로 세고
    배치는 멈추지 않는다. 손상된 zip 도
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
from gdelt.sink import LocalSink

from .aliases import ALIASES, BLOCKLIST_KEYS
from .lift import Aggregate, IssuePredicate, OrgLift, aggregate, rank
from .match import build_ticker_index, match_ticker, merge_aliases
from .parse import Record, parse_text
from .predicate import Member, Vocabulary, derive, describe
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
    rdd = spark.sparkContext.binaryFiles(",".join(uris))
    return rdd.map(fold_file(predicate)).reduce(lambda a, b: a.merge(b))


def spark_vocabulary(spark, uris: list[str]) -> Vocabulary:
    """술어를 뽑기 위해 코퍼스에 **실제로 나타난** 테마·지역 어휘를 센다 (WP-148).

    ⚠️ **이건 두 번째 스캔이다.** 술어를 알아야 집계하는데 술어는 어휘를 알아야 뽑으므로
    순환이라, zip 을 두 번 푼다. `--theme`·`--location` 을 직접 주면 이 패스는 아예
    안 돈다. 창이 넓어 비용이 부담되면 `--vocab-slots` 로 앞쪽 N 슬롯만 본다 — 비율
    가드는 스케일 무관이라 표본으로도 성립하지만, `min_support` 는 절대값이라 표본이
    작으면 용어가 더 쉽게 탈락한다.
    """
    rdd = spark.sparkContext.binaryFiles(",".join(uris))
    return rdd.map(fold_vocabulary_file).reduce(lambda a, b: a.merge(b))


def fold_vocabulary_file(key_bytes: tuple[str, bytes]) -> Vocabulary:
    """(경로, 바이트) 하나를 어휘 부분합으로. `fold_file` 과 같은 꼴이다."""
    _, data = key_bytes
    return Vocabulary.from_records(from_zip_bytes(data))


def load_cluster_members(database_url: str, cluster_id: int) -> list[Member]:
    """`cluster_member` → 술어 생성 입력.

    🔴 **제목은 canonical(공백형)이다** — `wiki_page.title` 이 그 계약이다(명세 §5.1).
    GKG 지역 풀네임도 공백형이라 그대로 맞물린다. 밑줄형이 섞여 들어오면 단어 경계
    매칭이 조용히 빗나간다.
    """
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.title, m.is_seed
              FROM cluster_member m
              JOIN wiki_page p ON p.id = m.page_id
             WHERE m.cluster_id = %s
             ORDER BY m.is_seed DESC, m.weight DESC, p.title
            """,
            (cluster_id,),
        )
        return [Member(title=title, is_seed=is_seed) for title, is_seed in cur.fetchall()]


def fold_file(predicate: IssuePredicate) -> Callable[[tuple[str, bytes]], Aggregate]:
    """(경로, 바이트) 하나를 파일 단위 부분합으로. driver 와 테스트가 같이 쓴다.

    파일마다 files=1 을 세고, 0행을 낸 파일(손상·잘린 zip·HTML 오류 페이지)은
    empty_files=1 로 표시한다 — reduce 로 합쳐 run() 이 결손과 나란히 출력해,
    "조용히 유실된 파일"이 lift 를 과소집계하는 걸 운영자가 보게 한다(인수 조건 4).
    """
    def fold(key_bytes: tuple[str, bytes]) -> Aggregate:
        _, data = key_bytes
        agg = aggregate(from_zip_bytes(data), predicate)
        agg.files = 1
        if agg.n_corpus == 0:
            agg.empty_files = 1
        return agg

    return fold


# --- ticker 매칭 -----------------------------------------------------------


def load_ticker_index(database_url: str) -> dict[str, str]:
    """stock 마스터 + 별칭(WP-47) 을 합친 정규화 색인.

    마스터 정확 일치가 우선이고, 별칭은 마스터가 못 잡은 자회사·브랜드명만
    메운다(merge_aliases). blocklist 는 짧은 이름 오탐 방지(aliases.py 참고).
    """
    import psycopg

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT ticker, name FROM stock ORDER BY ticker")
        rows = cur.fetchall()
    index = build_ticker_index(rows)
    return merge_aliases(index, ALIASES, BLOCKLIST_KEYS)


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
                   help="이슈 테마 부분일치(반복 가능). 예: HURRICANE. "
                        "생략하면 클러스터 멤버에서 뽑는다(WP-148)")
    p.add_argument("--location", action="append", default=[],
                   help="이슈 지역 단어경계 매칭(반복 가능). 예: florida. "
                        "생략하면 클러스터 멤버에서 뽑는다")
    p.add_argument("--vocab-slots", type=int, default=0,
                   help="술어 생성용 어휘 스캔을 앞쪽 N 슬롯으로 제한(0=전부). "
                        "두 번째 스캔 비용을 줄이지만 min_support 가 표본에 비례해 빡빡해진다")
    p.add_argument("--max-themes", type=int, default=2,
                   help="술어에 넣을 테마 용어 최대 개수(기본 2)")
    p.add_argument("--max-locations", type=int, default=3,
                   help="술어에 넣을 지역 용어 최대 개수(기본 3)")
    p.add_argument("--max-corpus-ratio", type=float, default=0.5,
                   help="이 비율보다 많은 코퍼스에 걸리는 용어는 버린다(기본 0.5). "
                        "조이면 진짜 사건 테마가 탈락한다 — predicate.py 주석 참고")
    # env 기본값은 문자열로 두고 argparse type=int 가 변환한다 — GKG_MIN_ISSUE_COUNT
    # 오설정 시 build_parser 시점 raw ValueError 대신 깔끔한 argparse 에러가 난다.
    p.add_argument("--min-issue-count", type=int, default=env("GKG_MIN_ISSUE_COUNT", "3"),
                   help="이 미만 이슈 기사에 나온 기관은 버린다(잡음 컷, 기본 3)")
    p.add_argument("--top", type=int, default=None, help="상위 N 만 저장(기본: 전부)")
    p.add_argument("--base-dir", default=env("GDELT_LOCAL_DIR", "gdelt-data"),
                   help="GKG 원본 로컬 루트(gdelt 싱크 레이아웃)")
    p.add_argument("--database-url", default=env("DATABASE_URL", ""),
                   help="PostgreSQL DSN. 없으면 ticker 미부착·저장 생략")
    p.add_argument("--dry-run", action="store_true",
                   help="집계·랭킹만 하고 DB 에 쓰지 않는다")
    return p


def run(args: argparse.Namespace) -> int:
    # 술어를 직접 주면 그대로 쓴다(override). 안 주면 클러스터 멤버에서 뽑는다
    # (WP-148) — 그러려면 멤버를 읽을 DB 가 필요하다.
    manual = bool(args.theme or args.location)
    predicate = (
        IssuePredicate(themes=tuple(args.theme), locations=tuple(args.location))
        if manual else None
    )
    if not manual and not args.database_url:
        print("--theme/--location 도 없고 DATABASE_URL 도 없다 — 술어를 만들 수 없다. "
              "둘 중 하나는 있어야 한다.", file=sys.stderr)
        return 1

    # 저장이 목적인데 DSN 이 없으면 수 분짜리 Spark 집계 전에 막는다(fail-fast).
    if not args.dry_run and not args.database_url:
        print("DATABASE_URL 이 없다 — 저장할 수 없어 중단. 집계만 하려면 --dry-run.",
              file=sys.stderr)
        return 1

    present, missing = plan_slots(args.start, args.end, LocalSink(args.base_dir).exists)
    print(f"슬롯: 존재 {len(present)} / 결손 {len(missing)} "
          f"(구간 {args.start}~{args.end})")
    if not present:
        print("존재하는 GKG 파일이 없다 — 집계할 것이 없다.", file=sys.stderr)
        return 1

    from pyspark.sql import SparkSession

    spark = None
    try:
        spark = (
            SparkSession.builder.appName(f"wikipulse-gkg-lift-{args.cluster_id}")
            .config("spark.sql.session.timeZone", "UTC")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel(env("SPARK_LOG_LEVEL", "WARN"))
        uris = [local_uri(args.base_dir, rp) for rp in present]

        if predicate is None:
            members = load_cluster_members(args.database_url, args.cluster_id)
            if not members:
                print(f"클러스터 {args.cluster_id} 에 멤버가 없다 — 술어를 만들 수 없다.",
                      file=sys.stderr)
                return 2
            vocab_uris = uris[:args.vocab_slots] if args.vocab_slots else uris
            print(f"술어 생성: 멤버 {len(members)}건, 어휘 스캔 {len(vocab_uris)}/{len(uris)} 슬롯")
            derivation = derive(
                members,
                spark_vocabulary(spark, vocab_uris),
                max_themes=args.max_themes,
                max_locations=args.max_locations,
                max_corpus_ratio=args.max_corpus_ratio,
            )
            print(describe(derivation))
            if derivation.predicate is None:
                # 🔴 여기서 멈춘다. 술어가 없다고 전체 코퍼스로 집계하면 lift 가 전부
                # 1 이 되고, 그게 "관련 기관 없음"처럼 보여 조용히 틀린다.
                print(f"클러스터 {args.cluster_id}: 술어를 만들지 못했다 — 집계를 건너뛴다.",
                      file=sys.stderr)
                return 2
            predicate = derivation.predicate

        agg = spark_aggregate(spark, uris, predicate)
    finally:
        if spark is not None:
            spark.stop()

    lifts = rank(agg, min_issue_count=args.min_issue_count, top=args.top)
    print(f"이슈 기사 {agg.n_issue:,} / 코퍼스 {agg.n_corpus:,} / 기관 {len(lifts):,}건")
    if agg.empty_files:
        print(f"⚠️ 손상·빈 파일 {agg.empty_files}/{agg.files}건 — 코퍼스가 그만큼 "
              f"과소집계됐다(lift 신뢰 저하). 수집측 재적재 확인.", file=sys.stderr)

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
