-- as-of revision 아웃링크 캐시 (WP-161, CORE 클러스터링)
--
-- ⚠️ ~~V11~~ → V12 로 리넘버 (2026-09-22). develop 에 `V11__issue_summary_attempt.sql`
--    이 먼저 머지돼 같은 번호가 둘이 됐다. `db/apply_migrations.py` 의 원장 키가
--    정수 version 이라 두 파일이 같은 번호면 한쪽이 조용히 건너뛰어진다(WP-117
--    이 V5 중복에서 겪은 것과 같은 형태). 머지 안 된 이쪽을 옮겼다.
--
-- CORE 는 "같은 스냅샷 root 끼리 판정 당시 revision 에 직접 링크가 있었는가" 로 묶는다.
-- 그 링크는 `action=parse&oldid=<spike.max_rev_id>&prop=wikitext` 한 번으로 얻는데,
-- 리플레이 한 판이 root 수만큼 요청을 낸다. 실측 기준 22,080 revision 이다 — 캐시가
-- 없으면 재계산할 때마다 위키미디어를 그만큼 다시 때린다.
--
-- 🔴 **revision 단위 캐시라 영구히 유효하다.** 특정 oldid 의 wikitext 는 불변이다.
--    시간이 지나도 다시 받을 이유가 없고, 만료도 필요 없다.
--
-- 🔴 **파일이 아니라 DB 에 둔 이유** — Spark driver 와 worker 가 서로 다른 서버다
--    (EC2 2노드). 로컬 sqlite/파일 캐시는 노드마다 갈리고, 어느 쪽이 맞는지 알 수 없게
--    된다. 어차피 판정 결과를 쓰는 DB 가 이미 공유 자원이다.
--
-- `links` 에 담는 것
--   revision wikitext 의 **리터럴 `[[...]]` 중 ns0 만**, `asof_links.link_key` 로
--   정규화한 제목의 정렬된 배열.
--
--   ⚠️ `parse.links`(렌더된 링크)를 담지 않는다. MediaWiki 는 옛 revision 을 렌더할
--      때도 **템플릿은 현재 판**을 쓴다 — navbox 가 스냅샷 이후에 얻은 링크가 섞여
--      들어오고, 그건 미래 정보 누수다. 에러 없이 조용히 틀린다.
--
-- `error` 의 뜻
--   수집을 시도했으나 실패했다(HTTP·API 오류). 행이 아예 없는 것과 구분한다 —
--   전자는 "재시도 대상", 후자는 "아직 안 해 봄" 이다. 둘 다 CORE 에서는 링크 없음
--   으로 취급해 singleton 이 되며, **현재 판으로 폴백하지 않는다.**

CREATE TABLE page_asof_links (
    rev_id     BIGINT      PRIMARY KEY,
    wiki       TEXT        NOT NULL,
    title      TEXT        NOT NULL,
    links      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    link_count INTEGER     NOT NULL DEFAULT 0 CHECK (link_count >= 0),
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error      TEXT,
    CONSTRAINT page_asof_links_links_is_array CHECK (jsonb_typeof(links) = 'array')
);

COMMENT ON TABLE page_asof_links IS
    'revision 단위 as-of 아웃링크 캐시. CORE 클러스터링(WP-161)의 입력. '
    'oldid 의 wikitext 는 불변이라 만료가 없다.';

COMMENT ON COLUMN page_asof_links.rev_id IS
    'spike.max_rev_id — 판정 시점의 마지막 revision. replay 는 과거 판, LIVE 는 '
    '관측 시점의 판이며 둘 다 같은 계약이다.';

COMMENT ON COLUMN page_asof_links.links IS
    'wikitext 리터럴 [[...]] 중 ns0 만, link_key 정규화 후 정렬한 배열. '
    'parse.links 가 아니다 — 옛 revision 을 렌더해도 템플릿은 현재 판이라 누수된다.';

COMMENT ON COLUMN page_asof_links.link_count IS
    'links 의 길이. focus 분모로 매번 jsonb_array_length 를 돌리지 않으려고 둔다.';

COMMENT ON COLUMN page_asof_links.error IS
    'NULL = 정상 수집. 값이 있으면 시도했으나 실패한 것이며, 행이 없는 상태('
    '아직 시도 안 함)와 구분한다. 둘 다 CORE 에서는 링크 없음(singleton)이고 '
    '현재 판으로 폴백하지 않는다.';

-- 재시도 대상(실패 행)을 싸게 고르는 경로.
CREATE INDEX page_asof_links_error_idx ON page_asof_links (fetched_at)
    WHERE error IS NOT NULL;
