package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
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
    void 대상_선택에_스냅샷_상한을_넘긴다() {
        // 🔴 batchSize 만으로는 비용이 안 묶인다 — 폴마다 대상을 새로 고르므로 반복하면
        //    미처리 클러스터 전체(운영 4,474개)를 훑고, 후보마다 LLM 검증이 따라붙는다.
        props.getScheduler().setBatchSize(7);
        props.getScheduler().setTopPerSnapshot(3);
        when(repository.pendingClusterIds(anyInt(), anyInt())).thenReturn(List.of());

        new StockCandidateWorker(service, repository, props).pollAndGenerate();

        verify(repository).pendingClusterIds(7, 3);
    }

    @Test
    void 기본_상한이_무제한이_아니고_요약과_같다() {
        // ⚠️ 0(무제한)으로 돌아가면 켜는 순간 크레딧을 넘긴다.
        // 🔴 요약 상한과 값이 다르면 같은 화면에서 요약은 있는데 종목이 없거나 그 반대가 생긴다.
        CandidateProperties fresh = new CandidateProperties();
        assertThat(fresh.getScheduler().getTopPerSnapshot()).isPositive();
        assertThat(fresh.getScheduler().getTopPerSnapshot())
                .isEqualTo(fresh.getSummary().getTopPerSnapshot());
    }

    @Test
    void 한_클러스터가_실패해도_나머지는_계속_처리된다() {
        when(repository.pendingClusterIds(anyInt(), anyInt()))
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
        when(repository.pendingClusterIds(anyInt(), anyInt())).thenReturn(List.of());

        new StockCandidateWorker(service, repository, props).pollAndGenerate();

        verify(service, never()).generateFor(anyLong());
    }
}
