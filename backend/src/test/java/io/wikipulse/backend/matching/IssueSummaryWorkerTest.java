package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 요약 폴러 계약. 하나가 실패해도 나머지는 돌고(WP-119), 대상 선택에 비용 상한을
 * 넘긴다(WP-165).
 *
 * <p>🔴 상한을 넘기는지 보는 이유: {@code batchSize} 만으로는 비용이 안 묶인다. 폴마다 대상을
 * 새로 고르므로 반복하면 미처리 클러스터 전체를 훑고, 운영 4,474건 전수가 약 277,000 크레딧이다.
 */
@ExtendWith(MockitoExtension.class)
class IssueSummaryWorkerTest {

    @Mock
    IssueSummaryService service;
    @Mock
    IssueSummaryRepository repository;

    final CandidateProperties props = new CandidateProperties();

    @Test
    void 대상_선택에_스냅샷_상한과_모델을_넘긴다() {
        props.getSummary().setBatchSize(7);
        props.getSummary().setTopPerSnapshot(3);
        when(service.modelTag()).thenReturn("claude-x (summary_v1)");
        when(repository.clustersNeedingSummary(anyInt(), anyInt(), anyString()))
                .thenReturn(List.of());

        worker().pollAndSummarize();

        ArgumentCaptor<Integer> limit = ArgumentCaptor.forClass(Integer.class);
        ArgumentCaptor<Integer> top = ArgumentCaptor.forClass(Integer.class);
        ArgumentCaptor<String> model = ArgumentCaptor.forClass(String.class);
        verify(repository).clustersNeedingSummary(limit.capture(), top.capture(), model.capture());
        assertThat(limit.getValue()).isEqualTo(7);
        assertThat(top.getValue()).isEqualTo(3);
        // 🔴 서비스가 저장에 쓰는 것과 같은 model 이어야 한다. 따로 조립하면 조용히 갈려서
        //    재사용 면제가 영영 안 걸리고 매번 LLM 을 부른다.
        assertThat(model.getValue()).isEqualTo("claude-x (summary_v1)");
    }

    @Test
    void 한_클러스터가_실패해도_나머지는_계속_처리된다() {
        when(service.modelTag()).thenReturn("m");
        when(repository.clustersNeedingSummary(anyInt(), anyInt(), anyString()))
                .thenReturn(List.of(1L, 2L, 3L));
        when(service.processCluster(2L)).thenThrow(new RuntimeException("GATEWAY 오류"));

        worker().pollAndSummarize();

        verify(service).processCluster(1L);
        verify(service).processCluster(2L);
        verify(service).processCluster(3L);
    }

    @Test
    void 대상이_없으면_아무것도_하지_않는다() {
        when(service.modelTag()).thenReturn("m");
        when(repository.clustersNeedingSummary(anyInt(), anyInt(), anyString()))
                .thenReturn(List.of());

        worker().pollAndSummarize();

        verify(service, never()).processCluster(anyLong());
    }

    @Test
    void 기본_상한이_무제한이_아니다() {
        // ⚠️ 기본값이 0(무제한)으로 돌아가면 켜는 순간 크레딧을 넘긴다. 기본값 자체를 못 박는다.
        assertThat(new CandidateProperties().getSummary().getTopPerSnapshot()).isPositive();
    }

    private IssueSummaryWorker worker() {
        return new IssueSummaryWorker(service, repository, props);
    }
}
