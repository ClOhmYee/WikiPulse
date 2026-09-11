-- WikiPulse 펄스맵 스냅샷·문서 그래프 저장  (WP-75)
-- 계약: docs/frontend/PULSE_MAP.md, frontend/docs/pulse-openapi.json
-- 기준: docs/requirements-v0.1.md §3.2 4번(클러스터링 게이트), §11(실측)
--
-- 목적. 버블맵(WP-74 조회 API)이 한 스냅샷을 통째로 그리려면
-- V1 이 갖지 못한 세 가지가 필요하다.
--
--   1. 시점 간 이슈 추적(issue_key)·최초 감지 시각·HOT·카테고리·척도 버전
--   2. 시점별로 "고정된" 문서 지표(편집/조회/기준선/급등/크기점수/집계구간)
--      — 리플레이는 과거 시점 값이라 지금 spike 테이블을 다시 읽어선 안 된다
--   3. 문서 쌍 간선(Clickstream 실선·Wikidata 점선)과 스냅샷 완성 목록
--
-- 설계 원칙: additive. 기존 컬럼·제약을 바꾸지 않고 추가만 한다.
-- V1 로 이미 적재된 행은 새 컬럼이 NULL/기본값으로 남고, 리플레이 재계산이
-- 같은 스키마에 다시 쓸 수 있다(재계산 호환). 백엔드 ddl-auto=validate 는
-- 매핑된 엔티티만 검사하므로 여기 추가한 테이블·컬럼은 검증을 깨지 않는다.

-- =====================================================================
-- 1. issue_cluster — 시점 간 추적·표시 메타
-- =====================================================================

ALTER TABLE issue_cluster
    ADD COLUMN issue_key         TEXT,
    ADD COLUMN first_detected_at TIMESTAMPTZ,
    ADD COLUMN hot               BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN category          TEXT    NOT NULL DEFAULT 'other'
        CHECK (category IN ('politics', 'world', 'society', 'economy',
                            'technology', 'science', 'culture', 'sports',
                            'environment', 'other'));

COMMENT ON COLUMN issue_cluster.issue_key IS
    '같은 사건을 시점 간에 잇는 안정 식별자. id 는 스냅샷마다 새로 생기지만 '
    'issue_key 는 유지된다 — 슬라이더가 시점을 옮겨도 같은 이슈 선택을 유지하는 근거. '
    'V1 로 적재된 행은 NULL 이고, 생산 파이프라인이 항상 채운다.';

COMMENT ON COLUMN issue_cluster.first_detected_at IS
    '이 issue_key 가 처음 감지된 시각. 입력 시각·문서 생성 시각과 구분한다. '
    'NEW 배지는 0 <= snapshot_ts - first_detected_at < new_window_hours 로 판정.';

COMMENT ON COLUMN issue_cluster.hot IS
    '이 스냅샷에서의 서버 급증 판정. NEW(신선도)와 독립이며 함께 켜질 수 있다.';

COMMENT ON COLUMN issue_cluster.category IS
    '이슈 뉴스형 카테고리(10종). 종목 산업·섹터와 별개다(PULSE_MAP.md). '
    'LLM 이 확정 전이면 기본 other.';

-- 같은 issue_key 의 시점별 행을 시간순으로 꺼내는 추적 조회용.
CREATE INDEX issue_cluster_issue_key_idx
    ON issue_cluster (issue_key, snapshot_ts)
    WHERE issue_key IS NOT NULL;

-- =====================================================================
-- 2. cluster_member — 시점별로 고정된 문서 지표
-- =====================================================================
--
-- 이 값들은 스냅샷 생산 시점에 계산해 여기 박아 둔다. 리플레이 응답이
-- 현재 spike/page_edit_window 를 다시 읽으면 과거·현재가 섞이므로(계약: 금지)
-- 노드 지표는 반드시 이 고정본에서 나온다.

ALTER TABLE cluster_member
    ADD COLUMN edit_count    INTEGER,
    ADD COLUMN views         INTEGER,
    ADD COLUMN edit_baseline DOUBLE PRECISION,
    ADD COLUMN view_baseline DOUBLE PRECISION,
    ADD COLUMN spike_score   DOUBLE PRECISION,
    ADD COLUMN size_score    DOUBLE PRECISION
        CHECK (size_score IS NULL OR (size_score >= 0 AND size_score <= 1)),
    ADD COLUMN completeness  TEXT NOT NULL DEFAULT 'complete'
        CHECK (completeness IN ('complete', 'pending', 'unavailable')),
    ADD COLUMN window_start  TIMESTAMPTZ,
    ADD COLUMN window_end    TIMESTAMPTZ,
    ADD CONSTRAINT cluster_member_window_order
        CHECK (window_start IS NULL OR window_end IS NULL OR window_start < window_end);

COMMENT ON COLUMN cluster_member.size_score IS
    '노드 반지름을 정하는 공통 척도 0~1. 신규/기존 문서의 원시 점수 산식 차이를 '
    '이 값으로 흡수한다(계약 scoreVersion). 매 시점 최댓값 정규화가 아니라 절대 척도. '
    'NULL(미제공)과 0 을 구분한다.';

COMMENT ON COLUMN cluster_member.completeness IS
    'complete: 지표 확정 / pending: 2차 판정(조회수) 대기 / unavailable: 소스 없음. '
    '수치 NULL 을 0 으로 보완하지 않는다 — 화면이 completeness 로 구분한다.';

COMMENT ON COLUMN cluster_member.window_start IS
    '노드 지표의 집계 구간. 시작 < 종료 <= snapshot_ts 여야 한다(계약).';

-- =====================================================================
-- 3. cluster_edge — 문서 쌍 간선
-- =====================================================================
--
-- membership weight 로 만들지 않는다(계약). 같은 클러스터 안 두 문서를 잇는
-- 독립 간선이다. Clickstream 은 방향·이동량·기준 월, Wikidata 는 점선 관계·관측 시각.
-- Wikidata 는 클러스터링 게이트에서 빠졌지만(§3.2 4번) 화면 근거로는 그린다.

CREATE TABLE cluster_edge (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id     BIGINT NOT NULL REFERENCES issue_cluster(id) ON DELETE CASCADE,
    source_page_id BIGINT NOT NULL REFERENCES wiki_page(id)     ON DELETE CASCADE,
    target_page_id BIGINT NOT NULL REFERENCES wiki_page(id)     ON DELETE CASCADE,
    kind           TEXT   NOT NULL CHECK (kind IN ('clickstream', 'wikidata')),
    directed       BOOLEAN NOT NULL,
    weight         DOUBLE PRECISION NOT NULL CHECK (weight >= 0),
    evidence_label       TEXT        NOT NULL,
    evidence_month       TEXT        CHECK (evidence_month ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    evidence_observed_at TIMESTAMPTZ,
    CONSTRAINT cluster_edge_no_self       CHECK (source_page_id <> target_page_id),
    CONSTRAINT cluster_edge_unique        UNIQUE (cluster_id, source_page_id, target_page_id, kind),
    -- Clickstream 은 월별 덤프 근거, Wikidata 는 관측 시각 근거. 종류마다 하나는 있어야 한다.
    CONSTRAINT cluster_edge_evidence_kind CHECK (
        (kind = 'clickstream' AND evidence_month IS NOT NULL)
        OR (kind = 'wikidata' AND evidence_observed_at IS NOT NULL))
);

COMMENT ON TABLE cluster_edge IS
    '한 클러스터 안 문서 쌍 간선. 양 끝은 반드시 같은 클러스터의 cluster_member 여야 한다 '
    '— DB 로 직접 강제하지 못해(멤버십은 복합키) 생산 파이프라인이 보장한다. '
    'Clickstream(실선·방향·이동량 weight·기준 월)과 Wikidata(점선·관계·관측 시각).';

COMMENT ON COLUMN cluster_edge.evidence_month IS
    'Clickstream 기준 월 YYYY-MM. 선택 스냅샷 이전 월이어야 하며 순간 이동량이 아니다.';

CREATE INDEX cluster_edge_cluster_idx ON cluster_edge (cluster_id);

-- =====================================================================
-- 4. cluster_snapshot — 완성된 스냅샷 목록 (0개 포함)
-- =====================================================================
--
-- issue_cluster 만으로는 "완료됐지만 클러스터 0개"인 스냅샷을 표현하지 못한다
-- (행이 아예 안 생긴다). 슬라이더 날짜 목록·빈 스냅샷 구분(계약)을 위해
-- 생산이 끝난 시점을 여기 등록한다. 아직 저장 안 된 시점과 완료된 빈 시점은 다르다.

CREATE TABLE cluster_snapshot (
    snapshot_ts      TIMESTAMPTZ NOT NULL,
    source           TEXT        NOT NULL CHECK (source IN ('live', 'replay')),
    cluster_count    INTEGER     NOT NULL DEFAULT 0 CHECK (cluster_count >= 0),
    score_version    TEXT        NOT NULL,
    new_window_hours DOUBLE PRECISION NOT NULL DEFAULT 24 CHECK (new_window_hours > 0),
    completed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, snapshot_ts)
);

COMMENT ON TABLE cluster_snapshot IS
    '생산이 완료된 스냅샷 레지스트리. (source, snapshot_ts) 유일. '
    'cluster_count=0 인 완료 스냅샷도 남긴다 — 조회 API 가 빈 스냅샷과 미저장 시점을 구분. '
    'score_version 은 size_score 척도 버전, new_window_hours 는 NEW 배지 창(기본 24).';

CREATE INDEX cluster_snapshot_ts_idx ON cluster_snapshot (snapshot_ts DESC);
