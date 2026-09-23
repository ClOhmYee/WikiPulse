package io.wikipulse.backend.page;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 문서 표시용 한국어 제목 채우기 워커 설정.
 *
 * <p>🔴 <b>기본 꺼짐.</b> 이 저장소의 모든 폴러가 그렇다 — 명시적으로 켜기 전에는 바깥으로
 * 나가는 호출이 0이다. GATEWAY 폴러들과 달리 크레딧을 쓰지는 않지만(위키미디어는 무료), 켜는
 * 순간 미조회 문서 전량을 훑기 시작하므로 운영이 시점을 고른다.
 *
 * <p>{@code wikipulse.matching.*} 밑에 두지 않았다. 이슈-종목 매칭과 아무 관계가 없고,
 * 매칭 폴러를 켜고 끄는 것과 독립으로 켜고 꺼야 한다.
 */
@ConfigurationProperties(prefix = "wikipulse.page-title")
public class PageTitleProperties {

    private boolean enabled;

    private Duration fixedDelay = Duration.ofMinutes(10);

    /**
     * 한 폴에서 처리할 문서 수. 🔴 위키미디어 요청 수는 이 값 / 50 이다
     * ({@link io.wikipulse.backend.matching.WikipediaExtractClient#TITLES_PER_REQUEST}).
     * 기본 500 이면 폴당 10 요청 — RateLimiter(초당 10)와 같은 자릿수라 한 폴이 1초 남짓 문다.
     */
    private int batchSize = 500;

    private final Azure azure = new Azure();

    public Azure getAzure() {
        return azure;
    }

    /**
     * 2단 폴백 — Azure Translator (en→ko). ko.wikipedia 에 대응 문서가 없는 문서만 대상이다.
     *
     * <p>🔴 키는 저장소에 넣지 않는다. {@code AZURE_TRANSLATOR_KEY} 환경변수로만 주입한다.
     * 비어 있으면 번역 단계를 통째로 건너뛰고 영문으로 표시한다 — 기능이 깨지지 않는다.
     */
    public static class Azure {
        /** 🔴 절대 기본값을 넣지 않는다. 빈 값 = 번역 끔. */
        private String key = "";
        private String endpoint = "https://api.cognitive.microsofttranslator.com";
        /** 리소스 지역(예: koreacentral). 전역 엔드포인트에는 이 헤더가 필요하다. */
        private String region = "";
        /** 🔴 타임아웃 필수 — 소켓 hang 이 단일 스케줄러 스레드를 영구 정지시킨다. */
        private Duration connectTimeout = Duration.ofSeconds(5);
        private Duration readTimeout = Duration.ofSeconds(10);
        /**
         * 한 폴에서 번역할 문서 수 상한. F0 는 월 200만 자라 무제한으로 두지 않는다.
         * 위키 조회(batch-size)와 별개 축이다 — 번역은 쿼터를 쓴다.
         */
        private int batchSize = 200;

        public String getKey() {
            return key;
        }

        public void setKey(String key) {
            this.key = key;
        }

        public String getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(String endpoint) {
            this.endpoint = endpoint;
        }

        public String getRegion() {
            return region;
        }

        public void setRegion(String region) {
            this.region = region;
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

        public int getBatchSize() {
            return batchSize;
        }

        public void setBatchSize(int batchSize) {
            this.batchSize = batchSize;
        }
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getFixedDelay() {
        return fixedDelay;
    }

    public void setFixedDelay(Duration fixedDelay) {
        this.fixedDelay = fixedDelay;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
