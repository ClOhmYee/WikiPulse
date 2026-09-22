#!/bin/bash
# LIVE spike → 클러스터 스냅샷 주기 실행 (WP-194).
#
# 🔴 이 파일은 서버(`wikipulse-live-cluster`)가 그대로 실행한다. 저장소가 정본이고
#    서버 `/home/deploy/wikipulse-local-test/data-pipeline/` 에 복사된다.
#    ⚠️ 자동 동기화는 없다 — 고쳤으면 서버에도 올려야 한다 (WP-196).
#
# ⚠️ **왜 이웃 인자가 없나** (2026-09-22, -194)
#    예전 서버 스크립트는 `--clickstream-root` + `--creation-index` 를 줬다.
#    -161 이 CORE 를 정본으로 바꾸면서 그 인자는 `--expansion` 없이 주면 **거부**된다.
#    bind mount 라 코드만 새로 들어오고 스크립트는 그대로여서, 5분마다 exit 2 로
#    죽으며 LIVE 스냅샷이 2026-09-21T12:00Z 에 멈춰 있었다. 21시간 동안 로그에만 남았다.
#    → CORE 정본은 root 멤버만 쓴다. 이웃 인자를 준다는 것은 legacy expansion 을
#      켠다는 뜻이므로 **함께 지운다.**
set -u

INTERVAL="${CLUSTER_LOOP_INTERVAL:-300}"

# as-of 링크 수집 노브 (기본 꺼짐).
# 🔴 캐시가 비면 그 root 는 singleton 이 되고 CORE 가 아무것도 묶지 못한다.
#    LIVE 는 새 시점이 계속 생기므로 캐시가 항상 비어 있다 — 켜지 않으면 간선 0 이다.
# ⚠️ 켜면 위키미디어로 요청이 나간다. 한 시점당 root 상한(기본 20)만큼이다.
#    CONTACT_EMAIL 이 필요하다 — 없으면 드라이버가 기동에서 멈춘다.
FETCH_LINKS=()
if [ "${CLUSTER_FETCH_LINKS:-0}" = "1" ]; then
  FETCH_LINKS=(--fetch-links)
fi

while true; do
  echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') cluster start"
  python3 -m cluster.driver --dsn "$DATABASE_URL" --source live "${FETCH_LINKS[@]}"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') sleep ${INTERVAL}s"
  sleep "$INTERVAL"
done
