#!/usr/bin/env bash
# .env 를 배포 러너 권한을 지키면서 고친다 (WP-178).
#
# 사용:
#   infra/edit-env.sh /home/deploy/infra/service/.env KEY=VALUE [KEY=VALUE ...]
#
# 🔴 **`sed -i` 를 쓰지 말 것.** 파일을 새로 만들어 교체하므로 그룹 소유권이
#    gitlab-runner → ubuntu 로 돌아가고, 다음 배포가 첫 검사에서 죽는다.
#    이 함정으로 죽은 파이프라인: #207183 · #207748 · #210453 · #214248.
#
# 2026-09-21 실측:
#     원본        -rw-r----- ubuntu gitlab-runner
#     sed -i 뒤   -rw-r----- ubuntu ubuntu          ← 날아감
#     cat > 뒤    -rw-r----- ubuntu gitlab-runner   ← 보존
#
# `cat tmp > 파일` 은 **기존 inode 에 써 넣어서** 소유권·권한이 그대로 남는다.
# 그래도 chgrp·chmod 를 다시 거는 이유는, 애초에 그룹이 틀어져 있던 파일도
# 이 스크립트를 거치면 고쳐지게 하려는 것이다.
set -euo pipefail

DEPLOY_GROUP="${DEPLOY_GROUP:-gitlab-runner}"

if [ $# -lt 2 ]; then
    echo "사용: $0 <env파일> KEY=VALUE [KEY=VALUE ...]" >&2
    exit 2
fi

target=$1
shift

if [ ! -f "$target" ]; then
    echo "🔴 env 파일이 없다: $target" >&2
    exit 1
fi

tmp=$(mktemp)
# shellcheck disable=SC2064
trap "rm -f '$tmp'" EXIT
cat "$target" > "$tmp"

# 🔴 덧붙이기 전에 끝 줄바꿈을 보장한다 (WP-218). 마지막 줄에 줄바꿈이 없으면
#    아래 `echo >>` 가 새 키를 그 줄 뒤에 이어 붙인다. 2026-09-23 운영 `.env` 가
#    `WIKIPULSE_PAGETITLE_ENABLED=trueWIKIPULSE_MATCHING_...` 가 됐다 — 재생성했으면
#    기존 키 값이 망가져 기능이 조용히 꺼졌다. 에러는 안 난다.
if [ -s "$tmp" ] && [ -n "$(tail -c1 "$tmp")" ]; then
    printf '\n' >> "$tmp"
fi

for pair in "$@"; do
    case "$pair" in
        *=*) ;;
        *) echo "🔴 KEY=VALUE 형식이 아니다: $pair" >&2; exit 2 ;;
    esac
    key=${pair%%=*}
    value=${pair#*=}

    if grep -q "^${key}=" "$tmp"; then
        # 구분자를 | 로 둬서 값에 / 가 있어도 깨지지 않는다(경로·URL).
        sed "s|^${key}=.*|${key}=${value}|" "$tmp" > "$tmp.new"
        mv "$tmp.new" "$tmp"
    else
        echo "${key}=${value}" >> "$tmp"
    fi
done

# 🔴 여기가 핵심 — 새 파일로 교체하지 않고 기존 파일에 써 넣는다.
cat "$tmp" > "$target"

# 애초에 틀어져 있던 파일도 여기서 바로잡는다.
sudo chgrp "$DEPLOY_GROUP" "$target"
sudo chmod 0640 "$target"

# ⚠️ 검증까지가 이 스크립트의 일이다. 조용히 실패하면 다음 배포에서야 드러난다.
if ! sudo -u "$DEPLOY_GROUP" test -r "$target"; then
    echo "🔴 ${DEPLOY_GROUP} 이 여전히 못 읽는다: $target" >&2
    ls -l "$target" >&2
    exit 1
fi

ls -l "$target"
for pair in "$@"; do
    grep "^${pair%%=*}=" "$target"
done
echo "OK — ${DEPLOY_GROUP} 읽기 확인"
