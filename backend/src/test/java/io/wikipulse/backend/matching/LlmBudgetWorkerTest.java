package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

/**
 * 예산이 소진됐을 때 워커가 어떻게 멈추는지 (WP-191).
 *
 * <p>🔴 <b>남은 클러스터를 계속 시도하지 않는다.</b> 어차피 전부 같은 벽에 부딪히므로,
 * 계속 돌면 DB 왕복과 로그만 늘고 얻는 것이 없다. 이번 폴을 끊고 다음 폴에서 이어진다.
 *
 * <p>🔴 <b>전송 실패와 구분된다.</b> 둘 다 클러스터를 미처리로 남기지만 원인이 다르다 —
 * 전송 실패는 재시도하면 될 수도 있고 예산 소진은 내일까지 소용없다. 같은 ERROR 로그로
 * 뭉치면 "왜 요약이 안 붙지" 를 몇 시간 뒤진다(지라 인수 조건 3번).
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class LlmBudgetWorkerTest {

    @Mock
    IssueSummaryService summaryService;
    @Mock
    IssueSummaryRepository summaryRepository;
    @Mock
    VerificationService verificationService;
    @Mock
    VerificationRepository verificationRepository;

    final CandidateProperties props = new CandidateProperties();

    // ------------------------------------------------------------ 요약 워커

    @Test
    void 요약_예산이_소진되면_남은_클러스터를_시도하지_않는다() {
        when(summaryService.modelTag()).thenReturn("m");
        when(summaryRepository.clustersNeedingSummary(
                anyInt(), anyInt(), anyString(), any(), anyInt()))
                .thenReturn(List.of(1L, 2L, 3L));
        when(summaryService.processCluster(2L))
                .thenThrow(new BudgetExceededException(LlmBudget.SUMMARY, 100));

        summaryWorker().pollAndSummarize();

        verify(summaryService).processCluster(1L);
        verify(summaryService).processCluster(2L);
        // 🔴 3L 은 시도조차 하지 않는다 — 같은 벽이다.
        verify(summaryService, never()).processCluster(3L);
    }

    @Test
    void 요약_전송실패는_예산소진과_달리_다음_클러스터로_넘어간다() {
        when(summaryService.modelTag()).thenReturn("m");
        when(summaryRepository.clustersNeedingSummary(
                anyInt(), anyInt(), anyString(), any(), anyInt()))
                .thenReturn(List.of(1L, 2L, 3L));
        when(summaryService.processCluster(2L))
                .thenThrow(new UpstreamUnavailableException("GATEWAY 불가", new RuntimeException()));

        summaryWorker().pollAndSummarize();

        verify(summaryService).processCluster(3L);
    }

    // ------------------------------------------------------------ 검증 워커

    @Test
    void 검증_예산이_소진되면_남은_클러스터를_시도하지_않는다() {
        when(verificationRepository.clustersWithPending(anyInt())).thenReturn(List.of(1L, 2L, 3L));
        when(verificationService.verifyCluster(2L))
                .thenThrow(new BudgetExceededException(LlmBudget.VERIFICATION, 300));

        verificationWorker().pollAndVerify();

        verify(verificationService).verifyCluster(1L);
        verify(verificationService, never()).verifyCluster(3L);
    }

    @Test
    void 검증_전송실패는_다음_클러스터로_넘어간다() {
        when(verificationRepository.clustersWithPending(anyInt())).thenReturn(List.of(1L, 2L, 3L));
        when(verificationService.verifyCluster(2L))
                .thenThrow(new UpstreamUnavailableException("GATEWAY 불가", new RuntimeException()));

        verificationWorker().pollAndVerify();

        verify(verificationService).verifyCluster(3L);
    }

    // ------------------------------------------------------------ 기본값

    @Test
    void 예산_기본값이_무제한이_아니다() {
        // ⚠️ 0 이하로 돌아가면 이 이슈 이전 동작이다. 기본값 자체를 못 박는다.
        CandidateProperties.Budget budget = new CandidateProperties().getBudget();

        assertThat(budget.getSummaryCalls()).isPositive();
        assertThat(budget.getVerificationCalls()).isPositive();
    }

    @Test
    void 요약과_검증_예산이_따로다() {
        // 🔴 한 통이면 검증이 요약을 굶는다 — 이슈당 검증은 후보 수만큼, 요약은 1회다.
        CandidateProperties.Budget budget = new CandidateProperties().getBudget();

        assertThat(budget.getVerificationCalls()).isNotEqualTo(budget.getSummaryCalls());
    }

    private IssueSummaryWorker summaryWorker() {
        return new IssueSummaryWorker(summaryService, summaryRepository, props);
    }

    private VerificationWorker verificationWorker() {
        return new VerificationWorker(verificationService, verificationRepository, props);
    }
}
