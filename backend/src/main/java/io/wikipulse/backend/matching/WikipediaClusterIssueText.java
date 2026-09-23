package io.wikipulse.backend.matching;

import java.util.List;
import org.springframework.stereotype.Component;

/**
 * {@link ClusterIssueText} 실제 구현: 시점에 맞는 도입부 → LLM 입력 텍스트.
 *
 * <p>🔴 {@link WikipediaGatewayEmbeddingSource} 와 <b>규칙이 다르다</b> (WP-213). 임베딩은 앞
 * N문장(§6.2 변형 D)이고, 여기(LLM 검증·요약)는 도입부 전체다 — 사건 문장이 도입부 끝에 붙어
 * 앞 N문장에서 잘리기 때문이다. 근거는 {@link IssueRepresentativeText#buildFullLead}.
 * 도입부를 어느 시점에서 가져올지는 {@link ClusterMemberIntros} 가 정한다.
 */
@Component
public class WikipediaClusterIssueText implements ClusterIssueText {

    private final ClusterMemberIntros intros;
    private final CandidateProperties props;

    public WikipediaClusterIssueText(ClusterMemberIntros intros, CandidateProperties props) {
        this.intros = intros;
        this.props = props;
    }

    @Override
    public String build(long clusterId) {
        List<IssueRepresentativeText.Member> members = intros.forCluster(clusterId);
        if (members.isEmpty()) {
            return "";
        }
        return IssueRepresentativeText.buildFullLead(members, props.getLlmMaxChars());
    }
}
