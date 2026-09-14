package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * 후보 생성 오케스트레이션 (WP-67). DB·네트워크는 목이다 — 조합·전달만 본다.
 */
@ExtendWith(MockitoExtension.class)
class StockCandidateServiceTest {

    @Mock
    CandidateRepository repository;
    @Mock
    ClusterEmbeddingSource embeddingSource;
    @Captor
    ArgumentCaptor<List<StockCandidate>> candidatesCaptor;

    final CandidateProperties props = new CandidateProperties();

    StockCandidateService service() {
        return new StockCandidateService(repository, embeddingSource, props);
    }

    @Test
    void 확정된_K값으로_두_경로를_뽑아_합집합을_적재한다() {
        float[] vector = {0.1f, 0.2f};
        when(repository.memberTitlesByPulse(42L)).thenReturn(List.of("Hurricane Milton", "Florida"));
        when(embeddingSource.embed(List.of("Hurricane Milton", "Florida")))
                .thenReturn(Optional.of(vector));
        when(repository.embeddingTopK(vector, 20)).thenReturn(Map.of("NEE", 0.31));
        when(repository.gdeltTopK(42L, 10)).thenReturn(Map.of("NEE", 10.5, "GNRC", 9.3));
        when(repository.replaceCandidates(eq(42L), candidatesCaptor.capture())).thenReturn(2);

        StockCandidateService.Result result = service().generateFor(42L);

        // K 는 명세 §6.3 확정값 (임베딩 20 / GDELT 10)
        verify(repository).embeddingTopK(vector, 20);
        verify(repository).gdeltTopK(42L, 10);

        assertThat(candidatesCaptor.getValue())
                .extracting(StockCandidate::ticker, StockCandidate::tier)
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple("NEE", CandidateTier.BOTH),
                        org.assertj.core.groups.Tuple.tuple("GNRC", CandidateTier.GDELT_ONLY));
        assertThat(result.embeddingCandidates()).isEqualTo(1);
        assertThat(result.gdeltCandidates()).isEqualTo(2);
        assertThat(result.stored()).isEqualTo(2);
    }

    @Test
    void 대표_텍스트가_비면_임베딩_경로를_건너뛰고_GDELT만으로_적재한다() {
        when(repository.memberTitlesByPulse(7L)).thenReturn(List.of("Some Title"));
        when(embeddingSource.embed(List.of("Some Title"))).thenReturn(Optional.empty());
        when(repository.gdeltTopK(7L, 10)).thenReturn(Map.of("DAL", 6.0));
        when(repository.replaceCandidates(eq(7L), candidatesCaptor.capture())).thenReturn(1);

        service().generateFor(7L);

        verify(repository, never()).embeddingTopK(org.mockito.ArgumentMatchers.any(), anyInt());
        assertThat(candidatesCaptor.getValue())
                .singleElement()
                .satisfies(c -> {
                    assertThat(c.ticker()).isEqualTo("DAL");
                    assertThat(c.tier()).isEqualTo(CandidateTier.GDELT_ONLY);
                });
    }
}
