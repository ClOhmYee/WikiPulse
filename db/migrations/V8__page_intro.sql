-- WP-129 (1번): 시점별 문서 도입부를 고정해 둔다.
--
-- 왜 필요한가
--   후보 생성·LLM 검증의 입력인 이슈 대표 텍스트(명세 §6.2)를 백엔드가 **현재** Wikipedia
--   도입부로 만들고 있었다. LIVE 는 그게 맞지만 리플레이는 틀린다 — 2025-06-12 시점의
--   이슈에 그 이후 두 달치 후속 정보가 섞인 텍스트로 종목을 매칭하고 요약하게 된다.
--   명세 v0.3 §6.2: "리플레이 출처는 snapshot_ts 이하의 마지막 revision" 이고
--   "historical revision 을 확보하지 못했을 때 현재 도입부로 폴백하지 않는다".
--
--   🔴 조용히 틀리는 쪽이다. 현재 도입부도 그럴듯한 영어 문단이라 결과만 봐서는
--      시점이 섞였는지 알 수 없다.
--
-- 왜 테이블인가 (계산해서 쓰고 버리지 않는 이유)
--   1. 같은 문서가 여러 스냅샷·여러 클러스터에 걸쳐 반복해서 필요하다. 매번 두 번의
--      API 왕복(revision 조회 + 그 revision 파싱)을 다시 하면 Wikipedia 를 그만큼 더 때린다.
--   2. 명세가 "도입부와 page ID·revision ID·기준 시각을 **함께 고정**" 하라고 한다.
--      나중에 "이 이슈는 무슨 텍스트로 매칭됐나" 를 되짚을 수 있어야 감사가 된다.
--   3. Wikipedia 에서 문서가 삭제되면 그 revision 은 일반 API 로 다시 못 꺼낸다.
--      한 번 받은 것을 들고 있어야 과거 스냅샷 재현이 계속 가능하다.
--
-- 키를 (page_id, rev_id) 로 잡은 이유
--   조회는 "snapshot_ts 이하의 마지막 revision" 이라 rev_ts 범위 검색이지만, 같은
--   revision 을 두 번 받는 일이 생기므로(다른 스냅샷이 같은 revision 으로 귀결) 저장은
--   revision 단위 멱등이어야 한다. 스냅샷을 키에 넣으면 같은 본문이 스냅샷 수만큼 복제된다.
--
-- ⚠️ wiki_page.id 는 우리 surrogate 다. wikipedia 쪽 page id 는 별도 컬럼(wiki_page_id)에
--    받아 둔다 — 문서 이동(제목 변경) 이력을 나중에 추적하려면 그쪽 식별자가 필요하다.

CREATE TABLE page_intro (
    page_id      BIGINT      NOT NULL REFERENCES wiki_page(id) ON DELETE CASCADE,
    rev_id       BIGINT      NOT NULL,
    rev_ts       TIMESTAMPTZ NOT NULL,
    wiki_page_id BIGINT,
    intro        TEXT        NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (page_id, rev_id)
);

-- "이 문서의 snapshot_ts 이하 마지막 revision" 조회 경로.
CREATE INDEX page_intro_as_of_idx ON page_intro (page_id, rev_ts DESC);

COMMENT ON TABLE page_intro IS
    '시점별 문서 도입부 평문. 리플레이 대표 텍스트(명세 §6.2)의 유일한 출처다. '
    '🔴 여기 없다고 현재 Wikipedia 도입부로 대체하지 않는다 — 그러면 미래 정보가 '
    '과거 이슈에 섞인다 (WP-129).';

COMMENT ON COLUMN page_intro.rev_ts IS
    '그 revision 의 편집 시각. 조회 기준이다 — snapshot_ts 이하 중 가장 큰 rev_ts 를 쓴다.';

COMMENT ON COLUMN page_intro.intro IS
    'action=parse&oldid=&section=0 의 리드 섹션에서 뽑은 평문. '
    '⚠️ prop=extracts 는 revids 를 줘도 **현재** 도입부를 돌려준다(2026-09-18 실측) — '
    '그 경로로는 과거 도입부를 못 만든다.';

COMMENT ON COLUMN page_intro.wiki_page_id IS
    'Wikipedia 쪽 page id. 우리 wiki_page.id 와 다르다. 문서 이동·동명 재생성 추적용이며 '
    '없을 수도 있다(응답에 안 온 경우).';
