package io.wikipulse.backend.matching;

import java.util.List;
import org.springframework.stereotype.Component;

/**
 * {@link ClusterIssueText} 실제 구현: 시점에 맞는 도입부 → 대표 텍스트(§6.2).
 * {@link WikipediaGatewayEmbeddingSource} 와 같은 조립 로직을 쓰되 임베딩 대신 텍스트를 돌려준다.
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
        return IssueRepresentativeText.build(members, props.getMaxChars());
    }
}
