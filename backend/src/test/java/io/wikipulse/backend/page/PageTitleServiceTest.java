package io.wikipulse.backend.page;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import io.wikipulse.backend.matching.UpstreamUnavailableException;
import io.wikipulse.backend.matching.WikipediaExtractClient;
import io.wikipulse.backend.page.PageTitleRepository.PendingPage;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/** ko 제목 채우기 서비스. 청크 상한·음성 캐시·전송 실패 세 가지를 본다. */
class PageTitleServiceTest {

    private final PageTitleRepository repository = mock(PageTitleRepository.class);
    private final WikipediaExtractClient wikipedia = mock(WikipediaExtractClient.class);
    private final PageTitleService service = new PageTitleService(repository, wikipedia);

    private static List<PendingPage> pages(int count) {
        return IntStream.rangeClosed(1, count)
                .mapToObj(i -> new PendingPage(i, "T" + i)).toList();
    }

    @SuppressWarnings("unchecked")
    private List<Map<Long, String>> capturedRecords() {
        ArgumentCaptor<Map<Long, String>> captor = ArgumentCaptor.forClass(Map.class);
        verify(repository, org.mockito.Mockito.atLeastOnce()).record(captor.capture());
        // 서비스가 청크마다 새 맵을 넘기므로 호출 순서대로 복사해 둔다.
        return new ArrayList<>(captor.getAllValues());
    }

    @Test
    void 대상이_없으면_위키를_부르지_않는다() {
        when(repository.findPending(anyInt())).thenReturn(List.of());

        assertThat(service.enrich(500)).isEqualTo(new PageTitleService.Result(0, 0));
        verify(wikipedia, never()).koTitles(anyList());
        verify(repository, never()).record(org.mockito.ArgumentMatchers.anyMap());
    }

    @Test
    void 한_요청에_50개를_넘기지_않는다() {
        // 🔴 51개부터는 잘림이 아니라 toomanyvalues 에러다(2026-09-22 실측). 120건이면 50/50/20.
        when(repository.findPending(anyInt())).thenReturn(pages(120));
        when(wikipedia.koTitles(anyList())).thenReturn(Map.of());

        service.enrich(500);

        ArgumentCaptor<List<String>> captor = ArgumentCaptor.forClass(List.class);
        verify(wikipedia, org.mockito.Mockito.times(3)).koTitles(captor.capture());
        assertThat(captor.getAllValues().stream().map(List::size)).containsExactly(50, 50, 20);
        assertThat(captor.getAllValues().get(0).get(0)).isEqualTo("T1");
    }

    @Test
    void ko가_없는_문서도_조회완료로_기록한다() {
        // 음성 캐시의 전부. 안 찍으면 ko 없는 절반을 매 폴 다시 물어본다.
        when(repository.findPending(anyInt())).thenReturn(List.of(
                new PendingPage(1, "Hurricane Milton"),
                new PendingPage(2, "Generac")));
        when(wikipedia.koTitles(anyList())).thenReturn(Map.of("Hurricane Milton", "허리케인 밀턴"));

        assertThat(service.enrich(500)).isEqualTo(new PageTitleService.Result(2, 1));

        Map<Long, String> recorded = capturedRecords().get(0);
        Map<Long, String> expected = new HashMap<>();
        expected.put(1L, "허리케인 밀턴");
        expected.put(2L, null);           // 조회했고 ko 없음 — 키는 있고 값이 null 이다
        assertThat(recorded).isEqualTo(expected);
        assertThat(recorded).containsKey(2L);
    }

    @Test
    void 전송_실패는_기록하지_않고_전파한다() {
        // ⚠️ 여기서 삼켜 "ko 없음"으로 찍으면 위키 일시 장애 구간 문서가 영구히 영문으로 굳는다.
        when(repository.findPending(anyInt())).thenReturn(pages(10));
        when(wikipedia.koTitles(anyList()))
                .thenThrow(new UpstreamUnavailableException("회로 개방", null));

        assertThatThrownBy(() -> service.enrich(500))
                .isInstanceOf(UpstreamUnavailableException.class);
        verify(repository, never()).record(org.mockito.ArgumentMatchers.anyMap());
    }

    @Test
    void 앞_청크가_성공했으면_뒤_청크_실패에도_남는다() {
        // 폴 하나가 터져도 이미 확보한 것은 지키고, 못 한 것만 다음 폴이 이어받는다.
        when(repository.findPending(anyInt())).thenReturn(pages(60));
        when(wikipedia.koTitles(anyList()))
                .thenReturn(Map.of("T1", "첫 문서"))
                .thenThrow(new UpstreamUnavailableException("타임아웃", null));

        assertThatThrownBy(() -> service.enrich(500))
                .isInstanceOf(UpstreamUnavailableException.class);

        List<Map<Long, String>> records = capturedRecords();
        assertThat(records).hasSize(1);            // 첫 청크만 기록됐다
        assertThat(records.get(0)).hasSize(50).containsEntry(1L, "첫 문서");
    }
}
