package io.wikipulse.backend.stock.dto;

/**
 * 이슈에 붙은 관련 종목 하나. 이슈 상세와 종목 목록이 공유한다.
 *
 * <p>연관 근거는 상관계수가 아니라 rationale(LLM 이 만든 근거 문장)이다 —
 * 위키 활동과 주가의 상관관계는 학술 결과가 엇갈린다(명세 §9). tier 는
 * 매칭 경로(BOTH / GDELT_ONLY / EMBEDDING_ONLY), matchPath 는 근거 종류다.
 */
public record RelatedStockResponse(
        String ticker,
        String name,
        String exchange,
        String tier,
        String matchPath,
        Double similarity,
        Double gdeltLift,
        String rationale) {
}
