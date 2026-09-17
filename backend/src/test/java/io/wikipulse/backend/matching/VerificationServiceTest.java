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
import io.wikipulse.backend.matching.VerificationRepository.Verdict;
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
        // 기본은 캐시 미스 — 대부분의 테스트는 재사용 없이 LLM 판정 경로를 본다(-69).
        lenient().when(repository.findPriorVerdict(anyLong(), any(), any(), any()))
                .thenReturn(Optional.empty());
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

    // ── 판정 재사용 캐시 (WP-69) ──────────────────────────────────────

    @Test
    void 캐시_히트면_LLM을_안_부르고_판정을_복사한다() {
        when(repository.pendingCandidates(10L))
                .thenReturn(List.of(new PendingCandidate("NEE", CandidateTier.BOTH)));
        Verdict prior = new Verdict(true, "REGION", "strong", "복사된 한국어 근거");
        when(repository.findPriorVerdict(10L, "milton-2024-10", "NEE", "v1"))
                .thenReturn(Optional.of(prior));

        VerificationService.Result r = service().verifyCluster(10L);

        // LLM 은 안 부른다 — 크레딧 0.
        verify(verifier, never()).verify(any());
        // 판정을 그대로 복사해 재사용 키와 함께 기록한다.
        verify(repository).recordReused(10L, "NEE", prior, "milton-2024-10", "v1");
        verify(repository, never()).recordDone(anyLong(), any(), any(), any(), any());
        // reused 는 별도 버킷 — verified/rejected 에는 안 잡힌다.
        assertThat(r.reused()).isEqualTo(1);
        assertThat(r.verified()).isZero();
        assertThat(r.rejected()).isZero();
    }

    @Test
    void 캐시_미스면_verify를_부른다() {
        when(repository.pendingCandidates(11L))
                .thenReturn(List.of(new PendingCandidate("NEE", CandidateTier.BOTH)));
        // commonStubs 의 기본 미스(Optional.empty) 사용.
        when(verifier.verify(any())).thenReturn(Optional.of(pass()));

        VerificationService.Result r = service().verifyCluster(11L);

        // 현재 prompt_version 으로 캐시를 조회한 뒤, 미스라 LLM 을 부른다.
        verify(repository).findPriorVerdict(11L, "milton-2024-10", "NEE", "v1");
        verify(verifier).verify(any());
        verify(repository, never()).recordReused(anyLong(), any(), any(), any(), any());
        assertThat(r.reused()).isZero();
        assertThat(r.verified()).isEqualTo(1);
    }

    @Test
    void prompt_version은_캐시_조회_키에_들어간다() {
        // prompt_version 이 다른 이전 판정은 현재 버전 조회에서 미스가 된다(-49): 서비스는 항상
        // 현재 PROMPT_VERSION 으로만 조회하므로, 조회 인자에 "v1" 이 들어가는지로 이 규칙을 본다.
        when(repository.pendingCandidates(12L))
                .thenReturn(List.of(new PendingCandidate("NEE", CandidateTier.BOTH)));
        when(verifier.verify(any())).thenReturn(Optional.of(pass()));

        service().verifyCluster(12L);

        verify(repository).findPriorVerdict(eq(12L), eq("milton-2024-10"), eq("NEE"), eq("v1"));
    }

    @Test
    void issue_key가_null이면_캐시를_안_쓰고_verify를_부른다() {
        when(repository.issueKeyOf(13L)).thenReturn(null); // V2 옛 클러스터.
        when(repository.pendingCandidates(13L))
                .thenReturn(List.of(new PendingCandidate("NEE", CandidateTier.BOTH)));
        when(verifier.verify(any())).thenReturn(Optional.of(pass()));

        VerificationService.Result r = service().verifyCluster(13L);

        // issue_key 가 없으면 조회 자체를 안 한다 — 캐시를 못 쓴다.
        verify(repository, never()).findPriorVerdict(anyLong(), any(), any(), any());
        verify(verifier).verify(any());
        assertThat(r.reused()).isZero();
    }

    @Test
    void 재사용된_verified행은_tier3_게이트_카운트에_반영된다() {
        // BOTH 후보는 캐시 히트로 재사용되어 DB 에 DONE+verified 로 남는다. 그 결과 tier1·2 확정
        // 통과 수가 임계값에 도달하면(DB 조회 verifiedPassCountTier12), EMBEDDING_ONLY 는 건너뛴다.
        when(repository.pendingCandidates(14L)).thenReturn(List.of(
                new PendingCandidate("A", CandidateTier.BOTH),
                new PendingCandidate("B", CandidateTier.GDELT_ONLY),
                new PendingCandidate("C", CandidateTier.EMBEDDING_ONLY)));
        Verdict pass = new Verdict(true, "REGION", "strong", "근거");
        when(repository.findPriorVerdict(eq(14L), eq("milton-2024-10"), eq("A"), eq("v1")))
                .thenReturn(Optional.of(pass));
        when(repository.findPriorVerdict(eq(14L), eq("milton-2024-10"), eq("B"), eq("v1")))
                .thenReturn(Optional.of(pass));
        // 재사용된 두 verified 행이 DONE 으로 남아 DB 카운트가 임계값(2)에 도달한 상태.
        when(repository.verifiedPassCountTier12(14L)).thenReturn(2);

        VerificationService.Result r = service().verifyCluster(14L);

        assertThat(r.reused()).isEqualTo(2);
        assertThat(r.tier3Skipped()).isEqualTo(1);
        // C(EMBEDDING_ONLY)는 캐시 미스(commonStubs 기본)지만 게이트에서 걸려 LLM·기록 안 한다.
        verify(verifier, never()).verify(any());
        verify(repository, never()).recordReused(anyLong(), eq("C"), any(), any(), any());
    }
}
