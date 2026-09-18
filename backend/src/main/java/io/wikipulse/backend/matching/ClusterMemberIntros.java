package io.wikipulse.backend.matching;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 클러스터 멤버의 도입부를 <b>그 클러스터의 시점에 맞게</b> 모은다 (명세 §6.2, WP-129).
 *
 * <p>대표 텍스트를 쓰는 두 경로({@link WikipediaGatewayEmbeddingSource} 후보 생성,
 * {@link WikipediaClusterIssueText} LLM 검증)가 같은 규칙을 쓰도록 여기 한 곳에 둔다.
 * 이전에는 두 클래스가 각자 {@code wikipedia.intro(title)} 를 돌려 <b>현재</b> 도입부를 썼다.
 *
 * <h2>왜 시점을 따지나</h2>
 * 2026-09-18 canary 에서 2025-06-12 이슈의 후보를 만들면서 백엔드가 현재 Wikipedia 도입부를
 * 읽었다. 그러면 사건 이후 두 달치 후속 정보가 섞인 텍스트로 종목을 매칭하고 요약한다 —
 * 결과만 봐서는 시점이 섞인 걸 알 수 없는, 조용히 틀리는 종류다.
 *
 * <h2>경로</h2>
 * <ul>
 *   <li><b>LIVE</b>({@code issue_cluster.source='live'}) — 현재 도입부가 곧 그 시점 도입부다.
 *       {@code prop=extracts} 를 그대로 쓴다
 *   <li><b>리플레이</b> — {@code page_intro} 에 고정된 {@code snapshot_ts} 이하 도입부를 읽는다.
 *       없으면 그 시점 revision 을 받아 와 고정하고 쓴다
 * </ul>
 *
 * <p>🔴 <b>리플레이에서 현재 도입부로 폴백하지 않는다</b> (명세 §6.2). 과거 revision 을 못
 * 받으면 그 문서를 빼는 게 아니라 <b>예외를 던져 클러스터를 미완료로 남긴다</b> — 빼면 대표
 * 텍스트가 조용히 얇아지고, 폴러는 그 클러스터를 완료로 보아 다시 안 만든다
 * ({@link WikipediaExtractClient} finding#4 와 같은 함정).
 *
 * <p>⚠️ 단, "그 시점에 문서가 없었다"(revision 자체가 없음)는 실패가 아니라 정상 답이라
 * 그 멤버만 빠진다. 사건 당일 생긴 문서가 몇 시간 전 스냅샷에 딸려 오는 경우가 여기다.
 */
@Component
public class ClusterMemberIntros {

    private static final Logger log = LoggerFactory.getLogger(ClusterMemberIntros.class);

    private final ClusterIntroRepository repository;
    private final WikipediaExtractClient wikipedia;

    public ClusterMemberIntros(ClusterIntroRepository repository, WikipediaExtractClient wikipedia) {
        this.repository = repository;
        this.wikipedia = wikipedia;
    }

    /**
     * 급등도 내림차순 멤버와 그 시점 도입부. 클러스터가 없거나 멤버가 없으면 빈 목록.
     *
     * @throws UpstreamUnavailableException 전이성 실패로 과거 도입부를 못 받았을 때
     */
    public List<IssueRepresentativeText.Member> forCluster(long clusterId) {
        Optional<ClusterIntroRepository.ClusterContext> found = repository.context(clusterId);
        if (found.isEmpty()) {
            return List.of();
        }
        ClusterIntroRepository.ClusterContext context = found.get();
        List<IssueRepresentativeText.Member> members = new ArrayList<>(context.members().size());
        for (ClusterIntroRepository.ClusterContext.Member member : context.members()) {
            String intro = context.isReplay()
                    ? replayIntro(context, member)
                    : wikipedia.intro(member.title());
            members.add(new IssueRepresentativeText.Member(member.title(), intro));
        }
        return members;
    }

    /**
     * {@code snapshot_ts} 이하 revision 의 도입부. 고정된 게 있으면 그걸 쓰고, 없으면 받아서 고정한다.
     *
     * <p>받아 온 도입부가 비어도(리드 섹션에 문단이 없는 문서) 그대로 고정한다 — 안 그러면
     * 스냅샷마다 같은 문서를 다시 받는다. 빈 도입부는 대표 텍스트에서 줄이 빠질 뿐이다.
     */
    private String replayIntro(
            ClusterIntroRepository.ClusterContext context,
            ClusterIntroRepository.ClusterContext.Member member) {
        Optional<String> pinned = repository.introAsOf(member.pageId(), context.snapshotTs());
        if (pinned.isPresent()) {
            return pinned.get();
        }
        Optional<WikipediaExtractClient.Revision> revision =
                wikipedia.revisionAt(member.title(), context.snapshotTs());
        if (revision.isEmpty()) {
            // 그 시점에 없던 문서다. 현재 도입부로 메우면 문서가 생기기도 전의 이슈에
            // 그 문서 내용이 들어간다 — 폴백 금지의 가장 분명한 사례다.
            log.info("시점 도입부 없음(그때 문서가 없었다) page={} title={} as_of={}",
                    member.pageId(), member.title(), context.snapshotTs());
            return "";
        }
        String intro = wikipedia.introAt(revision.get().revId());
        repository.saveIntro(member.pageId(), revision.get(), intro);
        return intro;
    }
}
