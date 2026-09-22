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
