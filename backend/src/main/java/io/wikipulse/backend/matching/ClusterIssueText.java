package io.wikipulse.backend.matching;

import java.util.List;

/**
 * 클러스터 멤버 제목들로부터 이슈 대표 텍스트(§6.2)를 만든다 — LLM 검증(-68) 입력.
 *
 * <p>{@link ClusterEmbeddingSource} 는 같은 대표 텍스트를 만들지만 임베딩 벡터만 돌려준다.
 * 검증은 텍스트 자체가 필요해 이 이음매를 따로 둔다. Wikipedia 도입부 조회의 외부 I/O 를 이
 * 이음매 뒤에 가둬 오케스트레이터가 네트워크 없이 단위 테스트되게 한다.
 */
public interface ClusterIssueText {

    /**
     * @param orderedTitles 급등도 내림차순 멤버 제목 (명세 §6.2 순서)
     * @return 이슈 대표 텍스트. 유효한 도입부가 하나도 없으면 빈 문자열
     */
    String build(List<String> orderedTitles);
}
