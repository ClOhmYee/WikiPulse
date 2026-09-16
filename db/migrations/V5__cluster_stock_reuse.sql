-- WP-44(재오픈)·WP-49·WP-50
-- cluster_stock 에 재사용 조회·재시도 상태를 위한 컬럼을 더한다.
--
-- 왜 다시 여나 (2026-09-16)
--   -49(LLM 판정 재사용) 설계 중 cluster_id 가 스냅샷마다 새로 생긴다는 걸 확인했다
--   (cluster/snapshot.py 독스트링: "id 는 스냅샷마다 새로 생기지만... issue_key 를
--   쓴다"). cluster_stock 은 (cluster_id, ticker) 로만 식별돼 있어, 진행 중인 이슈가
--   재감지될 때마다(새 snapshot_ts -> 새 cluster_id) 캐시 조회가 매번 미스한다.
--   재사용 키는 issue_key 여야 한다.
--
-- 왜 UNIQUE 가 아니라 일반 인덱스인가
--   V2 설계 원칙(파일 상단 주석)이 "additive, 기존 제약을 바꾸지 않는다"다.
--   issue_cluster/cluster_member 처럼 cluster_stock 도 스냅샷마다 새 cluster_id 로
--   다시 생길 수 있어(-67 이 새 snapshot 의 cluster_id 에 대해 다시 후보를 깐다),
--   같은 (issue_key, ticker) 가 여러 cluster_id 에 걸쳐 반복되는 게 정상이다 —
--   UNIQUE 로 묶으면 두 번째 스냅샷 적재가 제약 위반으로 깨진다.
--   재사용 조회는 유일성 제약이 아니라 "가장 최근 DONE 행을 찾는" 조회다
--   (cluster/driver.py 의 load_prior_first_detected 와 같은 패턴).
--
-- check_state 를 verified 와 분리하는 이유 (-50)
--   verified=false 하나로는 "아직 검증 안 됨"과 "GATEWAY 장애로 검증 실패"가 안 갈린다.
--   후자를 전자로 보이면, 사실은 판정 못 한 이슈가 "관련 종목 없음"으로 화면에
--   조용히 나간다. check_state='DONE' 일 때만 verified/match_path/rationale 이
--   유효한 판정이고, 'FAILED' 는 3번 재시도(attempt_count) 후 파킹된 것 —
--   재시도 안 하고 사람이 본다(운영 대시보드는 범위 밖).

ALTER TABLE cluster_stock
    ADD COLUMN issue_key      TEXT,
    ADD COLUMN prompt_version TEXT,
    ADD COLUMN check_state    TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (check_state IN ('PENDING', 'DONE', 'FAILED')),
    ADD COLUMN attempt_count  SMALLINT NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    ADD COLUMN confidence     TEXT
        CHECK (confidence IS NULL OR confidence IN ('strong', 'weak'));

COMMENT ON COLUMN cluster_stock.issue_key IS
    '재사용 조회 키(issue_cluster.issue_key 복제). NULL 이면 이 컬럼이 생기기 전 '
    '적재분 — 재사용 조회에서 자연히 제외된다. 생산 파이프라인(-67)이 항상 채운다.';

COMMENT ON COLUMN cluster_stock.prompt_version IS
    'LLM 검증에 쓴 프롬프트 버전(ai/llm-verify-poc/prompts/verify_system_v1.txt 의 '
    "'v1' 같은 값). 재사용 조회는 issue_key+ticker+prompt_version 이 모두 같을 때만 "
    '캐시를 쓴다 — 프롬프트를 올리면 이전 판정은 재사용 대상이 아니다(-49).';

COMMENT ON COLUMN cluster_stock.check_state IS
    "PENDING(아직 시도 안 함) / DONE(판정 완료 — verified 가 true/false 둘 다 유효한 "
    "결과) / FAILED(3회 재시도 후 파킹, verified 는 의미 없음). "
    "verified 단독으로는 '아직 안 됨'과 '검증 실패'가 안 갈려서 분리했다(-50).";

COMMENT ON COLUMN cluster_stock.attempt_count IS
    'GATEWAY 까지 실제로 도달했지만 스키마를 못 지켜 폐기된 시도 횟수(-45 재시도 규칙과는 '
    '별개 — 그건 한 호출 안의 정정 요청이다). 서킷브레이커로 호출 자체가 안 나간 경우는 '
    '안 올린다. 3 도달 시 check_state=FAILED 로 파킹(-50) — 무한 재시도로 장애 복구 '
    '직후 크레딧이 몰리는 걸 막는다.';

COMMENT ON COLUMN cluster_stock.confidence IS
    'LLM 응답의 strong/weak(ai/llm-verify-poc 출력 스키마). 정렬·필터에 아직 안 쓴다 — '
    '필요해지면 화면 계약과 함께 정한다.';

-- 재사용 조회용. UNIQUE 아님(위 설명) — 최근 DONE 행을 찾는 조회를 빠르게 한다.
CREATE INDEX cluster_stock_issue_key_ticker_idx
    ON cluster_stock (issue_key, ticker, prompt_version)
    WHERE check_state = 'DONE';
