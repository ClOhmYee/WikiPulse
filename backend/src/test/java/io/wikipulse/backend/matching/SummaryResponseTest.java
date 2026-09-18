package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

/**
 * 요약 응답 스키마 검증 (WP-119). {@link SummaryResponse#fromJson} 를 오프라인(GATEWAY 불필요)으로
 * 확인한다 — sufficient_context 게이트가 근거 부족을 구조적으로 잡는지.
 */
class SummaryResponseTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private SummaryResponse parse(String json) throws Exception {
        return SummaryResponse.fromJson(mapper.readTree(json));
    }

    @Test
    void sufficient_true_는_summary_ko_가_채워져야_통과한다() throws Exception {
        SummaryResponse r = parse("""
                {"sufficient_context":true,"summary_ko":"이란과 이스라엘 사이 무력 충돌이 격화됐다."}
                """);
        assertThat(r.sufficientContext()).isTrue();
        assertThat(r.summaryKo()).isEqualTo("이란과 이스라엘 사이 무력 충돌이 격화됐다.");
    }

    @Test
    void sufficient_false_는_summary_ko_가_null_이어야_통과한다() throws Exception {
        SummaryResponse r = parse("""
                {"sufficient_context":false,"summary_ko":null}
                """);
        assertThat(r.sufficientContext()).isFalse();
        assertThat(r.summaryKo()).isNull();
    }

    @Test
    void sufficient_true_인데_summary_ko_가_비면_위반() {
        // 거부 문장을 못 담게 하는 게이트: true 라 주장하면서 빈 요약은 스키마 위반이다.
        assertThatThrownBy(() -> parse("""
                {"sufficient_context":true,"summary_ko":"   "}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("summary_ko");
    }

    @Test
    void sufficient_false_인데_summary_ko_가_null_아니면_위반() {
        // 근거 부족이라면서 요약을 담으면 위반 — false 는 반드시 null 이어야 저장을 건너뛴다.
        assertThatThrownBy(() -> parse("""
                {"sufficient_context":false,"summary_ko":"설명할 수 없습니다."}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("null 아님");
    }

    @Test
    void 키가_빠지면_위반() {
        assertThatThrownBy(() -> parse("""
                {"sufficient_context":true}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("키 불일치");
    }

    @Test
    void 여분_키가_있으면_위반() {
        assertThatThrownBy(() -> parse("""
                {"sufficient_context":true,"summary_ko":"요약","extra":1}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("키 불일치");
    }

    @Test
    void sufficient_context_가_boolean_아니면_위반() {
        assertThatThrownBy(() -> parse("""
                {"sufficient_context":"true","summary_ko":"요약"}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("boolean");
    }

    @Test
    void object_가_아니면_위반() {
        assertThatThrownBy(() -> parse("[1, 2, 3]"))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("object 아님");
    }
}
