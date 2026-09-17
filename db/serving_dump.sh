#!/usr/bin/env bash
# 서빙용 DB dump 생성 + 복원 검증 (WP-109)
#
#   bash db/serving_dump.sh build  <label>   # 연산용 DB -> 서빙 DB -> artifacts/*.dump
#   bash db/serving_dump.sh verify <label>   # 새 빈 DB 에 migrations + restore 대조
#   bash db/serving_dump.sh all    <label>   # 둘 다
#
#   label 예: 2024-09-01_2024-10-31
#
# 왜 연산용 DB 와 전달용 dump 를 나누나
#   리플레이 파이프라인이 쓰는 DB 에는 warm-up 기준선을 만들며 등록된 wiki_page 수십만
#   행과 page_baseline, 그리고 중간 산출물인 spike 가 들어 있다. 그런데 **API 가 읽는
#   것은 다섯 테이블뿐**이다 (backend 의 IssueClusterRepository · IssueQueryRepository ·
#   PulseMapRepository · StockRepository 확인):
#
#       wiki_page · issue_cluster · cluster_snapshot · cluster_member · cluster_edge
#
#   spike·page_baseline 을 읽는 endpoint 는 없다. 그래서 전달용 dump 에서 뺀다 —
#   프론트·서버가 화면을 띄우는 데 필요한 최소집합만 주면 파일이 작고 복원이 빠르다.
#   재탐지·재클러스터링이 필요하면 연산용 DB 를 통째로 dump 한다(아래 COMPUTE 참고).
#
# 🔴 축소는 FK 도달성으로만 한다
#   cluster_member·cluster_edge 가 참조하지 않는 wiki_page 행만 지운다. 임의 생성·수정·
#   샘플링을 하지 않는다 — 남는 것은 전부 파이프라인이 실제로 만든 행의 부분집합이다.
#   지운 뒤 고아 참조 0건을 확인하고서야 dump 한다.
set -uo pipefail

MODE=${1:?"build | verify | all"}
LABEL=${2:?"label (예: 2024-09-01_2024-10-31)"}

: "${PG_CONTAINER:=wikipulse-postgres}"     # docker compose 의 postgres 컨테이너
: "${PG_USER:=wikipulse}"
: "${SRC_DB:=wikipulse_replay}"             # 연산용(파이프라인이 쓴) DB
: "${SERVING_DB:=wikipulse_serving}"        # 서빙 최소집합을 만들 작업 DB
: "${VERIFY_DB:=wikipulse_restore_test}"    # 복원 검증용 빈 DB

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MIGRATIONS="$REPO_ROOT/db/migrations"
OUT_DIR="${ARTIFACT_DIR:-$REPO_ROOT/artifacts}"
DUMP="wikipulse-replay-${LABEL}-serving.dump"

#: API 가 읽는 테이블. 순서는 pg_restore 가 알아서 잡는다.
TABLES=(wiki_page issue_cluster cluster_snapshot cluster_member cluster_edge)
TABLE_ARGS=(); for t in "${TABLES[@]}"; do TABLE_ARGS+=(-t "$t"); done

#: migrations 적용 순서. V5 가 두 개라 파일명 알파벳 순(컨테이너 initdb 와 같은 순서)이다.
MIGRATION_FILES=(V1__initial_schema.sql V2__pulse_snapshot_graph.sql
                 V3__baseline_hour_of_day.sql V4__baseline_view_stddev.sql
                 V5__cluster_stock_reuse.sql V5__spike_source.sql)

COUNT_SQL="SELECT 'wiki_page',count(*) FROM wiki_page
UNION ALL SELECT 'issue_cluster',count(*) FROM issue_cluster
UNION ALL SELECT 'cluster_snapshot',count(*) FROM cluster_snapshot
UNION ALL SELECT 'cluster_member',count(*) FROM cluster_member
UNION ALL SELECT 'cluster_edge',count(*) FROM cluster_edge
ORDER BY 1"

log() { echo "[$(date -u +%FT%TZ)] $*"; }
# 🔴 컨테이너 안 경로(/tmp/...)는 반드시 `bash -lc` 안의 문자열로 넘긴다. Git Bash 는 인자로
# 넘어온 `/tmp/x` 를 `C:/Users/.../Temp/x` 로 바꿔(MSYS 경로 변환) pg_dump 가 호스트 경로를
# 컨테이너 안에서 찾다가 "No such file or directory" 로 죽는다. 따옴표 안은 변환되지 않는다.
in_container() { docker exec "$PG_CONTAINER" bash -lc "$1"; }
psql_db() { docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" "${@:2}"; }

create_schema() {   # $1 = db name. 새로 만들고 migrations 를 올린다.
    docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d postgres -q \
        -c "DROP DATABASE IF EXISTS $1;" -c "CREATE DATABASE $1 OWNER $PG_USER;" || return 1
    for f in "${MIGRATION_FILES[@]}"; do
        docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -v ON_ERROR_STOP=1 -q -f - \
            < "$MIGRATIONS/$f" || { echo "migration 실패: $f" >&2; return 1; }
    done
}

build() {
    mkdir -p "$OUT_DIR"
    log "서빙 DB($SERVING_DB) 재생성 + migrations"
    create_schema "$SERVING_DB" || exit 1

    log "연산용 DB($SRC_DB) -> 서빙 DB 로 ${#TABLES[@]}개 테이블 이관"
    in_container "pg_dump -U $PG_USER -d $SRC_DB --data-only -Fc ${TABLE_ARGS[*]} -f /tmp/_serving_stage.dump" || exit 1
    in_container "pg_restore -U $PG_USER -d $SERVING_DB --data-only --disable-triggers /tmp/_serving_stage.dump" || exit 1

    log "참조되지 않는 wiki_page 제거 (FK 도달성)"
    psql_db "$SERVING_DB" -tAc "SELECT 'before ' || count(*) FROM wiki_page"
    psql_db "$SERVING_DB" -v ON_ERROR_STOP=1 -q -c "
        DELETE FROM wiki_page p
         WHERE NOT EXISTS (SELECT 1 FROM cluster_member m WHERE m.page_id = p.id)
           AND NOT EXISTS (SELECT 1 FROM cluster_edge e
                            WHERE e.source_page_id = p.id OR e.target_page_id = p.id);" || exit 1
    psql_db "$SERVING_DB" -tAc "SELECT 'after  ' || count(*) FROM wiki_page"
    psql_db "$SERVING_DB" -q -c "VACUUM ANALYZE;"

    log "무결성 확인 — 아래 세 값이 모두 0 이어야 한다"
    psql_db "$SERVING_DB" -tAF'|' -c "
        SELECT 'member_orphan', count(*) FROM cluster_member m
          LEFT JOIN wiki_page p ON p.id = m.page_id WHERE p.id IS NULL
        UNION ALL SELECT 'edge_orphan', count(*) FROM cluster_edge e
          LEFT JOIN wiki_page s ON s.id = e.source_page_id
          LEFT JOIN wiki_page t ON t.id = e.target_page_id
         WHERE s.id IS NULL OR t.id IS NULL
        UNION ALL SELECT 'cluster_without_snapshot', count(*) FROM issue_cluster c
          LEFT JOIN cluster_snapshot s
                 ON s.snapshot_ts = c.snapshot_ts AND s.source = c.source
         WHERE s.snapshot_ts IS NULL;"

    log "dump 생성 -> $OUT_DIR/$DUMP"
    in_container "pg_dump -U $PG_USER -d $SERVING_DB --data-only -Fc ${TABLE_ARGS[*]} -f /tmp/$DUMP" || exit 1
    docker cp "$PG_CONTAINER:/tmp/$DUMP" "$OUT_DIR/$DUMP" || exit 1
    ls -l "$OUT_DIR/$DUMP"
}

verify() {
    log "원본($SERVING_DB) row count"
    psql_db "$SERVING_DB" -tAF',' -c "$COUNT_SQL" > /tmp/_src_counts.txt || exit 1
    cat /tmp/_src_counts.txt

    log "새 빈 DB($VERIFY_DB) + migrations"
    create_schema "$VERIFY_DB" || exit 1

    log "pg_restore"
    docker cp "$OUT_DIR/$DUMP" "$PG_CONTAINER:/tmp/$DUMP" || exit 1
    in_container "pg_restore -U $PG_USER -d $VERIFY_DB --data-only --disable-triggers /tmp/$DUMP" || exit 1

    log "복원 row count"
    psql_db "$VERIFY_DB" -tAF',' -c "$COUNT_SQL" > /tmp/_dst_counts.txt || exit 1
    cat /tmp/_dst_counts.txt

    if diff /tmp/_src_counts.txt /tmp/_dst_counts.txt; then
        log "ROW COUNT MATCH"
    else
        log "ROW COUNT MISMATCH"; exit 1
    fi

    log "고아 참조 / identity 시퀀스 확인"
    psql_db "$VERIFY_DB" -tAF'|' -c "
        SELECT 'member_orphan', count(*) FROM cluster_member m
          LEFT JOIN wiki_page p ON p.id = m.page_id WHERE p.id IS NULL
        UNION ALL SELECT 'edge_orphan', count(*) FROM cluster_edge e
          LEFT JOIN wiki_page s ON s.id = e.source_page_id WHERE s.id IS NULL;"
    # identity 컬럼 시퀀스가 dump 와 함께 옮겨졌는지 — 안 옮겨지면 첫 INSERT 가 PK 충돌한다.
    psql_db "$VERIFY_DB" -tAc "
        INSERT INTO wiki_page (wiki, title) VALUES ('testwiki','__restore_probe__') RETURNING id;"
    psql_db "$VERIFY_DB" -q -c "DELETE FROM wiki_page WHERE wiki = 'testwiki';"
    log "verify 완료"
}

case "$MODE" in
    build)  build ;;
    verify) verify ;;
    all)    build && verify ;;
    *)      echo "사용법: $0 {build|verify|all} <label>" >&2; exit 2 ;;
esac
