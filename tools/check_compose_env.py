"""application.yml 의 WIKIPULSE_MATCHING_* 환경변수가 compose 에 다 적혀 있는지 본다.

⚠️ **같은 함정에 두 번 물려서 만들었다.** 노브를 더해 놓고 compose 에 안 적으면 `.env` 에
값을 넣어도 컨테이너 안에 안 들어간다. 애플리케이션 기본값으로 조용히 떨어지므로
"켰는데 아무 일도 안 일어난다" / "좁혔는데 안 좁혀진다"로 보인다 — 에러가 안 난다.

    WP-142  GATEWAY·워커 변수 누락
    WP-168  scheduler/summary SOURCE 누락 (머지 직전에 발견)

🔴 대상은 WIKIPULSE_MATCHING_* 뿐이다. DATABASE_URL 처럼 compose 가 직접 값을 주는 것은
   application.yml 의 플레이스홀더와 이름이 달라 여기 걸면 오탐이 된다.

의존성 없이 돈다:  py -3 tools/check_compose_env.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_YML = ROOT / "backend/src/main/resources/application.yml"
COMPOSES = [ROOT / "infra/service/compose.yaml", ROOT / "docker-compose.yml"]

PREFIX = "WIKIPULSE_MATCHING_"
PLACEHOLDER = re.compile(r"\$\{(" + PREFIX + r"[A-Z0-9_]+)")


def declared() -> set[str]:
    return set(PLACEHOLDER.findall(SOURCE_YML.read_text(encoding="utf-8")))


def forwarded(path: pathlib.Path) -> set[str]:
    # compose 는 `KEY: ${KEY:-기본값}` 꼴이라 좌변만 본다 — 좌변이 곧 컨테이너 안 이름이다.
    return set(re.findall(r"^\s*(" + PREFIX + r"[A-Z0-9_]+)\s*:", path.read_text(encoding="utf-8"),
                          re.MULTILINE))


def main() -> int:
    want = declared()
    if not want:
        print(f"[FAIL] {SOURCE_YML.relative_to(ROOT)} 에서 {PREFIX}* 를 하나도 못 찾았다 — "
              "경로나 표기가 바뀐 것 같다. 이 검사가 무력화된 상태다.")
        return 1

    failed = False
    for compose in COMPOSES:
        missing = sorted(want - forwarded(compose))
        rel = compose.relative_to(ROOT)
        if missing:
            failed = True
            print(f"[FAIL] {rel} 가 전달하지 않는 변수 {len(missing)}개:")
            for name in missing:
                print(f"         {name}")
        else:
            print(f"[ OK ] {rel} — {len(want)}개 전부 전달")

    if failed:
        print()
        print("compose 의 environment 에 `이름: ${이름:-기본값}` 으로 더한다.")
        print("🔴 .env 에 넣는 것만으로는 컨테이너 안에 안 들어간다.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
