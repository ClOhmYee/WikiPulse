package io.wikipulse.backend.matching;

/**
 * 후보가 어느 신호에서 왔는지 (명세 §6.3, cluster_stock.tier CHECK).
 *
 * <p>검증 우선순위는 {@code BOTH} → {@code GDELT_ONLY} → {@code EMBEDDING_ONLY} 다.
 * 두 경로의 교집합은 작아서(Jaccard 0.11 이하, 명세 §11) 합집합이 후보가 된다.
 */
public enum CandidateTier {
    /** 임베딩 Top-K 와 GDELT lift 상위에 모두 든 종목. 두 신호 일치. */
    BOTH,
    /** GDELT 동시 출현 lift 상위 단독. 설명엔 없는 2차 효과를 잡는다. */
    GDELT_ONLY,
    /** 임베딩 코사인 단독. 노이즈가 많아 검증 우선순위 최하위(명세 §6.3 3등급). */
    EMBEDDING_ONLY
}
