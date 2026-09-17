package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import io.wikipulse.backend.matching.VerificationRepository.CandidateInfo;
import io.wikipulse.backend.matching.VerificationRepository.PendingCandidate;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 검증 오케스트레이션 (WP-68). DB·LLM 은 목이다 — tier 순서·3등급 게이트·상태 전이·
 * 재사용 키 기록만 본다.
 */
@ExtendWith(MockitoExtension.class)
class VerificationServiceTest {

    @Mock
    VerificationRepository repository;
    @Mock
    ClusterIssueText issueText;
    @Mock
    LlmVerifier verifier;
    @Captor
    ArgumentCaptor<VerificationResponse> respCaptor;

    final CandidateProperties props = new CandidateProperties();

    VerificationService service() {
        return new VerificationService(repository, issueText, verifier, props);
    }

    private static VerificationResponse pass() {
        return new VerificationResponse(
                "SECTOR_OR_REGION_EVENT", true, "REGION", "strong", "en", "한국어 근거");
    }

    private static VerificationResponse reject() {
        return new VerificationResponse("SINGLE_COMPANY_EVENT", false, null, null, null, null);
    }

    @BeforeEach
    void commonStubs() {
        // lenient — PENDING 후보가 없으면 조기 반환해 아래 스텁이 안 쓰인다(그 테스트만의 정상 경로).
        lenient().when(issueText.build(any())).thenReturn("issue text");
        lenient().when(repository.memberTitlesByPulse(anyLong())).thenReturn(List.of("Doc"));
        lenient().when(repository.topOrgMentions(anyLong(), org.mockito.ArgumentMatchers.anyInt()))
                .thenReturn(List.of("NextEra Energy", "Duke Energy"));
        lenient().when(repository.issueKeyOf(anyLong())).thenReturn("milton-2024-10");
        lenient().when(repository.candidateInfo(any())).thenReturn(new CandidateInfo("Some Name", "biz"));
    }

    @Test
    void tier_순서대로_검증하고_통과분을_DONE으로_기록한다() {
        // pendingCandidates 는 tier 우선 정렬(BOTH→GDELT_ONLY)로 준다(SQL ORDER BY 는 pgserver 검증).
        // 여기선 서비스가 그 순서를 보존해 처리하는지를 본다.
        when(repository.pendingCandidates(1L)).thenReturn(List.of(
                new PendingCandidate("NEE", CandidateTier.BOTH),
                new PendingCandidate("MNST", CandidateTier.GDELT_ONLY)));
        when(verifier.verify(any())).thenReturn(Optional.of(pass()), Optional.of(reject()));

        VerificationService.Result r = service().verifyCluster(1L);

        assertThat(r.verified()).isEqualTo(1);
        assertThat(r.rejected()).isEqualTo(1);
        // 서비스가 repo 가 준 순서(BOTH 먼저)를 지켜 처리한다.
        InOrder order = inOrder(repository);
        order.verify(repository).recordDone(eq(1L), eq("NEE"), respCaptor.capture(),
                eq("milton-2024-10"), eq("v1"));
        order.verify(repository).recordDone(eq(1L), eq("MNST"), any(), eq("milton-2024-10"), eq("v1"));
        // 🔴 재사용 키(issue_key·prompt_version)와 rationale_ko 가 기록된다.
        assertThat(respCaptor.getValue().rationaleKo()).isEqualTo("한국어 근거");
    }

    @Test
    void tier3는_1_2등급_확정통과가_N이상이면_건너뛴다() {
        when(repository.pendingCandidates(2L)).thenReturn(List.of(
                new PendingCandidate("A", CandidateTier.BOTH),
                new PendingCandidate("B", CandidateTier.GDELT_ONLY),
                new PendingCandidate("C", CandidateTier.EMBEDDING_ONLY)));
        when(verifier.verify(any())).thenReturn(Optional.of(pass()), Optional.of(pass()));
        // tier1·2 두 건 통과 후 집계 = 2 (>= threshold 2) → tier3 스킵.
        when(repository.verifiedPassCountTier12(2L)).thenReturn(2);

        VerificationService.Result r = service().verifyCluster(2L);

        assertThat(r.verified()).isEqualTo(2);
        assertThat(r.tier3Skipped()).isEqualTo(1);
        // C(EMBEDDING_ONLY)는 LLM 호출도, 기록도 안 한다 — PENDING 유지.
        verify(repository, never()).candidateInfo("C");
        verify(repository, never()).recordDone(anyLong(), eq("C"), any(), any(), any());
        verify(repository, never()).recordSchemaFailure(anyLong(), eq("C"));
    }

    @Test
    void tier3는_1_2등급_확정통과가_N미만이면_호출한다() {
        when(repository.pendingCandidates(3L)).thenReturn(List.of(
                new PendingCandidate("A", CandidateTier.BOTH),
                new PendingCandidate("C", CandidateTier.EMBEDDING_ONLY)));
        when(verifier.verify(any())).thenReturn(Optional.of(reject()), Optional.of(pass()));
        when(repository.verifiedPassCountTier12(3L)).thenReturn(0); // 통과 0 < 2 → tier3 발동.

        VerificationService.Result r = service().verifyCluster(3L);

        assertThat(r.tier3Skipped()).isZero();
        verify(repository).recordDone(eq(3L), eq("C"), any(), eq("milton-2024-10"), eq("v1"));
    }

    @Test
    void 스키마_실패는_recordSchemaFailure로_간다() {
        when(repository.pendingCandidates(4L))
                .thenReturn(List.of(new PendingCandidate("X", CandidateTier.BOTH)));
        when(verifier.verify(any())).thenReturn(Optional.empty());

        VerificationService.Result r = service().verifyCluster(4L);

        assertThat(r.schemaFailed()).isEqualTo(1);
        verify(repository).recordSchemaFailure(4L, "X");
        verify(repository, never()).recordDone(anyLong(), any(), any(), any(), any());
    }

    @Test
    void 전송_실패는_전파되고_이미_판정한_후보만_커밋된다() {
        when(repository.pendingCandidates(5L)).thenReturn(List.of(
                new PendingCandidate("OK", CandidateTier.BOTH),
                new PendingCandidate("BOOM", CandidateTier.GDELT_ONLY)));
        // 첫 후보는 통과, 둘째에서 전송 실패.
        when(verifier.verify(any()))
                .thenReturn(Optional.of(pass()))
                .thenThrow(new UpstreamUnavailableException("GATEWAY 불가", new RuntimeException()));

        assertThatThrownBy(() -> service().verifyCluster(5L))
                .isInstanceOf(UpstreamUnavailableException.class);

        // 첫 후보는 DONE 으로 커밋, 둘째는 아무 기록도 없어 PENDING·attempt 미증가로 남는다.
        verify(repository).recordDone(eq(5L), eq("OK"), any(), any(), any());
        verify(repository, never()).recordDone(anyLong(), eq("BOOM"), any(), any(), any());
        verify(repository, never()).recordSchemaFailure(anyLong(), eq("BOOM"));
    }

    @Test
    void PENDING_후보가_없으면_아무것도_안_한다() {
        when(repository.pendingCandidates(9L)).thenReturn(List.of());

        VerificationService.Result r = service().verifyCluster(9L);

        assertThat(r.verified()).isZero();
        verify(verifier, never()).verify(any());
    }

    @Test
    void GDELT_컨텍스트를_후보_입력으로_넘긴다() {
        when(repository.pendingCandidates(6L))
                .thenReturn(List.of(new PendingCandidate("NEE", CandidateTier.BOTH)));
        when(verifier.verify(any())).thenReturn(Optional.of(pass()));

        ArgumentCaptor<LlmVerifier.Input> inputCaptor = ArgumentCaptor.forClass(LlmVerifier.Input.class);
        service().verifyCluster(6L);

        verify(verifier).verify(inputCaptor.capture());
        assertThat(inputCaptor.getValue().gdeltContext()).isEqualTo("NextEra Energy, Duke Energy");
        assertThat(inputCaptor.getValue().issueText()).isEqualTo("issue text");
    }
}
