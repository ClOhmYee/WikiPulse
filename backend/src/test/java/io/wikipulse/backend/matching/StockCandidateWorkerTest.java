package io.wikipulse.backend.matching;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 폴러 계약 (WP-67): 클러스터 하나가 실패해도 나머지는 계속 처리한다.
 */
@ExtendWith(MockitoExtension.class)
class StockCandidateWorkerTest {

    @Mock
    StockCandidateService service;
    @Mock
    CandidateRepository repository;

    final CandidateProperties props = new CandidateProperties();

    @Test
    void 한_클러스터가_실패해도_나머지는_계속_처리된다() {
        when(repository.pendingClusterIds(props.getScheduler().getBatchSize()))
                .thenReturn(List.of(1L, 2L, 3L));
        when(service.generateFor(1L)).thenReturn(new StockCandidateService.Result(1L, 1, 1, 1));
        when(service.generateFor(2L)).thenThrow(new RuntimeException("GATEWAY 오류"));
        when(service.generateFor(3L)).thenReturn(new StockCandidateService.Result(3L, 1, 1, 1));

        new StockCandidateWorker(service, repository, props).pollAndGenerate();

        // 2L 에서 던져도 예외가 폴러 밖으로 새지 않고 1L·3L 모두 시도된다.
        verify(service).generateFor(1L);
        verify(service).generateFor(2L);
        verify(service).generateFor(3L);
    }

    @Test
    void 대상이_없으면_아무것도_하지_않는다() {
        when(repository.pendingClusterIds(anyInt())).thenReturn(List.of());

        new StockCandidateWorker(service, repository, props).pollAndGenerate();

        verify(service, never()).generateFor(anyLong());
    }
}
