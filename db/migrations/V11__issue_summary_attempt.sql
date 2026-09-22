-- =====================================================================
-- V11 — 요약 시도 원장 (WP-182)
-- =====================================================================
--
-- 왜 필요한가
--   IssueSummarizer 가 sufficient_context=false 나 스키마 실패를 받으면 저장을
--   건너뛴다. 그러면 issue_report 가 계속 비어 있어 **다음 폴에서 같은 클러스터가
--   또 집힌다.** LLM 은 매번 호출되고 결과는 매번 버려진다 — 종료 조건이 없다.
--
--   2026-09-22 운영 실측: 51분간 확정 +10건에 5,414 크레딧. 앞 구간이 확정 1건당
--   약 107 크레딧이었는데 이 구간은 약 541 이다. 백엔드 로그 12분치에 "근거
--   부족(요약 폐기)" 40건 · "생성=true" 0건이 찍혔다.
--
--   🔴 top_per_snapshot 상한은 이걸 못 막는다. 그 상한은 "한 스냅샷에서 몇 개를
--      고르나"이지 "같은 클러스터를 몇 번 시도하나"가 아니다.
--
-- 왜 issue_report 에 컬럼을 더하지 않았나
--   issue_report.summary 가 NOT NULL 이고, 행이 있다 = 요약이 있다 가 지금 코드·
--   API 전체의 불변식이다(hasReport 가 CONFIRMED 게이트의 한 축). summary 를
--   nullable 로 바꾸면 그 불변식이 **조용히** 깨져 읽는 쪽 전부가 null 을 처리해야
--   한다. 실패는 요약이 아니므로 별도 원장에 남긴다.
--
-- cluster_stock(V6) 과 같은 관습
--   check_state + attempt_count 로 "아직 안 함 / 완료 / 파킹"을 가른다. 다만 여기엔
--   PENDING 이 없다 — 시도하지 않은 클러스터는 행 자체가 없다.

CREATE TABLE issue_summary_attempt (
    cluster_id      BIGINT      PRIMARY KEY REFERENCES issue_cluster(id) ON DELETE CASCADE,
    -- 🔴 model 에 프롬프트 버전이 박혀 있다(예: 'claude-... (summary_v1)').
    --    issue_report.model 과 같은 문자열을 쓴다 — 모델·프롬프트를 올리면 이 원장이
    --    더 이상 일치하지 않아 재시도가 자연히 풀린다. findPriorSummary 가 재사용을
    --    model 동등성으로 거는 것과 같은 의도다.
    model           TEXT        NOT NULL,
    attempt_count   SMALLINT    NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_state      TEXT        NOT NULL
        CHECK (last_state IN ('INSUFFICIENT_CONTEXT', 'SCHEMA_VIOLATION')),
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE issue_summary_attempt IS
    '요약이 저장되지 못한 시도의 원장 (WP-182). 성공하면 행이 남지 않는다 '
    '— 성공 기록은 issue_report 다. 이 표의 목적은 단 하나, 같은 클러스터를 무한히 '
    '다시 집지 않게 하는 것이다.';

COMMENT ON COLUMN issue_summary_attempt.last_state IS
    'INSUFFICIENT_CONTEXT(모델이 근거 부족을 정직하게 신고 — 입력이 빈약한 것이 '
    '원인일 수 있다) / SCHEMA_VIOLATION(정정 1회 후에도 스키마 위반). '
    '⚠️ 둘을 구분해 남기는 이유는 "거절이 정상인 입력"과 "장애"가 다른 사실이기 '
    '때문이다 — 전자는 대표 텍스트를 고쳐야 풀리고 후자는 프롬프트·모델 문제다. '
    '전송 실패(UpstreamUnavailableException)는 여기 안 남는다. 그건 재시도해야 '
    '하는 일시 장애라 VERIFYING 으로 두고 다음 폴에 다시 집는 것이 맞다.';

COMMENT ON COLUMN issue_summary_attempt.attempt_count IS
    '이 model 로 시도한 횟수. 상한(wikipulse.matching.summary.max-attempts, 기본 3)에 '
    '닿으면 요약 대상 선택에서 빠진다. 🔴 상한에 닿아도 status 는 VERIFYING 으로 '
    '남긴다 — 요약이 없는데 CONFIRMED 로 올리면 화면에 빈 요약이 분석 완료로 나간다.';
