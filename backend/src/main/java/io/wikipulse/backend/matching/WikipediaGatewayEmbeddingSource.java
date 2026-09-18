package io.wikipulse.backend.matching;

import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * {@link ClusterEmbeddingSource} 실제 구현: 시점에 맞는 도입부 → 대표 텍스트(§6.2) → GATEWAY 임베딩.
 * 도입부를 어느 시점에서 가져올지는 {@link ClusterMemberIntros} 가 정한다 (WP-129).
 */
@Component
public class WikipediaGatewayEmbeddingSource implements ClusterEmbeddingSource {

    private final ClusterMemberIntros intros;
    private final GatewayEmbeddingClient embeddingClient;
    private final CandidateProperties props;

    public WikipediaGatewayEmbeddingSource(
            ClusterMemberIntros intros,
            GatewayEmbeddingClient embeddingClient,
            CandidateProperties props) {
        this.intros = intros;
        this.embeddingClient = embeddingClient;
        this.props = props;
    }

    @Override
    public Optional<float[]> embed(long clusterId) {
        List<IssueRepresentativeText.Member> members = intros.forCluster(clusterId);
        if (members.isEmpty()) {
            return Optional.empty();
        }
        String text = IssueRepresentativeText.build(members, props.getMaxChars());
        if (text.isBlank()) {
            return Optional.empty();
        }
        return Optional.of(embeddingClient.embed(text));
    }
}
