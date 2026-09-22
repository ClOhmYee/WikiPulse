package io.wikipulse.backend.issue;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.PageMeta;
import io.wikipulse.backend.common.QueryParams;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueRankingsResponse;
import io.wikipulse.backend.issue.dto.IssueDetailResponse;
import io.wikipulse.backend.issue.dto.IssueMemberResponse;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class IssueService {

    /** 상세 진입 시 미리 담는 관련 종목 수 (명세 §2). 전체는 /issues/{id}/stocks. */
    private static final int DETAIL_STOCK_PREVIEW = 5;

    private final IssueClusterRepository clusterRepository;
    private final IssueQueryRepository queryRepository;

    public IssueService(IssueClusterRepository clusterRepository,
                        IssueQueryRepository queryRepository) {
        this.clusterRepository = clusterRepository;
        this.queryRepository = queryRepository;
    }

    public ApiResponse<IssueRankingsResponse> rankings() {
        return rankings(Instant.now());
    }

    ApiResponse<IssueRankingsResponse> rankings(Instant asOf) {
        var local = asOf.atZone(ZoneId.of("Asia/Seoul"));
        var monthFrom = local.minusDays(30).toInstant();
        var yearFrom = local.minusYears(1).toInstant();
        return ApiResponse.of(new IssueRankingsResponse(
                asOf.toString(), monthFrom.toString(), yearFrom.toString(),
                queryRepository.findRankings(monthFrom, asOf).stream()
                        .map(IssueRankingsResponse.Entry::from).toList(),
                queryRepository.findRankings(yearFrom, asOf).stream()
                        .map(IssueRankingsResponse.Entry::from).toList()));
    }

    /** 이슈 피드 / 버블맵. 봉투 + pagination·snapshotTs meta. */
    public ApiResponse<List<IssueCardResponse>> feed(
            Instant snapshotTs, String status, String source, Integer offset, Integer limit) {

        int off = QueryParams.offset(offset);
        int lim = QueryParams.limit(limit);
        List<String> statuses = QueryParams.statuses(status);
        String src = QueryParams.source(source);

        // 시각 미지정이면 요청한 출처의 최신 스냅샷(출처도 없으면 최신 LIVE,
        // 없으면 최신 replay). /issues/map 과 같은 규칙이라 두 화면이 같은 시점을 본다.
        Instant target = (snapshotTs != null)
                ? snapshotTs
                : clusterRepository.findLatestSnapshot(src).orElse(null);

        // 아직 스냅샷이 하나도 없으면 빈 목록 + total 0.
        if (target == null) {
            return ApiResponse.of(List.of(),
                    PageMeta.of(PageMeta.Pagination.of(off, lim, 0, 0)));
        }

        long total = clusterRepository.countCards(target, statuses, src);
        List<IssueCardResponse> cards = clusterRepository
                .findCards(target, statuses, src, off, lim)
                .stream().map(IssueCardResponse::from).toList();

        return ApiResponse.of(cards, new PageMeta(
                PageMeta.Pagination.of(off, lim, total, cards.size()),
                target.toString()));
    }

    public ApiResponse<IssueDetailResponse> detail(Long id) {
        IssueCluster cluster = clusterRepository.findById(id)
                .filter(c -> !"DISCARDED".equals(c.getStatus()))
                .orElseThrow(() -> ApiException.notFound("issue %d not found".formatted(id)));

        List<IssueMemberResponse> members = queryRepository.findMembers(id).stream()
                .map(IssueMemberResponse::from).toList();
        String summary = queryRepository.findSummary(id).orElse(null);
        String summaryModel = queryRepository.findSummaryModel(id).orElse(null);
        List<RelatedStockResponse> stocks = queryRepository
                .findVerifiedStocks(id, DETAIL_STOCK_PREVIEW)
                .stream().map(RelatedStockResponse::from).toList();

        return ApiResponse.of(
                IssueDetailResponse.of(cluster, summary, summaryModel, members, stocks));
    }

    /** /issues/{id}/stocks — 전체 관련 종목. */
    public ApiResponse<List<RelatedStockResponse>> stocks(Long id, Integer limit) {
        if (!clusterRepository.existsById(id)) {
            throw ApiException.notFound("issue %d not found".formatted(id));
        }
        int lim = QueryParams.limit(limit);
        List<RelatedStockResponse> stocks = queryRepository.findVerifiedStocks(id, lim)
                .stream().map(RelatedStockResponse::from).toList();
        return ApiResponse.of(stocks);
    }
}
