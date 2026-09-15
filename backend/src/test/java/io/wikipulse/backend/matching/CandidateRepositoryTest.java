package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * pgvector 리터럴 변환만 순수 검증한다. 네이티브 SQL 자체의 실 DB 검증은 db/ pgserver 몫이다.
 */
class CandidateRepositoryTest {

    @Test
    void float_배열을_pgvector_리터럴로_바꾼다() {
        assertThat(CandidateRepository.toVectorLiteral(new float[] {0.1f, -0.2f, 0.0f}))
                .isEqualTo("[0.1,-0.2,0.0]");
    }

    @Test
    void 빈_배열도_대괄호로_감싼다() {
        assertThat(CandidateRepository.toVectorLiteral(new float[] {})).isEqualTo("[]");
    }
}
