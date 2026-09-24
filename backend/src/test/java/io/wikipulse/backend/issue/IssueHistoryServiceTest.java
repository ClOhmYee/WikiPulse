package io.wikipulse.backend.issue;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import io.wikipulse.backend.common.ApiException;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class IssueHistoryServiceTest {
    private final IssueClusterRepository clusters = mock(IssueClusterRepository.class);
    private final IssueQueryRepository queries = mock(IssueQueryRepository.class);
    private final IssueService service = new IssueService(clusters, queries);

    @Test
    void 검색_특수문자는_와일드카드가_아닌_문자_그대로_보낸다() {
        when(queries.findHistoryGroups("%100!%!_!!\\%", null, null, 0, 20))
                .thenReturn(List.of());
        service.historyGroups(" 100%_!\\ ", null, null, 0, 20);
        verify(queries).countHistoryGroups("%100!%!_!!\\%", null, null);
        verify(queries).findHistoryGroups("%100!%!_!!\\%", null, null, 0, 20);
    }

    @Test
    void 너무_긴_검색어와_잘못된_상태를_거부한다() {
        assertEquals(ApiException.Code.INVALID_QUERY,
                assertThrows(ApiException.class,
                        () -> service.historyGroups("x".repeat(201), null, null, 0, 20)).code());
        assertEquals(ApiException.Code.INVALID_QUERY,
                assertThrows(ApiException.class,
                        () -> service.historyGroups(null, "DISCARDED", null, 0, 20)).code());
    }

    @Test
    void 리포트_이력은_출처를_뺀_대표_문서_키를_사용한다() {
        IssueCluster anchor = mock(IssueCluster.class);
        when(anchor.getStatus()).thenReturn("CONFIRMED");
        when(anchor.getSource()).thenReturn("replay");
        when(anchor.getIssueKey()).thenReturn("replay:enwiki:A");
        when(clusters.findById(42L)).thenReturn(Optional.of(anchor));
        when(queries.findHistoryReports(42L, "enwiki:A", "replay", 0, 100))
                .thenReturn(List.of());
        service.historyReports(42L, 0, 100);
        verify(queries).countHistoryReports(42L, "enwiki:A", "replay");
    }

    @Test
    void 출처가_맞지_않는_키는_다른_문서와_묶지_않는다() {
        IssueCluster anchor = mock(IssueCluster.class);
        when(anchor.getStatus()).thenReturn("CONFIRMED");
        when(anchor.getSource()).thenReturn("live");
        when(anchor.getIssueKey()).thenReturn("replay:enwiki:A");
        when(clusters.findById(42L)).thenReturn(Optional.of(anchor));
        when(queries.findHistoryReports(42L, null, "live", 0, 100))
                .thenReturn(List.of());
        service.historyReports(42L, 0, 100);
        verify(queries).countHistoryReports(42L, null, "live");
    }
}
