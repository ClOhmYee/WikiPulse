package io.wikipulse.backend.stock.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 이슈에 붙은 관련 종목. API 명세 v0.2 §2 `/issues/{id}/stocks`.
 * 이슈 상세와 종목쪽이 공유한다.
 *
 * <p>verified=true 만 나간다(규칙). 정렬은 tier → gdeltLift → similarity.
 * rationale 이 연관 근거다 — 상관계수가 아니다(명세 §9).
 * similarity·gdeltLift 는 그 경로로 안 들어온 후보면 null.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record RelatedStockResponse(
        String ticker,
        String name,
        String exchange,
        String sector,
        String tier,
        String matchPath,
        Double similarity,
        Double gdeltLift,
        String rationale) {

    public interface Projection {
        String getTicker();
        String getName();
        String getExchange();
        String getSector();
        String getTier();
        String getMatchPath();
        Double getSimilarity();
        Double getGdeltLift();
        String getRationale();
    }

    public static RelatedStockResponse from(Projection p) {
        return new RelatedStockResponse(
                p.getTicker(), p.getName(), p.getExchange(), p.getSector(),
                p.getTier(), p.getMatchPath(), p.getSimilarity(),
                p.getGdeltLift(), p.getRationale());
    }
}
