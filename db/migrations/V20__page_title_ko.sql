-- 문서 표시용 한국어 제목 (WikiPulse ko 표시명)
--
-- ⚠️ 번호가 V14 다음 V20 이다 — **비어 있는 V15~V19 는 의도한 간격이다.**
--    ~~V11~~ → ~~V15~~ → V20 (2026-09-22). 조사 시점엔 V11 이 비어 있었고, 구현을 마칠
--    무렵엔 develop 이 V14 까지 와서 V15 를 잡았다. 그런데 머지 직전에 다시 보니 미머지
--    원격 브랜치 **셋**이 이미 V15 를 쓰고 있었다(-210·-211·-212). V16·V17 로 한 칸씩
--    밀면 그 셋이 충돌을 푸는 과정에서 또 겹칠 수 있어, 멀찍이 떨어진 V20 을 잡았다.
--
--    🔴 같은 번호가 둘이면 한쪽이 **조용히** 건너뛰어진다 — `db/apply_migrations.py` 의
--       원장 키가 정수 version 이고, `docker/postgres/Dockerfile` 은 initdb 알파벳 정렬을
--       맞추려고 V%03d 로 패딩해 복사한다. 둘 다 간격에는 무관하지만 중복에는 취약하다.
--       (V5 중복 WP-117, V11 중복 V12 헤더 주석이 같은 형태다.)
--
--    ⚠️ 새 마이그레이션을 더할 때는 `ls db/migrations` 뿐 아니라 **원격 브랜치까지** 본다.
--       develop 만 보면 이 함정을 못 피한다:
--         for b in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin); do
--             git ls-tree --name-only "$b" db/migrations/; done | sort -u
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

-- =====================================================================
-- 2단 폴백 — Azure Translator 기계 번역 표시명
-- =====================================================================
--
-- 왜 컬럼을 더 두나 (title_ko 에 같이 안 넣는 이유)
--   ko.wikipedia 에 대응 문서가 **없는 문서가 절반이 넘는다**. 운영 스냅샷
--   2026-09-21T12:00:00Z 의 멤버 20건 중 ko 가 있는 건 8건뿐이었다. 나머지는
--   인물·지역 문서라 앞으로도 안 생긴다.
--
--   🔴 그렇다고 번역 결과를 `title_ko` 에 넣으면 **두 가지가 한 컬럼에서 섞인다** —
--      사람이 만든 정식 한국어 문서 제목과, 기계가 만든 표시용 문자열이다. 섞이면
--      나중에 "이 값으로 ko.wikipedia 링크를 만들어도 되나"를 판별할 수 없다.
--      실측된 번역 품질이 그 구분을 요구한다 (2026-09-22, 운영 제목 10건):
--          Jaxson Dart                      -> 잭슨 다트                (좋음)
--          Mark Wood (cricketer)            -> 마크 우드 (크리켓 선수)   (좋음)
--          Thailand at the 2026 Asian Games -> 2026년 아시안 게임에서 태국 (어순 어색)
--          List of Hindi film families      -> 힌디어 영화 가족 목록      (의미 흔들림)
--      ko.wikipedia 의 정식 제목이 아니다. **표시·검색 전용**이다.
--
-- 상태 네 가지 (title_ko 와 같은 음성 캐시 규칙)
--     fallback_checked_at IS NULL                              아직 번역 안 함
--     fallback_checked_at IS NOT NULL AND title_ko_fallback IS NULL   번역했고 결과 없음
--     title_ko_fallback 있음                                    번역 확보
--   ⚠️ 전송 실패·키 미설정에는 checked_at 을 찍지 않는다 — 찍으면 Azure 가 잠깐 죽은
--      사이 지나간 문서가 영구히 영문으로 굳는다. title_ko 와 같은 함정이다.
--
-- 호출 순서는 langlinks 가 먼저다. `title_ko` 가 있으면 번역 대상이 아니다 —
-- 정식 제목이 있는데 기계 번역을 덧붙일 이유가 없고, F0 쿼터도 아낀다.

ALTER TABLE wiki_page
    ADD COLUMN title_ko_fallback            TEXT,
    ADD COLUMN title_ko_fallback_checked_at TIMESTAMPTZ,
    ADD CONSTRAINT wiki_page_title_ko_fallback_not_blank
        CHECK (title_ko_fallback IS NULL OR btrim(title_ko_fallback) <> ''),
    ADD CONSTRAINT wiki_page_title_ko_fallback_checked
        CHECK (title_ko_fallback IS NULL OR title_ko_fallback_checked_at IS NOT NULL);

COMMENT ON COLUMN wiki_page.title_ko_fallback IS
    '표시 전용 기계 번역 제목(Azure Translator, en->ko). '
    '🔴 ko.wikipedia 의 정식 제목이 아니다 — 이 값으로 위키 링크를 만들지 않는다. '
    '🔴 title_ko 와 합치지 않는다. 표시 우선순위는 title_ko > title_ko_fallback > title.';

COMMENT ON COLUMN wiki_page.title_ko_fallback_checked_at IS
    '번역 호출에 성공한 시각. 결과가 있든 없든 찍는다(음성 캐시). '
    '⚠️ 전송 실패·키 미설정에는 찍지 않는다 — 다음 폴에서 다시 시도해야 한다.';

-- 번역 대상(= langlinks 를 끝냈고 ko 가 없으며 아직 번역 안 한 문서) 조회용.
CREATE INDEX wiki_page_title_ko_fallback_pending_idx
    ON wiki_page (id)
    WHERE title_ko IS NULL
      AND title_ko_checked_at IS NOT NULL
      AND title_ko_fallback_checked_at IS NULL;
