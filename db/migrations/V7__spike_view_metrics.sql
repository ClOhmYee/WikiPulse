-- WP-129: spike 에 판정에 쓴 조회수 원값·기준선을 저장한다.
--
-- 왜 필요한가 (2026-09-18 canary 실측, docs/validation/2026-09-18-one-day-e2e-canary.md)
--   canary 가 두 가지를 동시에 드러냈다. 원인이 하나다 — spike 가 조회수를 안 남긴다.
--
--   1. cluster_member.views 가 null
--        실제 판정에 쓴 조회수 25,426 이 있는데도 화면에 안 나온다. cluster/driver.py 가
--        `views=None` 을 하드코딩한다 — spike 에서 읽을 컬럼이 없어서다.
--
--   2. 판정이 끝났는데 completeness=pending
--        driver 가 view_ratio 가 NULL 이면 "아직 2차 판정 전" 으로 읽는다(V1 주석).
--        그런데 WP-126 의 2단계 계약에서 **표본이 없는 문서는 배수를 낼 수가 없다** —
--        분모(view_ewma)가 없으니 view_ratio 가 정당하게 NULL 이다. 신규 문서는 대부분
--        이 경로로 확정되는데(절대 하한 >= 100, "0 에서의 급등"), 그게 전부 pending 으로
--        저장된다. 판정은 끝났는데 화면은 대기로 보인다.
--
--   🔴 view_ratio 하나가 두 뜻으로 읽히고 있었다:
--        "배수를 낼 수 없음"(표본 없음)  vs  "아직 판정 안 됨"(조회수 미도착)
--      두 상태는 WP-126 에서 이미 갈라졌다(DecisionStatus). 저장 쪽만 못 따라왔다.
--
-- 왜 컬럼 두 개인가
--   views        판정에 쓴 조회수 원값. 이게 있으면 2차 판정이 실제로 돌았다는 뜻이다.
--                completeness 판단의 새 근거이자 cluster_member.views 의 원천이다.
--   view_baseline 그 시점 조회수 기준선(view_ewma). NULL = 표본 없음(0 에서의 급등 경로).
--                화면이 "평소 N회 -> 지금 M회" 를 그리려면 둘 다 필요하다.
--
--   view_ratio 는 그대로 둔다. 둘이 있으면 배수는 파생값이지만, 기존 행과 조회 코드가
--   쓰고 있고 표본 없는 경로에서는 여전히 NULL 이 맞는 값이다.
--
-- NULL 의 뜻 (🔴 이 구분이 이 마이그레이션의 핵심이다)
--   views IS NULL          조회수가 아직 안 왔다 = 2차 판정 전. 다만 spike 는 확정만
--                          담으므로(WP-126) 정상 경로에서는 나오지 않는다.
--                          V7 이전에 저장된 옛 행이 여기 해당한다.
--   view_baseline IS NULL  기준선 표본이 없다. 판정은 끝났고 절대 하한으로 통과했다.
--                          ⚠️ 이걸 "미완료" 로 읽으면 안 된다 — 그게 이번 결함이다.
--
-- 기존 행
--   TRUNCATE 하지 않는다. V3·V5 와 달리 키 구조가 안 바뀌고, 기존 spike 는 리플레이
--   산출물이라 지우면 클러스터가 통째로 사라진다. 옛 행은 두 컬럼이 NULL 로 남고,
--   driver 는 views IS NULL 을 pending 으로 읽어 여태와 같은 화면을 낸다.
--   다시 적재하면 채워진다.

ALTER TABLE spike ADD COLUMN views         INTEGER;
ALTER TABLE spike ADD COLUMN view_baseline DOUBLE PRECISION;

COMMENT ON COLUMN spike.views IS
    '판정에 쓴 조회수 원값. NULL = 조회수 미도착(2차 판정 전). '
    'spike 는 확정만 담으므로 정상 경로에서는 NULL 이 아니다 — V7 이전 행만 NULL 이다. '
    'cluster_member.views 의 원천이고 completeness 판단 근거다 (WP-129).';

COMMENT ON COLUMN spike.view_baseline IS
    '그 시점 조회수 기준선(view_ewma). NULL = 표본 없음 — 절대 하한(>=100)으로 통과한 '
    '"0 에서의 급등" 경로다(명세 §3.2 3번). 🔴 판정 미완료가 아니다.';

COMMENT ON COLUMN spike.view_ratio IS
    '조회수 급등 배수(views / view_baseline). 표본이 없으면 분모가 없어 NULL 이다. '
    '~~NULL = 아직 2차 판정 전~~ -> 그 뜻은 views 가 가져갔다 (2026-09-18, WP-129). '
    '두 뜻을 한 컬럼이 지고 있어서 판정 완료 건이 pending 으로 저장됐다.';
