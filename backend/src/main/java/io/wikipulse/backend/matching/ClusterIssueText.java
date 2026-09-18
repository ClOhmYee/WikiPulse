package io.wikipulse.backend.matching;

/**
 * 클러스터 멤버 제목들로부터 이슈 대표 텍스트(§6.2)를 만든다 — LLM 검증(-68) 입력.
 *
 * <p>🔴 제목이 아니라 <b>클러스터 id</b> 를 받는다 (WP-129). 도입부를 어느 시점에서
 * 뽑을지가 클러스터의 {@code source}·{@code snapshot_ts} 에 달렸기 때문이다 — 제목만으로는
 * 리플레이인지 LIVE 인지 알 수 없어 구현이 현재 도입부를 쓸 수밖에 없었다.
 *
 * <p>{@link ClusterEmbeddingSource} 는 같은 대표 텍스트를 만들지만 임베딩 벡터만 돌려준다.
 * 검증은 텍스트 자체가 필요해 이 이음매를 따로 둔다. Wikipedia 도입부 조회의 외부 I/O 를 이
 * 이음매 뒤에 가둬 오케스트레이터가 네트워크 없이 단위 테스트되게 한다.
 */
public interface ClusterIssueText {

    /**
     * @param clusterId 대상 클러스터. 멤버 순서(급등도 내림차순)와 도입부 시점은 구현이 정한다
     * @return 이슈 대표 텍스트. 유효한 도입부가 하나도 없으면 빈 문자열
     */
    String build(long clusterId);
}
