package io.wikipulse.backend.matching;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 이슈-종목 후보 생성 워커 설정 (WP-67).
 *
 * <p>K·lift 컷은 실측으로 확정된 값이다 (명세 §6.3, WP-22): 임베딩 Top-20,
 * GDELT Top-10. 기본값을 여기 박되 운영에서 프로파일로 덮을 수 있게 설정으로 뺀다.
 * GATEWAY 키는 🔴 저장소에 넣지 않는다 — 환경변수 {@code LLM_GATEWAY_KEY} 로만 주입한다.
 */
@ConfigurationProperties(prefix = "wikipulse.matching")
public class CandidateProperties {

    /** 이슈 임베딩 ↔ 종목 임베딩 코사인 Top-K (명세 §6.3, 확정 20). */
    private int embeddingTopK = 20;

    /** GDELT 동시 출현 lift 상위 Top-K (명세 §6.3, 확정 10). */
    private int gdeltTopK = 10;

    /** 이슈 대표 텍스트 전체 상한 (명세 §6.2, 2,000자). */
    private int maxChars = 2000;

    private final Wikipedia wikipedia = new Wikipedia();
    private final Gateway gateway = new Gateway();
    private final Scheduler scheduler = new Scheduler();
    private final Verification verification = new Verification();
    private final Summary summary = new Summary();

    public int getEmbeddingTopK() {
        return embeddingTopK;
    }

    public void setEmbeddingTopK(int embeddingTopK) {
        this.embeddingTopK = embeddingTopK;
    }

    public int getGdeltTopK() {
        return gdeltTopK;
    }

    public void setGdeltTopK(int gdeltTopK) {
        this.gdeltTopK = gdeltTopK;
    }

    public int getMaxChars() {
        return maxChars;
    }

    public void setMaxChars(int maxChars) {
        this.maxChars = maxChars;
    }

    public Wikipedia getWikipedia() {
        return wikipedia;
    }

    public Gateway getGateway() {
        return gateway;
    }

    public Scheduler getScheduler() {
        return scheduler;
    }

    public Verification getVerification() {
        return verification;
    }

    public Summary getSummary() {
        return summary;
    }

    /** 대표 텍스트 도입부 출처. 명세 §6.2 — prop=extracts&exintro&explaintext, 리다이렉트 추적. */
    public static class Wikipedia {
        private String apiUrl = "https://en.wikipedia.org/w/api.php";
        /** 위키미디어 API 예절 — 연락처를 담은 User-Agent 를 붙인다. */
        private String userAgent = "WikiPulse/0.1 (https://github.com/ClOhmYee/WikiPulse)";
        /** 🔴 타임아웃 필수 — 없으면 소켓 hang 이 단일 스케줄러 스레드를 영구 정지시킨다. */
        private Duration connectTimeout = Duration.ofSeconds(5);
        private Duration readTimeout = Duration.ofSeconds(10);

        public String getApiUrl() {
            return apiUrl;
        }

        public void setApiUrl(String apiUrl) {
            this.apiUrl = apiUrl;
        }

        public String getUserAgent() {
            return userAgent;
        }

        public void setUserAgent(String userAgent) {
            this.userAgent = userAgent;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }
    }

    /** LLM 게이트웨이 (명세 §4). text-embedding-3-small, Authorization: Bearer. */
    public static class Gateway {
        private String baseUrl = "https://llm-gateway.example.com";
        private String embeddingModel = "text-embedding-3-small";
        /**
         * LLM 검증(WP-68)에 쓰는 모델. 🔴 이름이 {@code claude-} 로 시작하면 Anthropic,
         * 아니면 OpenAI 경로로 나간다 ({@link GatewayVerificationClient}).
         *
         * <p>~~{@code claude-sonnet-4-5-20250929}~~ → <b>{@code gpt-5.4-nano}</b>
         * (2026-09-21, WP-170·-172). 정답셋 3사례 36건에서 32건 정답·<b>오탐 0</b>이고
         * Sonnet 대비 <b>9.8배</b> 싸다(이슈당 1,317 → 134 크레딧). 제일 걱정한 "경쟁사를 배경지식
         * 만으로 통과시키는" 오탐도 안 났다 — CrowdStrike 이슈의 PANW·FTNT·AAL·UAL, PayPal 이슈의
         * V·MA·ADYEY 를 전부 탈락시켰다. 근거: {@code ai/llm-verify-batch-poc/RESULT.md}.
         *
         * <p>⚠️ 프롬프트({@code verify_system_v1.txt})는 Sonnet 으로 실측된 계약이다(-45). 모델만
         * 바꿨고 프롬프트는 안 건드렸다. 되돌리려면 이 값에 {@code claude-*} 를 넣으면 된다.
         *
         * <p>⚠️ 모델이 바뀌면 판정 재사용 키도 바뀐다 — {@link LlmVerifier#verdictVersion} 참고.
         */
        private String verificationModel = "gpt-5.4-nano";
        /**
         * 이슈 요약(WP-119)에 쓰는 모델. 🔴 검증과 <b>분리</b>한다(-172) — 검증은 nano 로
         * 실측했지만 <b>요약은 nano 로 재지 않았다.</b> 한 노브를 공유하면 검증을 내리는 순간
         * 요약 품질이 측정 없이 같이 바뀐다.
         */
        private String summaryModel = "claude-sonnet-4-5-20250929";
        /**
         * 검증 응답 상한 토큰. 응답은 짧은 JSON 하나(6필드)다. POC 는 400 으로 실측했으나,
         * verified=true 는 rationale_en·rationale_ko 두 자유텍스트를 요구하고 한국어는 문자당
         * 토큰이 무거워 400 에서 절단될 수 있다 — 절단되면 파싱 실패로 정정 1회 후 폐기되어
         * 정상 판정이 조용히 누락되고 토큰만 2배 든다. 안전 마진으로 800 을 준다(상한만 늘 뿐
         * 400 에 맞던 응답엔 영향 없음).
         */
        private int verificationMaxTokens = 800;
        /**
         * 이슈 요약(WP-119) 응답 상한 토큰. 검증과 분리한다 — 요약은 사용자 노출용 한국어
         * 1~3문장(대략 200토큰)이라 800이면 충분하지만, 검증 예산({@link #verificationMaxTokens})을
         * 낮추면 요약이 조용히 절단돼 파싱 실패→미저장으로 흐르므로 노브를 나눈다(멀티렌즈 리뷰).
         * 모델은 검증과 같은 Anthropic 모델을 공유한다({@link #verificationModel}).
         */
        private int summaryMaxTokens = 800;
        /** 🔴 환경변수 LLM_GATEWAY_KEY. 저장소에 넣지 않는다. */
        private String apiKey = "";
        /** 🔴 타임아웃 필수. read 는 게이트웨이 p99 지연을 덮게 잡는다(페이로드는 항상 작다). */
        private Duration connectTimeout = Duration.ofSeconds(5);
        private Duration readTimeout = Duration.ofSeconds(30);

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public String getEmbeddingModel() {
            return embeddingModel;
        }

        public void setEmbeddingModel(String embeddingModel) {
            this.embeddingModel = embeddingModel;
        }

        public String getSummaryModel() {
            return summaryModel;
        }

        public void setSummaryModel(String summaryModel) {
            this.summaryModel = summaryModel;
        }

        public String getVerificationModel() {
            return verificationModel;
        }

        public void setVerificationModel(String verificationModel) {
            this.verificationModel = verificationModel;
        }

        public int getVerificationMaxTokens() {
            return verificationMaxTokens;
        }

        public void setVerificationMaxTokens(int verificationMaxTokens) {
            this.verificationMaxTokens = verificationMaxTokens;
        }

        public int getSummaryMaxTokens() {
            return summaryMaxTokens;
        }

        public void setSummaryMaxTokens(int summaryMaxTokens) {
            this.summaryMaxTokens = summaryMaxTokens;
        }

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public Duration getReadTimeout() {
            return readTimeout;
        }

        public void setReadTimeout(Duration readTimeout) {
            this.readTimeout = readTimeout;
        }
    }

    /**
     * 폴러. 기본 꺼짐 — 서버에서 명시적으로 켠다. CI·로컬 개발에서 조용히 외부 API 를
     * 때리는 것을 막는다. 서비스 자체는 항상 살아 있어 다른 트리거(수동·검증 워커)로 부를 수 있다.
     */
    public static class Scheduler {
        /**
         * 스냅샷 하나에서 후보를 만들 클러스터 수 상한 ({@code pulse_score} 상위). 0 이면 무제한.
         *
         * <p>🔴 <b>{@code batchSize} 는 비용 상한이 아니다</b> (WP-176). 폴마다 대상을
         * 새로 고르므로 반복하면 미처리 클러스터 전체를 훑는다 — 운영 4,474개를 다 돌면
         * 후보 10~20개씩 검증이 따라붙어 310k~620k 크레딧이다.
         *
         * <p>⚠️ 후보 생성 자체는 싸다(임베딩 0.04/건). 이 상한의 실제 효과는 그 뒤 <b>검증</b>
         * 호출 수를 묶는 것이다 — {@code VERIFICATION_ENABLED} 가 켜져 있으면 후보가 생기는
         * 즉시 검증이 따라붙는다.
         *
         * <p>🔴 <b>요약 상한과 같은 값이어야 한다</b>({@link Summary#topPerSnapshot}). 다르면
         * 같은 화면에서 요약은 있는데 종목이 없거나 그 반대가 생긴다.
         */
        private int topPerSnapshot = 10;

        /**
         * 대상을 한 출처로 좁힌다 ({@code issue_cluster.source}: {@code live}·{@code replay}).
         * 빈 값이면 전체 — 기본값이라 동작이 바뀌지 않는다.
         *
         * <p>폴러는 최근 스냅샷부터 집으므로 LIVE 가 쌓이는 동안 과거 replay 구간에는
         * 닿지 못한다. 특정 구간을 먼저 채울 때 쓴다(WP-168).
         *
         * <p>🔴 <b>{@link Summary#source} 와 같은 값이어야 한다.</b> 한쪽만 좁히면 같은
         * 화면에서 요약은 있는데 종목이 없거나 그 반대가 생긴다.
         */
        private String source = "";

        private boolean enabled = false;
        /**
         * 폴 간격 (ISO-8601 Duration). ⚠️ 실제 바인딩은 {@code @Scheduled(fixedDelayString=...)}
         * SpEL 이 프로퍼티 키를 직접 읽어 한다(어노테이션은 상수식만 받아 게터를 못 쓴다).
         * 이 필드는 문서·기본값 정의용이며, 어노테이션 기본값과 값을 맞춰 둔다.
         */
        private String fixedDelay = "PT5M";
        /** 한 번에 처리할 클러스터 수 상한. */
        private int batchSize = 20;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getFixedDelay() {
            return fixedDelay;
        }

        public void setFixedDelay(String fixedDelay) {
            this.fixedDelay = fixedDelay;
        }

        public int getTopPerSnapshot() {
            return topPerSnapshot;
        }

        public void setTopPerSnapshot(int topPerSnapshot) {
            this.topPerSnapshot = topPerSnapshot;
        }

        public String getSource() {
            return source;
        }

        public void setSource(String source) {
            this.source = source;
        }

        public int getBatchSize() {
            return batchSize;
        }

        public void setBatchSize(int batchSize) {
            this.batchSize = batchSize;
        }
    }

    /**
     * LLM 검증 워커 (WP-68, 명세 §6.3). 후보 생성 폴러와 같은 이유로 기본 꺼짐 —
     * 서버에서 LLM_GATEWAY_KEY 를 넣고 {@code verification.enabled=true} 로 켠다. 켜기 순서는
     * 후보 생성(-67) 뒤다: 검증할 PENDING 후보가 있어야 의미가 있다.
     */
    public static class Verification {
        private boolean enabled = false;
        /**
         * 폴 간격 (ISO-8601 Duration). {@link Scheduler#fixedDelay} 와 같은 SpEL 바인딩 관습 —
         * {@code @Scheduled} 는 프로퍼티 키를 직접 읽는다. 이 필드는 문서·기본값 정의용.
         */
        private String fixedDelay = "PT5M";
        /** 한 폴에서 검증할 클러스터 수 상한. */
        private int batchSize = 20;
        /**
         * GDELT 컨텍스트에 담을 상위 기관명 수 (cluster_org_mention lift 내림차순).
         * ⚠️ 스키마에 '테마' 컬럼은 없어 기관명만 넣는다 (cluster_org_mention: org_name·lift).
         */
        private int orgContextLimit = 15;
        /**
         * EMBEDDING_ONLY(3등급) 검증을 건너뛰는 문턱. 1·2등급(BOTH·GDELT_ONLY) 확정 통과가
         * 이 값 이상이면 3등급은 호출하지 않는다 (명세 §6.3, WP-22 확정 N=2).
         */
        private int tier3Threshold = 2;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getFixedDelay() {
            return fixedDelay;
        }

        public void setFixedDelay(String fixedDelay) {
            this.fixedDelay = fixedDelay;
        }

        public int getBatchSize() {
            return batchSize;
        }

        public void setBatchSize(int batchSize) {
            this.batchSize = batchSize;
        }

        public int getOrgContextLimit() {
            return orgContextLimit;
        }

        public void setOrgContextLimit(int orgContextLimit) {
            this.orgContextLimit = orgContextLimit;
        }

        public int getTier3Threshold() {
            return tier3Threshold;
        }

        public void setTier3Threshold(int tier3Threshold) {
            this.tier3Threshold = tier3Threshold;
        }
    }

    /**
     * 이슈 요약 writer·상태 전이 워커 (WP-119, 명세 §3.2 7번). 검증 워커와 같은 이유로
     * 기본 꺼짐 — 서버에서 LLM_GATEWAY_KEY 를 넣고 {@code summary.enabled=true} 로 켠다. 요약은 검증과 같은
     * gateway 신뢰성 계층·모델·max_tokens 를 재사용한다(새 GATEWAY 설정 없음).
     */
    public static class Summary {
        private boolean enabled = false;
        /**
         * 폴 간격 (ISO-8601 Duration). {@link Scheduler#fixedDelay} 와 같은 SpEL 바인딩 관습 —
         * {@code @Scheduled} 는 프로퍼티 키를 직접 읽는다. 이 필드는 문서·기본값 정의용.
         */
        private String fixedDelay = "PT5M";
        /** 한 폴에서 처리할 클러스터 수 상한. */
        private int batchSize = 20;
        /**
         * 스냅샷 하나에서 요약할 클러스터 수 상한 ({@code pulse_score} 상위). 0 이면 무제한.
         *
         * <p>🔴 <b>{@link #batchSize} 는 비용 상한이 아니다.</b> 폴마다 대상을 새로 고르므로
         * 반복하면 결국 미처리 클러스터 전체를 훑는다. 실제 상한은 이 값이고, LLM 실호출은
         * 최대 {@code 스냅샷 수 × topPerSnapshot} 이다 (같은 issue_key 는 재사용이라 0).
         *
         * <p>상위 N 을 고르는 축이 화면 정렬과 같다 — 목록·버블맵이 모두
         * {@code pulse_score DESC} 다. 즉 "보여주는 것만 요약한다".
         */
        private int topPerSnapshot = 10;

        /**
         * 대상을 한 출처로 좁힌다. 빈 값이면 전체(기본값).
         * 🔴 <b>{@link Scheduler#source} 와 같은 값이어야 한다</b> — 근거는 거기 적었다.
         */
        private String source = "";

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getFixedDelay() {
            return fixedDelay;
        }

        public void setFixedDelay(String fixedDelay) {
            this.fixedDelay = fixedDelay;
        }

        public int getBatchSize() {
            return batchSize;
        }

        public void setBatchSize(int batchSize) {
            this.batchSize = batchSize;
        }

        public int getTopPerSnapshot() {
            return topPerSnapshot;
        }

        public void setTopPerSnapshot(int topPerSnapshot) {
            this.topPerSnapshot = topPerSnapshot;
        }

        public String getSource() {
            return source;
        }

        public void setSource(String source) {
            this.source = source;
        }
    }
}
