package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 대표 텍스트 도입부의 시점 계약 (명세 §6.2, WP-129).
 *
 * <p>🔴 이 파일이 "리플레이는 현재 도입부를 쓰지 않는다" 의 실행 가능한 정의다.
 * 2026-09-18 canary 에서 2025-06-12 이슈의 후보를 현재 도입부로 만들던 것이 결함이었다.
 */
@ExtendWith(MockitoExtension.class)
class ClusterMemberIntrosTest {

    static final OffsetDateTime SNAPSHOT =
            OffsetDateTime.of(2025, 6, 12, 9, 0, 0, 0, ZoneOffset.UTC);

    @Mock
    ClusterIntroRepository repository;
    @Mock
    WikipediaExtractClient wikipedia;

    ClusterMemberIntros intros() {
        return new ClusterMemberIntros(repository, wikipedia);
    }

    static ClusterIntroRepository.ClusterContext context(String source, long pageId, String title) {
        return new ClusterIntroRepository.ClusterContext(source, SNAPSHOT,
                List.of(new ClusterIntroRepository.ClusterContext.Member(pageId, title)));
    }

    @Test
    void 클러스터가_없으면_빈_목록이고_외부호출도_없다() {
        when(repository.context(404L)).thenReturn(Optional.empty());

        assertThat(intros().forCluster(404L)).isEmpty();
        verify(wikipedia, never()).intro(anyString());
    }

    // ------------------------------------------------------------------ LIVE

    @Test
    void live는_현재_도입부를_쓴다() {
        when(repository.context(1L)).thenReturn(Optional.of(context("live", 7L, "Air India Flight 171")));
        when(wikipedia.intro("Air India Flight 171")).thenReturn("Now text.");

        assertThat(intros().forCluster(1L))
                .containsExactly(new IssueRepresentativeText.Member("Air India Flight 171", "Now text."));
        // LIVE 는 지금이 곧 그 시점이라 과거 revision 을 뒤질 이유가 없다.
        verify(wikipedia, never()).revisionAt(anyString(), any());
    }

    // -------------------------------------------------------------- 리플레이

    @Test
    void 리플레이는_고정된_시점_도입부를_쓰고_현재_도입부를_안_본다() {
        when(repository.context(2L)).thenReturn(Optional.of(context("replay", 7L, "Air India Flight 171")));
        when(repository.introAsOf(7L, SNAPSHOT)).thenReturn(Optional.of("Text as of 2025-06-12."));

        assertThat(intros().forCluster(2L))
                .containsExactly(new IssueRepresentativeText.Member(
                        "Air India Flight 171", "Text as of 2025-06-12."));

        // 🔴 이 두 줄이 결함의 회귀 방지다 — 현재 도입부를 한 번이라도 부르면 미래가 섞인다.
        verify(wikipedia, never()).intro(anyString());
        verify(wikipedia, never()).revisionAt(anyString(), any());
    }

    @Test
    void 고정본이_없으면_그_시점_revision을_받아_고정하고_쓴다() {
        when(repository.context(3L)).thenReturn(Optional.of(context("replay", 7L, "Air India Flight 171")));
        when(repository.introAsOf(7L, SNAPSHOT)).thenReturn(Optional.empty());
        var revision = new WikipediaExtractClient.Revision(
                1295306391L, SNAPSHOT.minusMinutes(2), 80194626L);
        when(wikipedia.revisionAt("Air India Flight 171", SNAPSHOT)).thenReturn(Optional.of(revision));
        when(wikipedia.introAt(1295306391L)).thenReturn("Text at that revision.");

        assertThat(intros().forCluster(3L))
                .containsExactly(new IssueRepresentativeText.Member(
                        "Air India Flight 171", "Text at that revision."));

        // 다음 스냅샷이 같은 문서를 다시 받지 않도록 고정한다.
        verify(repository).saveIntro(7L, revision, "Text at that revision.");
        verify(wikipedia, never()).intro(anyString());
    }

    @Test
    void 그_시점에_없던_문서는_현재_도입부로_메우지_않고_빈_도입부로_둔다() {
        // 폴백 금지의 가장 분명한 사례 — 문서가 생기기도 전의 이슈에 그 내용이 들어가면 안 된다.
        when(repository.context(4L)).thenReturn(Optional.of(context("replay", 9L, "Later Article")));
        when(repository.introAsOf(9L, SNAPSHOT)).thenReturn(Optional.empty());
        when(wikipedia.revisionAt("Later Article", SNAPSHOT)).thenReturn(Optional.empty());

        assertThat(intros().forCluster(4L))
                .containsExactly(new IssueRepresentativeText.Member("Later Article", ""));
        verify(wikipedia, never()).intro(anyString());
        verify(wikipedia, never()).introAt(anyLong());
    }

    @Test
    void 과거_도입부_전송실패는_삼키지_않고_전파한다() {
        // 삼켜서 빈 문자열로 돌리면 대표 텍스트가 조용히 얇아지고, 폴러는 그 클러스터를
        // 완료로 보아 다시 안 만든다 (WikipediaExtractClient finding#4 와 같은 함정).
        when(repository.context(5L)).thenReturn(Optional.of(context("replay", 7L, "Iran")));
        when(repository.introAsOf(7L, SNAPSHOT)).thenReturn(Optional.empty());
        when(wikipedia.revisionAt("Iran", SNAPSHOT))
                .thenThrow(new UpstreamUnavailableException("Wikipedia revision 조회 불가",
                        new RuntimeException("504")));

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> intros().forCluster(5L))
                .isInstanceOf(UpstreamUnavailableException.class);
        verify(repository, never()).saveIntro(anyLong(), any(), anyString());
    }
}
