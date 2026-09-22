-- 문서 표시용 한국어 제목 (WikiPulse ko 표시명)
--
-- ⚠️ 번호. 조사 단계 기록은 "V11" 이었으나 그 사이 develop 에 V11~V14 가 머지됐다.
--    `db/apply_migrations.py` 의 원장 키가 정수 version 이라 같은 번호가 둘이면 한쪽이
--    조용히 건너뛰어진다(V5 중복 WP-117, V11 중복 V12 헤더 주석과 같은 형태).
--    머지 직전에 `ls db/migrations` 를 다시 보고 다음 번호를 쓴다.
--
-- 무엇을 푸는가
--   화면이 영문 raw title(`Hurricane Milton`)을 그대로 보여준다. 사용자에게는
--   ko.wikipedia 대응 제목(`허리케인 밀턴`)을 보여주고 싶다.
--
-- 🔴 `title` 을 번역해 덮어쓰지 않는다. `title` 은 (wiki, title) 자연키의 한쪽이고
--    클러스터링·조회·Clickstream 조인·Wikipedia 링크가 전부 그 값을 쓴다. 표시명은
--    **별도 컬럼**이고, 없으면 화면이 영문으로 떨어진다.
--
-- 왜 컬럼 두 개인가 (음성 캐시)
--   ko 대응이 **없는 문서가 절반이다** — 후보 유니버스 무작위 200건에서 ko 있음
--   49.5%(2026-09-22 실측, `prop=langlinks&lllang=ko`). `title_ko IS NULL` 하나로는
--   "아직 안 물어봤다" 와 "물어봤는데 없다" 가 안 갈려서, 없는 문서를 매 주기 다시
--   위키미디어에 물어보게 된다. `title_ko_checked_at` 이 그 둘을 가른다.
--
--     checked_at IS NULL                      → 아직 조회 안 함 (워커 대상)
--     checked_at IS NOT NULL AND title_ko IS NULL → 조회했고 ko 문서 없음 (재조회 안 함)
--     checked_at IS NOT NULL AND title_ko 있음    → ko 제목 확보
--
--   ⚠️ 전송 실패(타임아웃·5xx·회로개방)에는 checked_at 을 찍지 않는다. 찍으면 위키가
--      잠깐 죽은 사이 지나간 문서가 영구히 영문으로 굳는다. 조용히 틀리는 쪽이다.
--
-- 시점 정합성
--   ⚠️ 이 값은 `cluster_member` 의 편집수·조회수처럼 판정 당시로 고정한 값이 **아니다**.
--      문서당 한 벌만 두므로, 과거 스냅샷을 열면 그 시점엔 아직 없던 한국어 제목이
--      보일 수 있다. 판정 근거 수치가 아니라 표시명이고 폴백이 영문이라 감수한다
--      — 수치 as-of 계약(명세 §5.2)과 혼동하지 말 것.

ALTER TABLE wiki_page
    ADD COLUMN title_ko            TEXT,
    ADD COLUMN title_ko_checked_at TIMESTAMPTZ,
    -- 빈 문자열이 들어오면 화면에 빈 제목이 뜬다. 없으면 NULL 이어야 폴백이 돈다.
    ADD CONSTRAINT wiki_page_title_ko_not_blank
        CHECK (title_ko IS NULL OR btrim(title_ko) <> ''),
    -- 제목이 있으면 반드시 조회 시각이 있다. 역은 성립하지 않는다(= 조회했고 없음).
    ADD CONSTRAINT wiki_page_title_ko_checked
        CHECK (title_ko IS NULL OR title_ko_checked_at IS NOT NULL);

COMMENT ON COLUMN wiki_page.title_ko IS
    '표시 전용 ko.wikipedia 대응 제목. MediaWiki action=query&prop=langlinks&lllang=ko 로 '
    '1회 조회해 재사용한다. NULL 이면 화면이 title(영문)로 떨어진다. '
    '🔴 식별자가 아니다 — 링크·조인·클러스터링은 title 을 쓴다.';

COMMENT ON COLUMN wiki_page.title_ko_checked_at IS
    'langlinks 조회에 성공한 시각. 성공이면 ko 가 있든 없든 찍는다(음성 캐시). '
    '⚠️ 전송 실패에는 찍지 않는다 — 찍으면 위키 일시 장애 구간 문서가 영구 영문이 된다.';

-- 워커 대상(= 아직 조회 안 한 문서) 조회용. 백필이 끝나면 인덱스가 비어 사실상 공짜다.
CREATE INDEX wiki_page_title_ko_pending_idx
    ON wiki_page (id)
    WHERE title_ko_checked_at IS NULL;
