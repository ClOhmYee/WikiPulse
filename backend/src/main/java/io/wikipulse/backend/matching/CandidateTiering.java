package io.wikipulse.backend.matching;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 두 후보 경로(임베딩 Top-K, GDELT lift 상위)를 합집합으로 묶고 tier 를 붙인다 (명세 §6.3).
 *
 * <p>순수 함수다 — 입력은 티커→점수 맵 둘, 출력은 tier 가 붙은 후보 목록. 정렬은
 * 검증 우선순위(BOTH → GDELT_ONLY → EMBEDDING_ONLY)를 따르고, 같은 tier 안에서는
 * 강한 신호부터 온다(BOTH·GDELT_ONLY 는 lift 내림차순, EMBEDDING_ONLY 는 similarity
 * 내림차순). 저장 순서일 뿐 노출 순위는 아니다 — 노출은 LLM 검증 통과분으로 다시 매긴다.
 */
public final class CandidateTiering {

    private CandidateTiering() {
    }

    /**
     * @param embedding 티커 → 코사인 유사도 (임베딩 Top-K 결과)
     * @param gdelt     티커 → GDELT lift (동시 출현 상위 결과)
     */
    public static List<StockCandidate> combine(
            Map<String, Double> embedding, Map<String, Double> gdelt) {

        Set<String> tickers = new LinkedHashSet<>();
        tickers.addAll(gdelt.keySet());
        tickers.addAll(embedding.keySet());

        List<StockCandidate> out = new ArrayList<>(tickers.size());
        for (String ticker : tickers) {
            boolean inEmb = embedding.containsKey(ticker);
            boolean inGdelt = gdelt.containsKey(ticker);
            Double sim = embedding.get(ticker);
            Double lift = gdelt.get(ticker);

            CandidateTier tier;
            if (inEmb && inGdelt) {
                tier = CandidateTier.BOTH;
            } else if (inGdelt) {
                tier = CandidateTier.GDELT_ONLY;
            } else {
                tier = CandidateTier.EMBEDDING_ONLY;
            }
            out.add(new StockCandidate(ticker, tier, sim, lift));
        }

        out.sort(Comparator
                .comparingInt((StockCandidate c) -> priority(c.tier()))
                .thenComparing(c -> -sortScore(c)));
        return out;
    }

    private static int priority(CandidateTier tier) {
        return switch (tier) {
            case BOTH -> 0;
            case GDELT_ONLY -> 1;
            case EMBEDDING_ONLY -> 2;
        };
    }

    /** tier 안 정렬 키. GDELT 가 있는 tier 는 lift, 임베딩 단독은 similarity 로 내림차순. */
    private static double sortScore(StockCandidate c) {
        Double key = c.tier() == CandidateTier.EMBEDDING_ONLY ? c.similarity() : c.gdeltLift();
        return key == null ? Double.NEGATIVE_INFINITY : key;
    }
}
