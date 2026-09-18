package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
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
import org.springframework.web.client.RestClientException;

/**
 * 임베딩 소스 이음매 (명세 §6.2). 대표 텍스트 생성·임베딩의 외부 I/O 조합 로직을 목으로 검증한다.
 */
@ExtendWith(MockitoExtension.class)
class WikipediaGatewayEmbeddingSourceTest {

    @Mock
    ClusterMemberIntros intros;
    @Mock
    GatewayEmbeddingClient embeddingClient;

    final CandidateProperties props = new CandidateProperties();

    WikipediaGatewayEmbeddingSource source() {
        return new WikipediaGatewayEmbeddingSource(intros, embeddingClient, props);
    }

    static IssueRepresentativeText.Member member(String title, String intro) {
        return new IssueRepresentativeText.Member(title, intro);
    }

    @Test
    void 멤버가_없으면_빈_결과이고_GATEWAY도_안_부른다() {
        when(intros.forCluster(1L)).thenReturn(List.of());

        assertThat(source().embed(1L)).isEmpty();
        verify(embeddingClient, never()).embed(anyString());
    }

    @Test
    void 모든_도입부가_비면_GATEWAY를_호출하지_않고_빈_결과() {
        when(intros.forCluster(1L)).thenReturn(List.of(member("A", ""), member("B", "   ")));

        assertThat(source().embed(1L)).isEmpty();
        verify(embeddingClient, never()).embed(anyString());
    }

    @Test
    void 도입부가_있으면_대표텍스트를_임베딩해_벡터를_돌려준다() {
        when(intros.forCluster(1L)).thenReturn(List.of(
                member("Hurricane Milton", "A big storm. It hit Florida."),
                member("Florida", "A US state.")));
        float[] vector = {0.1f, 0.2f};
        when(embeddingClient.embed(anyString())).thenReturn(vector);

        assertThat(source().embed(1L)).contains(vector);
    }

    @Test
    void 위키_전이성_실패는_삼키지_않고_전파한다() {
        // WikipediaExtractClient 가 타임아웃·5xx·429 를 예외로 던지면 소스는 그대로 전파해야 한다 —
        // 삼켜 빈 텍스트로 만들면 클러스터가 조기 done 으로 굳는다(finding#4). -66 이후 클라이언트 폴백은
        // 전송 실패를 UpstreamUnavailableException 으로 정규화하므로 실제 표면 타입도 이것이다.
        when(intros.forCluster(anyLong()))
                .thenThrow(new UpstreamUnavailableException("Wikipedia 도입부 호출 불가",
                        new RestClientException("504 Gateway Timeout")));

        assertThatThrownBy(() -> source().embed(1L))
                .isInstanceOf(UpstreamUnavailableException.class);
        verify(embeddingClient, never()).embed(anyString());
    }
}
