package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import io.wikipulse.backend.matching.IssueSummaryRepository.PriorSummary;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 요약 writer·라이프사이클 오케스트레이션 (WP-119). DB·LLM 은 목이다 — 상태 전이,
 * 요약 재사용, 멱등 저장, CONFIRMED 두-조건 게이트, 실패→미확정만 본다. 🔴 실 GATEWAY 호출 0.
 */
@ExtendWith(MockitoExtension.class)
class IssueSummaryServiceTest {

    @Mock
    IssueSummaryRepository repository;
    @Mock
    VerificationRepository verificationRepository;
    @Mock
    ClusterIssueText issueText;
    @Mock
    IssueSummarizer summarizer;

    final CandidateProperties props = new CandidateProperties();

    IssueSummaryService service() {
        return new IssueSummaryService(repository, verificationRepository, issueText, summarizer, props);
    }

    @BeforeEach
    void commonStubs() {
        lenient().when(verificationRepository.issueKeyOf(anyLong())).thenReturn("iran-2026-08");
        lenient().when(verificationRepository.topOrgMentions(anyLong(), anyInt()))
                .thenReturn(List.of("Reuters"));
        lenient().when(issueText.build(anyLong())).thenReturn("Iran: ...");
        // 기본: 재사용 캐시 미스 — 대부분 테스트는 새 생성 경로를 본다.
        lenient().when(repository.findPriorSummary(anyLong(), anyString(), anyString()))
                .thenReturn(Optional.empty());
        lenient().when(repository.advanceToVerifying(anyLong())).thenReturn(1);
        lenient().when(repository.confirm(anyLong())).thenReturn(1);
    }

    @Test
    void DETECTED면_VERIFYING으로_올리고_요약을_생성_저장한다() {
        when(repository.statusOf(1L)).thenReturn("DETECTED");
        when(repository.hasReport(1L)).thenReturn(false);
        when(summarizer.summarize(any())).thenReturn(ok("이란 이슈 요약."));
        when(repository.stockVerificationComplete(1L)).thenReturn(false); // 종목 미완료 → 확정 보류

        IssueSummaryService.Result r = service().processCluster(1L);

        verify(repository).advanceToVerifying(1L);
        ArgumentCaptor<String> model = ArgumentCaptor.forClass(String.class);
        verify(repository).upsertReport(eq(1L), eq("이란 이슈 요약."), model.capture());
        assertThat(model.getValue()).contains("summary_v1"); // 모델 + 프롬프트 버전 기록
        // WP-213: 입력 규칙도 기록 — 앞 N문장으로 쓴 옛 요약을 재사용하지 않게
        assertThat(model.getValue()).contains(IssueRepresentativeText.LLM_INPUT_VERSION);
        assertThat(r.summarized()).isTrue();
        assertThat(r.confirmed()).isFalse();
        verify(repository, never()).confirm(anyLong());
    }

    @Test
    void 요약_완료_AND_종목검증_완료면_CONFIRMED로_전이한다() {
        when(repository.statusOf(2L)).thenReturn("VERIFYING");
        when(repository.hasReport(2L)).thenReturn(true);       // 요약 이미 있음
        when(repository.stockVerificationComplete(2L)).thenReturn(true); // 종목 검증 끝

        IssueSummaryService.Result r = service().processCluster(2L);

        // 요약이 이미 있으면 생성/재사용을 안 한다(멱등).
        verify(summarizer, never()).summarize(any());
        verify(repository, never()).upsertReport(anyLong(), anyString(), anyString());
        verify(repository).confirm(2L);
        assertThat(r.confirmed()).isTrue();
    }

    @Test
    void 통과_종목_0개도_요약_AND_검증_완료면_정상_CONFIRMED다() {
        // stockVerificationComplete 는 PENDING 0 만 본다 — 전부 탈락(0 통과)이어도 완료다(§10 11번).
        when(repository.statusOf(3L)).thenReturn("VERIFYING");
        when(repository.hasReport(3L)).thenReturn(true);
        when(repository.stockVerificationComplete(3L)).thenReturn(true);

        assertThat(service().processCluster(3L).confirmed()).isTrue();
        verify(repository).confirm(3L);
    }

    @Test
    void 종목검증_미완료면_요약이_있어도_확정하지_않는다() {
        // PENDING 이 남아 있음(전송 실패 재시도 대기) → 아직 검증 중 → CONFIRMED 금지.
        when(repository.statusOf(4L)).thenReturn("VERIFYING");
        when(repository.hasReport(4L)).thenReturn(true);
        when(repository.stockVerificationComplete(4L)).thenReturn(false);

        assertThat(service().processCluster(4L).confirmed()).isFalse();
        verify(repository, never()).confirm(anyLong());
    }

    @Test
    void 요약_근거부족이면_저장하지_않고_확정하지_않는다() {
        when(repository.statusOf(5L)).thenReturn("VERIFYING");
        when(repository.hasReport(5L)).thenReturn(false);
        when(summarizer.summarize(any()))
                .thenReturn(failed(IssueSummarizer.Failure.INSUFFICIENT_CONTEXT));
        // 요약이 없으니 stockVerificationComplete 를 볼 것도 없다.

        IssueSummaryService.Result r = service().processCluster(5L);

        verify(repository, never()).upsertReport(anyLong(), anyString(), anyString());
        verify(repository, never()).confirm(anyLong());
        assertThat(r.summarized()).isFalse();
        assertThat(r.confirmed()).isFalse();
    }

    @Test
    void 요약_전송실패는_전파되고_확정하지_않는다() {
        when(repository.statusOf(6L)).thenReturn("VERIFYING");
        when(repository.hasReport(6L)).thenReturn(false);
        when(summarizer.summarize(any()))
                .thenThrow(new UpstreamUnavailableException("GATEWAY 불가", new RuntimeException()));

        assertThatThrownBy(() -> service().processCluster(6L))
                .isInstanceOf(UpstreamUnavailableException.class);

        verify(repository, never()).upsertReport(anyLong(), anyString(), anyString());
        verify(repository, never()).confirm(anyLong());
    }

    @Test
    void 같은_issue_key의_이전_요약이_있으면_복사하고_LLM을_안_부른다() {
        when(repository.statusOf(7L)).thenReturn("VERIFYING");
        when(repository.hasReport(7L)).thenReturn(false);
        when(repository.findPriorSummary(eq(7L), eq("iran-2026-08"), anyString()))
                .thenReturn(Optional.of(new PriorSummary("이전 스냅샷 요약.", "claude-x (summary_v1)")));
        when(repository.stockVerificationComplete(7L)).thenReturn(false);

        IssueSummaryService.Result r = service().processCluster(7L);

        // LLM 0 — 크레딧 절약. 이전 요약·모델을 그대로 복사 upsert.
        verify(summarizer, never()).summarize(any());
        verify(repository).upsertReport(7L, "이전 스냅샷 요약.", "claude-x (summary_v1)");
        assertThat(r.reused()).isTrue();
        assertThat(r.summarized()).isFalse();
    }

    @Test
    void 재사용_후_종목검증_완료면_같은_폴에서_CONFIRMED된다() {
        // 재사용(EnsureResult(true,true)) 후 confirm 블록으로 fall-through 해 확정되는 경로 —
        // ensureSummary 재사용 분기가 조기 return 하도록 리팩터되는 회귀를 막는다.
        when(repository.statusOf(20L)).thenReturn("VERIFYING");
        when(repository.hasReport(20L)).thenReturn(false);
        when(repository.findPriorSummary(eq(20L), eq("iran-2026-08"), anyString()))
                .thenReturn(Optional.of(new PriorSummary("복사된 요약.", "claude-x (summary_v1)")));
        when(repository.stockVerificationComplete(20L)).thenReturn(true);

        IssueSummaryService.Result r = service().processCluster(20L);

        verify(summarizer, never()).summarize(any());
        verify(repository).confirm(20L);
        assertThat(r.reused()).isTrue();
        assertThat(r.confirmed()).isTrue();
    }

    @Test
    void confirm_경합에서_지면_confirmed는_false다() {
        // 다른 폴러가 먼저 CONFIRMED 로 올려 가드 UPDATE 가 0행이면 confirmed=false.
        when(repository.statusOf(21L)).thenReturn("VERIFYING");
        when(repository.hasReport(21L)).thenReturn(true);
        when(repository.stockVerificationComplete(21L)).thenReturn(true);
        when(repository.confirm(21L)).thenReturn(0); // 경합 패배

        assertThat(service().processCluster(21L).confirmed()).isFalse();
    }

    @Test
    void issue_key가_null이면_재사용조회를_안_하고_생성한다() {
        when(repository.statusOf(8L)).thenReturn("VERIFYING");
        when(repository.hasReport(8L)).thenReturn(false);
        when(verificationRepository.issueKeyOf(8L)).thenReturn(null); // V1 옛 클러스터
        when(summarizer.summarize(any())).thenReturn(ok("생성 요약."));
        when(repository.stockVerificationComplete(8L)).thenReturn(false);

        service().processCluster(8L);

        verify(repository, never()).findPriorSummary(anyLong(), anyString(), anyString());
        verify(summarizer).summarize(any());
    }

    @Test
    void CONFIRMED_클러스터는_건너뛴다() {
        when(repository.statusOf(9L)).thenReturn("CONFIRMED");

        IssueSummaryService.Result r = service().processCluster(9L);

        verify(repository, never()).advanceToVerifying(anyLong());
        verify(summarizer, never()).summarize(any());
        verify(repository, never()).confirm(anyLong());
        assertThat(r.confirmed()).isFalse();
    }

    @Test
    void DISCARDED_클러스터는_건너뛴다() {
        when(repository.statusOf(10L)).thenReturn("DISCARDED");

        service().processCluster(10L);

        verify(repository, never()).advanceToVerifying(anyLong());
        verify(summarizer, never()).summarize(any());
        verify(repository, never()).upsertReport(anyLong(), anyString(), anyString());
    }

    @Test
    void GDELT_기관명을_요약_입력으로_넘긴다_테마지역은_없다() {
        when(repository.statusOf(11L)).thenReturn("VERIFYING");
        when(repository.hasReport(11L)).thenReturn(false);
        when(verificationRepository.topOrgMentions(eq(11L), anyInt()))
                .thenReturn(List.of("NextEra Energy", "Duke Energy"));
        when(summarizer.summarize(any())).thenReturn(ok("요약."));
        when(repository.stockVerificationComplete(11L)).thenReturn(false);

        ArgumentCaptor<IssueSummarizer.Input> in = ArgumentCaptor.forClass(IssueSummarizer.Input.class);
        service().processCluster(11L);

        verify(summarizer).summarize(in.capture());
        assertThat(in.getValue().gdeltContext()).isEqualTo("NextEra Energy, Duke Energy");
        assertThat(in.getValue().issueText()).isEqualTo("Iran: ...");
    }

    @Test
    void 요약_저장에_실패하면_시도를_원장에_남긴다() {
        // 🔴 WP-182. 안 남기면 hasReport 가 계속 false 라 다음 폴에서 같은
        //    클러스터를 또 집는다 — 종료 조건이 없는 재시도다. 운영에서 51분에 5,414
        //    크레딧이 이렇게 나갔다.
        when(repository.statusOf(20L)).thenReturn("VERIFYING");
        when(repository.hasReport(20L)).thenReturn(false);
        when(summarizer.summarize(any()))
                .thenReturn(failed(IssueSummarizer.Failure.INSUFFICIENT_CONTEXT));

        service().processCluster(20L);

        verify(repository).recordFailedAttempt(eq(20L), anyString(),
                eq("INSUFFICIENT_CONTEXT"));
        verify(repository, never()).upsertReport(anyLong(), anyString(), anyString());
    }

    @Test
    void 스키마_위반은_근거부족과_다른_사유로_남는다() {
        // 원인도 대책도 다르다 — 근거 부족은 입력을 고쳐야 풀리고 스키마 위반은 프롬프트다.
        when(repository.statusOf(21L)).thenReturn("VERIFYING");
        when(repository.hasReport(21L)).thenReturn(false);
        when(summarizer.summarize(any()))
                .thenReturn(failed(IssueSummarizer.Failure.SCHEMA_VIOLATION));

        service().processCluster(21L);

        verify(repository).recordFailedAttempt(eq(21L), anyString(), eq("SCHEMA_VIOLATION"));
    }

    @Test
    void 전송_실패는_원장에_남기지_않는다() {
        // 🔴 일시 장애라 재시도해야 한다. 여기 남기면 GATEWAY 가 잠깐 죽은 동안 상한을 태워
        //    멀쩡한 클러스터가 영영 요약되지 않는다.
        when(repository.statusOf(22L)).thenReturn("VERIFYING");
        when(repository.hasReport(22L)).thenReturn(false);
        when(summarizer.summarize(any()))
                .thenThrow(new UpstreamUnavailableException("GATEWAY 불가", new RuntimeException()));

        assertThatThrownBy(() -> service().processCluster(22L))
                .isInstanceOf(UpstreamUnavailableException.class);

        verify(repository, never()).recordFailedAttempt(anyLong(), anyString(), anyString());
    }

    @Test
    void 요약에_성공하면_원장에_남기지_않는다() {
        when(repository.statusOf(23L)).thenReturn("VERIFYING");
        when(repository.hasReport(23L)).thenReturn(false);
        when(summarizer.summarize(any())).thenReturn(ok("요약."));
        when(repository.stockVerificationComplete(23L)).thenReturn(false);

        service().processCluster(23L);

        verify(repository, never()).recordFailedAttempt(anyLong(), anyString(), anyString());
    }

    // ---- WP-182: summarize 가 Optional 대신 Outcome 을 돌려준다 ----

    private static IssueSummarizer.Outcome ok(String summaryKo) {
        return new IssueSummarizer.Outcome(
                Optional.of(summaryKo), IssueSummarizer.Failure.NONE);
    }

    private static IssueSummarizer.Outcome failed(IssueSummarizer.Failure failure) {
        return new IssueSummarizer.Outcome(Optional.empty(), failure);
    }
}
