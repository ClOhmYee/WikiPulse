# PostgreSQL + pgvector. 스키마는 컨테이너 최초 기동 시 자동 적재된다.
#
# db/migrations 의 SQL 을 /docker-entrypoint-initdb.d 로 복사한다. 이 디렉터리의
# 파일은 데이터 볼륨이 비어 있을 때(최초 1회)만 **알파벳 순으로** 실행된다.
# 스키마를 고쳤으면 볼륨을 지우고(`docker compose down -v`) 다시 올린다.
#
# 🔴 **알파벳 순과 버전 순이 갈린다 — 번호를 채워 넣어 복사한다** (2026-09-20).
#    `V10__` 이 `V1__` 보다 앞서 정렬돼서, V10 추가 후 첫 기동이
#    `relation "wiki_page" does not exist` 로 죽었다. 컨테이너가 죽은 채로
#    healthcheck 만 unhealthy 라 원인이 바로 안 보인다.
#    저장소 파일명은 그대로 두고(문서·원장 참조가 붙어 있다) 여기서만
#    `V001__`·`V010__` 으로 바꿔 복사한다. `db/apply_migrations.py`(EC2 경로)는
#    파일명이 아니라 정수 version 으로 정렬하므로 원래부터 이 문제가 없었다 —
#    ⚠️ 두 경로의 정렬 규칙이 다르다는 것이 이 버그의 뿌리다.
#
# pgvector/pgvector 이미지는 vector 확장 바이너리를 들고 있어
# db/migrations/V1 의 CREATE EXTENSION vector 가 그대로 된다.
FROM pgvector/pgvector:pg16

COPY db/migrations/ /tmp/migrations/

RUN set -eu; \
    for f in /tmp/migrations/V*__*.sql; do \
        name="$(basename "$f")"; \
        version="${name%%__*}"; \
        rest="${name#*__}"; \
        printf -- '%s -> V%03d__%s\n' "$name" "${version#V}" "$rest"; \
        cp "$f" "$(printf '/docker-entrypoint-initdb.d/V%03d__%s' "${version#V}" "$rest")"; \
    done; \
    rm -rf /tmp/migrations
