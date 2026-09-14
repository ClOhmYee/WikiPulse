package io.wikipulse.backend.matching;

/**
 * 이슈 하나에 붙는 종목 후보 한 건. cluster_stock 한 행에 대응한다 (verified=false).
 *
 * <p>{@code similarity} 는 임베딩 경로에서만, {@code gdeltLift} 는 GDELT 경로에서만
 * 채워진다 — tier 에 따라 한쪽 또는 양쪽이 있다(GDELT_ONLY 면 similarity 가 null).
 * 근거 경로(match_path)·근거 문장(rationale)·검증 여부는 LLM 검증 단계(명세 §6.3, 별도
 * 이슈)가 채우므로 여기서는 만들지 않는다.
 */
public record StockCandidate(
        String ticker,
        CandidateTier tier,
        Double similarity,
        Double gdeltLift) {
}
