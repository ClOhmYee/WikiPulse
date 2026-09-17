package io.wikipulse.backend.matching;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * {@link ClusterIssueText} 실제 구현: Wikipedia 도입부 → 대표 텍스트(§6.2).
 * {@link WikipediaGatewayEmbeddingSource} 와 같은 조립 로직을 쓰되 임베딩 대신 텍스트를 돌려준다.
 */
@Component
public class WikipediaClusterIssueText implements ClusterIssueText {

    private final WikipediaExtractClient wikipedia;
    private final CandidateProperties props;

    public WikipediaClusterIssueText(WikipediaExtractClient wikipedia, CandidateProperties props) {
        this.wikipedia = wikipedia;
        this.props = props;
    }

    @Override
    public String build(List<String> orderedTitles) {
        if (orderedTitles == null || orderedTitles.isEmpty()) {
            return "";
        }
        List<IssueRepresentativeText.Member> members = new ArrayList<>(orderedTitles.size());
        for (String title : orderedTitles) {
            members.add(new IssueRepresentativeText.Member(title, wikipedia.intro(title)));
        }
        return IssueRepresentativeText.build(members, props.getMaxChars());
    }
}
