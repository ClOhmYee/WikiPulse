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
         * LLM 검증(WP-68)에 쓰는 Anthropic 모델. POC(ai/llm-verify-poc)에서 검증한
         * {@code claude-sonnet-4-5-20250929} 를 그대로 못박는다 — 프롬프트·판정 규칙이 이 모델로
         * 실측됐다(-45 RESULT.md). 모델을 바꾸면 prompt_version 재검토가 필요하다.
         */
        private String verificationModel = "claude-sonnet-4-5-20250929";
        /**
         * 검증 응답 상한 토큰. 응답은 짧은 JSON 하나(6필드)다. POC 는 400 으로 실측했으나,
         * verified=true 는 rationale_en·rationale_ko 두 자유텍스트를 요구하고 한국어는 문자당
         * 토큰이 무거워 400 에서 절단될 수 있다 — 절단되면 파싱 실패로 정정 1회 후 폐기되어
         * 정상 판정이 조용히 누락되고 토큰만 2배 든다. 안전 마진으로 800 을 준다(상한만 늘 뿐
         * 400 에 맞던 응답엔 영향 없음).
         */
        private int verificationMaxTokens = 800;
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
}
