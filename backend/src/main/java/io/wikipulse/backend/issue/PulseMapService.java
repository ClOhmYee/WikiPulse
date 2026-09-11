package io.wikipulse.backend.issue;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.QueryParams;
import io.wikipulse.backend.issue.PulseMapRepository.ClusterRow;
import io.wikipulse.backend.issue.PulseMapRepository.EdgeRow;
import io.wikipulse.backend.issue.PulseMapRepository.NodeRow;
import io.wikipulse.backend.issue.PulseMapRepository.SnapshotMeta;
import io.wikipulse.backend.issue.dto.pulse.PulseMap;
import io.wikipulse.backend.issue.dto.pulse.SnapshotView;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 펄스맵 스냅샷·그래프 조회 서비스 (WP-74).
 *
 * <p>지도 응답은 한 스냅샷의 원자적 그래프다. 클러스터·노드·간선을 각각 한 번씩
 * 벌크로 읽어 cluster_id 로 묶는다(N+1 없음). 없는 시점은 404 이고 현재 데이터로
 * 대체하지 않는다. DISCARDED 는 리포지토리 질의에서 빠진다.
 */
@Service
@Transactional(readOnly = true)
public class PulseMapService {

    /** 시각은 주어졌으나 출처가 없으면 LIVE 로 본다(피드와 일관). */
    private static final String DEFAULT_SOURCE = "live";

    private final PulseMapRepository repo;

    public PulseMapService(PulseMapRepository repo) {
        this.repo = repo;
    }

    /** GET /issues/snapshots — 완료된 선택 가능 스냅샷 목록. meta 없음. */
    public ApiResponse<List<SnapshotView>> snapshots(Instant from, Instant to, String source) {
        String src = QueryParams.source(source);
        List<SnapshotView> data = repo.findSnapshots(from, to, src).stream()
                .map(SnapshotView::from).toList();
        return ApiResponse.of(data);
    }

    /** GET /issues/map — 한 스냅샷의 그래프. 없으면 404. */
    public ApiResponse<PulseMap.Data> map(Instant snapshotTs, String source) {
        String src = QueryParams.source(source);

        SnapshotMeta meta = resolve(snapshotTs, src);

        Instant ts = meta.getSnapshotTs();
        String resolvedSource = meta.getSource();

        Map<Long, List<PulseMap.Node>> nodesByCluster = groupNodes(ts, resolvedSource);
        Map<Long, List<PulseMap.Edge>> edgesByCluster = groupEdges(ts, resolvedSource);

        List<PulseMap.Cluster> clusters = new ArrayList<>();
        long nodeCount = 0;
        long edgeCount = 0;
        for (ClusterRow c : repo.findClusters(ts, resolvedSource)) {
            List<PulseMap.Node> nodes = nodesByCluster.getOrDefault(c.getId(), List.of());
            List<PulseMap.Edge> edges = edgesByCluster.getOrDefault(c.getId(), List.of());
            nodeCount += nodes.size();
            edgeCount += edges.size();
            clusters.add(new PulseMap.Cluster(
                    str(c.getId()),
                    c.getIssueKey(),
                    c.getLabel(),
                    c.getSummary(),
                    c.getCategory(),
                    iso(c.getFirstDetectedAt()),
                    c.getHot(),
                    c.getPulseScore(),
                    c.getStatus(),
                    c.getMemberCount(),
                    nodes,
                    edges));
        }

        PulseMap.Meta responseMeta = new PulseMap.Meta(
                ts.toString(),
                resolvedSource,
                null,                       // dataMode — 운영 산출물엔 안 붙인다
                meta.getScoreVersion(),
                meta.getNewWindowHours(),
                clusters.size(),
                nodeCount,
                edgeCount,
                false);                      // 전체를 반환하므로 잘림 없음

        return ApiResponse.of(new PulseMap.Data(clusters), responseMeta);
    }

    // --- 내부 -------------------------------------------------------------

    private SnapshotMeta resolve(Instant snapshotTs, String src) {
        if (snapshotTs != null) {
            String lookup = (src != null) ? src : DEFAULT_SOURCE;
            return repo.findSnapshot(snapshotTs, lookup).orElseThrow(() ->
                    ApiException.notFound("snapshot %s (%s) not found"
                            .formatted(snapshotTs, lookup)));
        }
        return repo.findLatestSnapshot(src).orElseThrow(() ->
                ApiException.notFound("no snapshot available"));
    }

    private Map<Long, List<PulseMap.Node>> groupNodes(Instant ts, String source) {
        Map<Long, List<PulseMap.Node>> byCluster = new LinkedHashMap<>();
        for (NodeRow n : repo.findNodes(ts, source)) {
            byCluster.computeIfAbsent(n.getClusterId(), k -> new ArrayList<>())
                    .add(new PulseMap.Node(
                            str(n.getPageId()), n.getWiki(), n.getTitle(), n.getIsSeed(),
                            n.getEditCount(), n.getViews(), n.getEditBaseline(),
                            n.getViewBaseline(), n.getSpikeScore(), n.getSizeScore(),
                            n.getCompleteness(), iso(n.getWindowStart()), iso(n.getWindowEnd())));
        }
        return byCluster;
    }

    private Map<Long, List<PulseMap.Edge>> groupEdges(Instant ts, String source) {
        Map<Long, List<PulseMap.Edge>> byCluster = new LinkedHashMap<>();
        for (EdgeRow e : repo.findEdges(ts, source)) {
            PulseMap.Evidence evidence = new PulseMap.Evidence(
                    e.getEvidenceLabel(), e.getEvidenceMonth(), iso(e.getEvidenceObservedAt()));
            byCluster.computeIfAbsent(e.getClusterId(), k -> new ArrayList<>())
                    .add(new PulseMap.Edge(
                            str(e.getId()), str(e.getSourcePageId()), str(e.getTargetPageId()),
                            e.getKind(), e.getDirected(), e.getWeight(), evidence));
        }
        return byCluster;
    }

    /** BIGINT 키를 불투명 문자열로. 정밀도 손실 방지(계약). */
    private static String str(Long id) {
        return id == null ? null : id.toString();
    }

    private static String iso(Instant ts) {
        return ts == null ? null : ts.toString();
    }
}
