package io.wikipulse.backend.issue;

import io.wikipulse.backend.common.NotFoundException;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueDetailResponse;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Limit;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class IssueService {

    private static final int DEFAULT_FEED_LIMIT = 50;

    private final IssueClusterRepository clusterRepository;
    private final IssueQueryRepository queryRepository;

    public IssueService(IssueClusterRepository clusterRepository,
                        IssueQueryRepository queryRepository) {
        this.clusterRepository = clusterRepository;
        this.queryRepository = queryRepository;
    }

    /**
     * 이슈 피드. snapshotTs 를 주면 그 시점(리플레이), 안 주면 최근 LIVE 스냅샷.
     * 아직 클러스터가 하나도 없으면 빈 리스트다.
     */
    public List<IssueCardResponse> feed(Instant snapshotTs, String status, Integer limit) {
        Instant target = (snapshotTs != null)
                ? snapshotTs
                : clusterRepository.findLatestLiveSnapshot().orElse(null);
        if (target == null) {
            return List.of();
        }
        int cap = (limit != null && limit > 0) ? limit : DEFAULT_FEED_LIMIT;
        return clusterRepository.findBySnapshot(target, status, Limit.of(cap))
                .stream()
                .map(IssueCardResponse::from)
                .toList();
    }

    public IssueDetailResponse detail(Long id) {
        IssueCluster cluster = clusterRepository.findById(id)
                .orElseThrow(() -> new NotFoundException("이슈 %d 없음".formatted(id)));

        List<String> members = queryRepository.findMemberTitles(id);
        String summary = queryRepository.findSummary(id).orElse(null);
        List<RelatedStockResponse> stocks = queryRepository.findVerifiedStocks(id).stream()
                .map(p -> new RelatedStockResponse(
                        p.getTicker(), p.getName(), p.getExchange(),
                        p.getTier(), p.getMatchPath(),
                        p.getSimilarity(), p.getGdeltLift(), p.getRationale()))
                .toList();

        return IssueDetailResponse.of(cluster, members, summary, stocks);
    }
}
