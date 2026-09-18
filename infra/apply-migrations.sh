#!/usr/bin/env bash
# EC2 에서 마이그레이션을 적용하고 애플리케이션 롤에 권한을 준다 (WP-133).
#
#   ./infra/apply-migrations.sh                # 남은 것 적용 + 권한
#   ./infra/apply-migrations.sh --dry-run      # 무엇이 남았는지만
#   ./infra/apply-migrations.sh --baseline 9   # 이력 없던 DB 에 한 번 (손으로 적용한 만큼)
#
# 배포 잡(deploy:backend)이 이 파일을 부른다. 사람이 서버에서 직접 돌릴 때도 같은 것을
# 쓰라고 스크립트로 뺐다 — 명령이 두 벌이면 한쪽만 바뀐다.
#
# ⚠️ ec2-shell 러너 호스트에는 psycopg 가 없다. 그래서 컨테이너 안에서 돌린다.
# 🔴 비밀값은 서버의 .env 에서만 읽는다. CI 변수로 복제하지 않는다 — 두 곳이 갈리면
#    어느 쪽이 맞는지 알 수 없다.
#
# 🔴 **마이그레이션은 DB 소유자로 붙는다. 앱 롤로 붙으면 안 된다.**
#    2026-09-18 실측: 두 .env 를 같이 읽었더니 service/.env 의 POSTGRES_USER(=앱 롤)가
#    이겨서 `permission denied for table wiki_page` 로 죽었다. 앱 롤은 DML 만 갖고
#    있어서(그게 맞다) 테이블을 못 만든다. 그래서 소유자 계정을 MIGRATION_USER 로
#    따로 받는다 — infra/db/.env 에 둔다.
set -euo pipefail

REPO_DB_DIR="${REPO_DB_DIR:-$(cd "$(dirname "$0")/../db" && pwd)}"
DB_ENV="${DB_ENV:-/home/deploy/infra/db/.env}"
SERVICE_ENV="${SERVICE_ENV:-/home/deploy/infra/service/.env}"
NETWORK="${NETWORK:-wikipulse-net}"
IMAGE="${MIGRATION_IMAGE:-python:3.11-slim}"

for f in "$DB_ENV" "$SERVICE_ENV"; do
    [ -r "$f" ] || { echo "🔴 env 파일을 못 읽는다: $f" >&2; exit 2; }
done

# ⚠️ --env-file 은 뒤에 준 것이 이긴다. 겹치는 POSTGRES_* 는 db 쪽이 맞다.
docker run --rm --network "$NETWORK" \
    --env-file "$SERVICE_ENV" \
    --env-file "$DB_ENV" \
    -v "$REPO_DB_DIR:/db:ro" \
    -e "EXTRA_ARGS=$*" \
    "$IMAGE" sh -c '
        set -e
        : "${MIGRATION_USER:?infra/db/.env 에 MIGRATION_USER(=DB 소유자)를 넣는다}"
        pip install --quiet "psycopg[binary]==3.3.5"
        export DATABASE_URL="postgresql://$MIGRATION_USER:$POSTGRES_PASSWORD@postgres:5432/${POSTGRES_DB:-wikipulse}"
        python /db/apply_migrations.py --grant-role "${APP_DB_ROLE:-user_wikipulse}" $EXTRA_ARGS
    '
