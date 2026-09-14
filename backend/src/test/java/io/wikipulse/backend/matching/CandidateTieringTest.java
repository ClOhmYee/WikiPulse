package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * 후보 합집합·tier 규칙 (명세 §6.3). 교집합 BOTH, 나머지는 각 경로 단독.
 */
class CandidateTieringTest {

    @Test
    void 교집합은_BOTH_이고_similarity와_lift를_모두_갖는다() {
        var embedding = Map.of("NEE", 0.31);
        var gdelt = Map.of("NEE", 10.5);

        List<StockCandidate> out = CandidateTiering.combine(embedding, gdelt);

        assertThat(out).singleElement().satisfies(c -> {
            assertThat(c.ticker()).isEqualTo("NEE");
            assertThat(c.tier()).isEqualTo(CandidateTier.BOTH);
            assertThat(c.similarity()).isEqualTo(0.31);
            assertThat(c.gdeltLift()).isEqualTo(10.5);
        });
    }

    @Test
    void GDELT_단독은_similarity가_null() {
        List<StockCandidate> out = CandidateTiering.combine(Map.of(), Map.of("GNRC", 9.3));

        assertThat(out).singleElement().satisfies(c -> {
            assertThat(c.tier()).isEqualTo(CandidateTier.GDELT_ONLY);
            assertThat(c.similarity()).isNull();
            assertThat(c.gdeltLift()).isEqualTo(9.3);
        });
    }

    @Test
    void 임베딩_단독은_lift가_null() {
        List<StockCandidate> out = CandidateTiering.combine(Map.of("INTC", 0.22), Map.of());

        assertThat(out).singleElement().satisfies(c -> {
            assertThat(c.tier()).isEqualTo(CandidateTier.EMBEDDING_ONLY);
            assertThat(c.similarity()).isEqualTo(0.22);
            assertThat(c.gdeltLift()).isNull();
        });
    }

    @Test
    void 검증_우선순위대로_정렬된다_BOTH_먼저_그다음_GDELT_그다음_임베딩() {
        Map<String, Double> embedding = new LinkedHashMap<>();
        embedding.put("NEE", 0.31);   // BOTH
        embedding.put("INTC", 0.25);  // EMBEDDING_ONLY
        embedding.put("MNST", 0.20);  // EMBEDDING_ONLY

        Map<String, Double> gdelt = new LinkedHashMap<>();
        gdelt.put("NEE", 10.5);   // BOTH
        gdelt.put("GNRC", 9.3);   // GDELT_ONLY
        gdelt.put("DUK", 8.4);    // GDELT_ONLY

        List<StockCandidate> out = CandidateTiering.combine(embedding, gdelt);

        assertThat(out).extracting(StockCandidate::ticker, StockCandidate::tier)
                .containsExactly(
                        tuple("NEE", CandidateTier.BOTH),
                        tuple("GNRC", CandidateTier.GDELT_ONLY),  // lift 9.3 > 8.4
                        tuple("DUK", CandidateTier.GDELT_ONLY),
                        tuple("INTC", CandidateTier.EMBEDDING_ONLY),  // sim 0.25 > 0.20
                        tuple("MNST", CandidateTier.EMBEDDING_ONLY));
    }

    @Test
    void 빈_입력이면_빈_목록() {
        assertThat(CandidateTiering.combine(Map.of(), Map.of())).isEmpty();
    }
}
