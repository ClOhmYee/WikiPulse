-- V21: 이슈 리포트 본문(섹션형) — WP-223
--
-- 왜
--   프론트 이슈 상세의 "리포트" 칸(-186·-188)은 report{status, model, generatedAt,
--   sections[{id,title,body,evidenceIds}]} 를 받게 돼 있는데 백엔드에 그 값이 없었다.
--   그래서 모든 이슈가 "리포트를 만들 근거가 충분하지 않습니다" 로 떴다 — 근거 부족이
--   아니라 미연결이다.
--
-- 왜 issue_report 에 컬럼을 더하나 (V11 은 별도 표를 만들었다)
--   리포트는 요약과 같은 클러스터·같은 수명(CASCADE)이고, 요약이 있는 이슈에만 붙는다.
--   V11 이 별도 표를 만든 이유("행이 있다 = 요약이 있다")는 여기서도 유지된다 — 세 컬럼
--   모두 NULL 허용이라 행의 의미가 바뀌지 않는다.
--   🔴 요약 워커의 upsert(IssueSummaryRepository)는 summary·model·generated_at 만 갱신한다.
--      리포트 컬럼은 요약이 다시 써져도 지워지지 않는다(test_schema_v21 가 고정).
--
-- report_sections 는 API 모양 그대로다:
--   [{"id": "overview", "title": "이슈 개요", "body": "…", "evidenceIds": ["901", …]}, …]
--   evidenceIds 는 이 클러스터 멤버의 wiki_page.id(문자열) — 프론트 근거 칩이 멤버 pageId 로 찾는다.

ALTER TABLE issue_report
    ADD COLUMN report_sections     JSONB,
    ADD COLUMN report_model        TEXT,
    ADD COLUMN report_generated_at TIMESTAMPTZ;

ALTER TABLE issue_report
    ADD CONSTRAINT issue_report_sections_is_array
        CHECK (report_sections IS NULL OR jsonb_typeof(report_sections) = 'array');

COMMENT ON COLUMN issue_report.report_sections IS
    '섹션형 리포트 본문(JSON 배열). NULL 이면 리포트 없음 — 상세 API 가 report 를 내리지 않는다. '
    'WP-223.';
COMMENT ON COLUMN issue_report.report_model IS
    '리포트를 만든 모델·프롬프트 버전. 요약의 model 과 따로 둔다 — 두 단계가 다른 시점에 다른 모델로 돈다.';
