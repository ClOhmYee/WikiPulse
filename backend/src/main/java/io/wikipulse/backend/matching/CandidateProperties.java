package io.wikipulse.backend.matching;

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

    /** 대표 텍스트 도입부 출처. 명세 §6.2 — prop=extracts&exintro&explaintext, 리다이렉트 추적. */
    public static class Wikipedia {
        private String apiUrl = "https://en.wikipedia.org/w/api.php";
        /** 위키미디어 API 예절 — 연락처를 담은 User-Agent 를 붙인다. */
        private String userAgent = "WikiPulse/0.1 (https://github.com/ClOhmYee/WikiPulse)";

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
    }

    /** LLM 게이트웨이 (명세 §4). text-embedding-3-small, Authorization: Bearer. */
    public static class Gateway {
        private String baseUrl = "https://llm-gateway.example.com";
        private String embeddingModel = "text-embedding-3-small";
        /** 🔴 환경변수 LLM_GATEWAY_KEY. 저장소에 넣지 않는다. */
        private String apiKey = "";

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

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey;
        }
    }

    /**
     * 폴러. 기본 꺼짐 — 서버에서 명시적으로 켠다. CI·로컬 개발에서 조용히 외부 API 를
     * 때리는 것을 막는다. 서비스 자체는 항상 살아 있어 다른 트리거(수동·검증 워커)로 부를 수 있다.
     */
    public static class Scheduler {
        private boolean enabled = false;
        /** 폴 간격 (ISO-8601 Duration). */
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
}
