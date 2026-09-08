-- WikiPulse 데이터 모델 v1  (WP-35)
-- 명세: docs/requirements-v0.1.md §3.2, §5
--
-- 설계에서 결정한 것 세 가지. 나머지는 각 테이블 주석에 붙였다.
--
--  1. 위키 문서에 page_id 가 없다.
--     EventStreams recentchange 에 page_id 필드가 없다 (2026-09-08 실측).
--     식별자가 (wiki, title) 뿐이라 대리키를 두고 그 쌍에 UNIQUE 를 건다.
--     문서 이동(rename)이 일어나면 새 행이 생긴다 — MVP 범위에서 감수한다.
--
--  2. 클러스터는 시점의 함수다.
--     버블맵에 시간 슬라이더(리플레이)가 있어서 같은 사건이라도 시점마다
--     구성과 급등도가 다르다. issue_cluster 가 snapshot_ts 를 갖고,
--     LIVE 화면은 가장 최근 snapshot_ts 를, 리플레이는 과거 값을 읽는다.
--
--  3. RDB 는 PostgreSQL 하나다.
--     pgvector 때문에 PG 가 필수이고, 벡터 Top-K 결과에 종목 메타를 붙이는
--     조인이 SQL 한 번에 끝난다. MySQL 을 따로 두지 않는다.
--
-- 상태·등급 컬럼은 ENUM 대신 TEXT + CHECK 다. ENUM 은 값을 추가할 때
-- ALTER TYPE 이 필요하고 롤백이 번거롭다.

CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================================
-- 1. 위키 문서와 편집 신호
-- =====================================================================

CREATE TABLE wiki_page (
    id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    wiki       TEXT        NOT NULL,
    title      TEXT        NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT wiki_page_natural_key UNIQUE (wiki, title)
);

COMMENT ON TABLE wiki_page IS
    '위키 문서. EventStreams 에 page_id 가 없어 (wiki, title) 이 자연키다.';


CREATE TABLE page_edit_window (
    page_id        BIGINT      NOT NULL REFERENCES wiki_page(id) ON DELETE CASCADE,
    window_start   TIMESTAMPTZ NOT NULL,
    window_end     TIMESTAMPTZ NOT NULL,
    edit_count     INTEGER     NOT NULL,
    editor_count   INTEGER     NOT NULL,
    byte_delta_sum BIGINT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (page_id, window_start)
);

COMMENT ON TABLE page_edit_window IS
    'Spark Structured Streaming 의 윈도우 집계 출력. '
    '슬라이딩 윈도우라 편집 1건이 여러 행에 걸친다 — 1시간 윈도우 / 5분 슬라이드면 12행. '
    '급증 판정을 통과한 것만 spike 로 남으므로 이 테이블은 단기 보존한다(디버깅·기준선 재계산용). '
    '보존 기간은 운영하면서 정한다.';

CREATE INDEX page_edit_window_window_start_idx
    ON page_edit_window (window_start DESC);


CREATE TABLE page_view_hourly (
    page_id  BIGINT      NOT NULL REFERENCES wiki_page(id) ON DELETE CASCADE,
    ts_hour  TIMESTAMPTZ NOT NULL,
    views    INTEGER     NOT NULL,
    PRIMARY KEY (page_id, ts_hour)
);

COMMENT ON TABLE page_view_hourly IS
    'Pageviews API 조회수. 급증 2차 판정(편집 전후 조회수 급등)에 쓴다. '
    'API 가 시간 단위라 2차 판정이 최대 1시간 늦다 — 명세 §10 미결 항목.';


CREATE TABLE page_baseline (
    page_id      BIGINT      NOT NULL REFERENCES wiki_page(id) ON DELETE CASCADE,
    hour_of_week SMALLINT    NOT NULL CHECK (hour_of_week BETWEEN 0 AND 167),
    edit_ewma    DOUBLE PRECISION NOT NULL,
    edit_stddev  DOUBLE PRECISION,
    view_ewma    DOUBLE PRECISION,
    sample_days  SMALLINT    NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (page_id, hour_of_week)
);

COMMENT ON TABLE page_baseline IS
    '문서 × 요일·시간대(0~167) 기준선. 28일치를 EWMA 로 굴린다. '
    '동시간대로 나누는 이유는 위키 편집이 요일·시간대를 크게 타기 때문이다. '
    'sample_days 가 적으면(신규 문서) 판정을 보류한다 — 표본이 얇으면 z 값이 폭발한다.';

COMMENT ON COLUMN page_baseline.hour_of_week IS
    '월요일 00시 UTC = 0, 일요일 23시 = 167';


CREATE TABLE spike (
    id           BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    page_id      BIGINT      NOT NULL REFERENCES wiki_page(id) ON DELETE CASCADE,
    detected_at  TIMESTAMPTZ NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    edit_count   INTEGER     NOT NULL,
    edit_z       DOUBLE PRECISION,
    view_ratio   DOUBLE PRECISION,
    spike_score  DOUBLE PRECISION NOT NULL,
    CONSTRAINT spike_unique_window UNIQUE (page_id, window_start)
);

COMMENT ON TABLE spike IS
    '급증 판정을 통과한 문서. 편집 급증(edit_z)과 조회수 급등(view_ratio)을 '
    '둘 다 넘어야 들어온다 — 편집만 튀고 조회수가 안 따라오면 편집 전쟁·정리 작업이다. '
    '판정 수식은 아직 확정 전이라(WP-38) 컬럼만 잡아뒀다.';

COMMENT ON COLUMN spike.view_ratio IS
    'Pageviews 가 1시간 늦어서 판정 시점에 NULL 일 수 있다. NULL = 아직 2차 판정 전.';

CREATE INDEX spike_detected_at_idx ON spike (detected_at DESC);

-- =====================================================================
-- 2. 이슈 클러스터 — 시점별 스냅샷
-- =====================================================================

CREATE TABLE issue_cluster (
    id          BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_ts TIMESTAMPTZ NOT NULL,
    label       TEXT,
    pulse_score DOUBLE PRECISION NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'DETECTED'
                CHECK (status IN ('DETECTED', 'VERIFYING', 'CONFIRMED', 'DISCARDED')),
    source      TEXT        NOT NULL DEFAULT 'live'
                CHECK (source IN ('live', 'replay')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE issue_cluster IS
    '한 시점의 이슈 클러스터. 버블맵의 버블 하나에 대응한다. '
    'LIVE 는 가장 최근 snapshot_ts, 리플레이는 사용자가 고른 시점을 읽는다. '
    'source 로 실시간 파이프라인 산출물과 덤프 재계산 산출물을 구분한다.';

COMMENT ON COLUMN issue_cluster.status IS
    '피드 3단계 노출용. DETECTED(감지됨) → VERIFYING(검증 중) → CONFIRMED(확정). '
    'LLM 검증에서 떨어지면 DISCARDED. 명세 §3.2 7번.';

COMMENT ON COLUMN issue_cluster.label IS
    'LLM 이 붙인 사람이 읽을 제목. 확정 전에는 NULL 이라 화면은 대표 문서명을 쓴다.';

CREATE INDEX issue_cluster_snapshot_idx ON issue_cluster (snapshot_ts DESC, pulse_score DESC);


CREATE TABLE cluster_member (
    cluster_id BIGINT NOT NULL REFERENCES issue_cluster(id) ON DELETE CASCADE,
    page_id    BIGINT NOT NULL REFERENCES wiki_page(id) ON DELETE CASCADE,
    weight     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    is_seed    BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (cluster_id, page_id)
);

COMMENT ON TABLE cluster_member IS
    '클러스터에 묶인 문서. weight 는 Clickstream 이동량 기반 엣지 가중치다.';

COMMENT ON COLUMN cluster_member.is_seed IS
    '급증 판정을 직접 통과한 문서인지. false 면 Clickstream·Wikidata 관계로 딸려온 것.';


CREATE TABLE issue_report (
    cluster_id   BIGINT      PRIMARY KEY REFERENCES issue_cluster(id) ON DELETE CASCADE,
    summary      TEXT        NOT NULL,
    model        TEXT        NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE issue_report IS
    'LLM 이 만든 이슈 요약. 클러스터당 하나. model 을 남겨 나중에 품질 비교가 되게 한다.';

-- =====================================================================
-- 3. 종목
-- =====================================================================

CREATE TABLE stock (
    ticker           TEXT        PRIMARY KEY,
    name             TEXT        NOT NULL,
    exchange         TEXT        NOT NULL,
    cik              TEXT,
    sector           TEXT,
    business_summary TEXT,
    embedding        vector(1536),
    embedded_at      TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE stock IS
    '미국 3대 거래소 보통주 약 5,100종목. 마스터는 SEC company_tickers.json 과 '
    'NASDAQ Trader 심볼 디렉터리에서 받는다. '
    '⚠️ Wikidata 로 티커를 받지 말 것 — wdt:P249 는 40건만 나온다 (CLAUDE.md 폐기 절).';

COMMENT ON COLUMN stock.business_summary IS
    'yfinance longBusinessSummary. 임베딩 입력이다. 표본 200종목 보유율 100% 실측.';

COMMENT ON COLUMN stock.embedding IS
    'text-embedding-3-small(1536차원), LLM 게이트웨이 경유.';

-- 5,100행이면 순차 스캔도 빠르지만, 종목 유니버스를 넓히면 필요해진다.
-- HNSW 는 코사인 거리 기준. 조회 쿼리도 <=> (코사인)을 써야 인덱스를 탄다.
CREATE INDEX stock_embedding_idx ON stock
    USING hnsw (embedding vector_cosine_ops);


CREATE TABLE stock_price (
    ticker     TEXT        NOT NULL REFERENCES stock(ticker) ON DELETE CASCADE,
    trade_date DATE        NOT NULL,
    open       NUMERIC(14, 4),
    high       NUMERIC(14, 4),
    low        NUMERIC(14, 4),
    close      NUMERIC(14, 4) NOT NULL,
    volume     BIGINT,
    PRIMARY KEY (ticker, trade_date)
);

COMMENT ON TABLE stock_price IS
    'yfinance 일봉. 종목 5,100 × 5년 ≈ 640만 행이라 PostgreSQL 로 충분하다 — '
    'HBase 를 넣지 않은 근거다. 가격은 부동소수 반올림 오차를 피하려고 NUMERIC 이다.';

-- =====================================================================
-- 4. 이슈 - 종목 매칭
-- =====================================================================

CREATE TABLE cluster_stock (
    cluster_id  BIGINT NOT NULL REFERENCES issue_cluster(id) ON DELETE CASCADE,
    ticker      TEXT   NOT NULL REFERENCES stock(ticker) ON DELETE CASCADE,
    tier        TEXT   NOT NULL
                CHECK (tier IN ('BOTH', 'GDELT_ONLY', 'EMBEDDING_ONLY')),
    similarity  DOUBLE PRECISION,
    gdelt_lift  DOUBLE PRECISION,
    verified    BOOLEAN NOT NULL DEFAULT false,
    match_path  TEXT
                CHECK (match_path IS NULL OR match_path IN
                       ('DIRECT_MENTION', 'PRODUCT_INDUSTRY', 'SUPPLY_CHAIN', 'REGION')),
    rationale   TEXT,
    verified_at TIMESTAMPTZ,
    PRIMARY KEY (cluster_id, ticker)
);

COMMENT ON TABLE cluster_stock IS
    '이슈에 붙은 종목. 후보 생성은 두 경로의 합집합이고 tier 가 어느 쪽에서 왔는지 남긴다. '
    'BOTH(두 신호 일치) > GDELT_ONLY > EMBEDDING_ONLY 순으로 LLM 검증을 돌린다. '
    '실측상 두 경로의 교집합은 작다 — Jaccard 0.11 이하 (명세 §11).';

COMMENT ON COLUMN cluster_stock.match_path IS
    'LLM 이 판정한 근거 경로. 직접언급 / 제품·산업 / 공급망·고객·경쟁 / 지역 노출. '
    '경로를 못 만들면 verified=false 로 남고 화면에 안 나간다.';

COMMENT ON COLUMN cluster_stock.rationale IS
    '사용자에게 보여줄 근거 문장. 상관계수가 아니라 이 문장이 연관 근거다 — '
    '위키 활동과 주가의 상관관계는 학술 결과가 엇갈린다 (명세 §9).';

CREATE INDEX cluster_stock_ticker_idx ON cluster_stock (ticker) WHERE verified;


CREATE TABLE cluster_org_mention (
    cluster_id    BIGINT NOT NULL REFERENCES issue_cluster(id) ON DELETE CASCADE,
    org_name      TEXT   NOT NULL,
    ticker        TEXT   REFERENCES stock(ticker) ON DELETE SET NULL,
    issue_count   INTEGER NOT NULL,
    corpus_count  INTEGER NOT NULL,
    lift          DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (cluster_id, org_name)
);

COMMENT ON TABLE cluster_org_mention IS
    'GDELT GKG Organizations 동시 출현 집계. lift = P(기업|이슈 기사) / P(기업|전체 기사). '
    'ticker 가 NULL 이면 종목 마스터에 매칭 안 된 기관이다 — 언론사·정부기관이 절반 넘는다. '
    'LLM 검증의 RAG 컨텍스트로도 쓴다.';

-- =====================================================================
-- 5. 회원 · 관심종목 · 알림 · 토론
-- =====================================================================

CREATE TABLE member (
    id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT        NOT NULL UNIQUE,
    display_name  TEXT        NOT NULL,
    password_hash TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN member.password_hash IS
    '자체 로그인용. OAuth 만 쓰기로 하면 NULL 이다 — 인증 방식은 아직 미정.';


CREATE TABLE watchlist (
    member_id BIGINT NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    ticker    TEXT   NOT NULL REFERENCES stock(ticker) ON DELETE CASCADE,
    added_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, ticker)
);


CREATE TABLE notification (
    id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id  BIGINT      NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    cluster_id BIGINT      REFERENCES issue_cluster(id) ON DELETE SET NULL,
    ticker     TEXT        REFERENCES stock(ticker) ON DELETE SET NULL,
    body       TEXT        NOT NULL,
    read_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE notification IS
    '관심종목에 새 이슈가 붙으면 생긴다. 전달 수단(웹 배지·푸시·메일)은 미정이라 '
    '지금은 저장만 하고 읽음 여부만 관리한다.';

CREATE INDEX notification_unread_idx
    ON notification (member_id, created_at DESC) WHERE read_at IS NULL;


CREATE TABLE comment_thread (
    id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id BIGINT      NOT NULL REFERENCES issue_cluster(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT comment_thread_one_per_cluster UNIQUE (cluster_id)
);

COMMENT ON TABLE comment_thread IS '이슈별 토론방. 클러스터당 하나.';


CREATE TABLE thread_comment (
    id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id  BIGINT      NOT NULL REFERENCES comment_thread(id) ON DELETE CASCADE,
    member_id  BIGINT      REFERENCES member(id) ON DELETE SET NULL,
    body       TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

COMMENT ON COLUMN thread_comment.member_id IS
    '탈퇴해도 글은 남긴다. NULL 이면 화면에 "삭제된 사용자".';

CREATE INDEX thread_comment_thread_idx
    ON thread_comment (thread_id, created_at) WHERE deleted_at IS NULL;
