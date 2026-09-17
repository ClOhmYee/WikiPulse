package io.wikipulse.backend.matching;

import java.util.List;
import java.util.Optional;

/**
 * 클러스터 멤버 제목들로부터 이슈 임베딩 벡터를 만든다 (명세 §3.2 5번, §6.2).
 *
 * <p>대표 텍스트 생성(Wikipedia 도입부)·임베딩(GATEWAY)의 외부 I/O 를 이 이음매 뒤에 가둔다.
 * 서비스는 이 인터페이스만 알아서 네트워크 없이 단위 테스트가 된다.
 *
 * <p>이슈 임베딩은 후보 생성 시 만들고 저장하지 않는다. LLM 판정 결과는
 * {@code (issue_key, ticker, prompt_version)}으로 재사용한다(WP-49).
 */
public interface ClusterEmbeddingSource {

    /**
     * @param orderedTitles 급등도 내림차순 멤버 제목 (명세 §6.2 순서)
     * @return 이슈 임베딩. 유효한 도입부가 하나도 없어 대표 텍스트가 비면 {@link Optional#empty()}
     */
    Optional<float[]> embed(List<String> orderedTitles);
}
