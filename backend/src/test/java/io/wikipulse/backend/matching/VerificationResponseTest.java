package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

/**
 * 응답 스키마 검증 (WP-68). POC {@code verify_experiment.validate} 규칙(-45)을 그대로
 * 옮긴 {@link VerificationResponse#fromJson} 를 오프라인(GATEWAY 불필요)으로 확인한다.
 */
class VerificationResponseTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private VerificationResponse parse(String json) throws Exception {
        return VerificationResponse.fromJson(mapper.readTree(json));
    }

    @Test
    void verified_true_는_네_필드가_모두_채워져야_통과한다() throws Exception {
        VerificationResponse r = parse("""
                {"issue_class":"SECTOR_OR_REGION_EVENT","verified":true,
                 "match_path":"REGION","confidence":"strong",
                 "rationale_en":"Florida utility.","rationale_ko":"플로리다 전력사."}
                """);
        assertThat(r.verified()).isTrue();
        assertThat(r.matchPath()).isEqualTo("REGION");
        assertThat(r.confidence()).isEqualTo("strong");
        assertThat(r.rationaleKo()).isEqualTo("플로리다 전력사.");
        assertThat(r.issueClass()).isEqualTo("SECTOR_OR_REGION_EVENT");
    }

    @Test
    void verified_false_는_나머지가_전부_null_이어야_통과한다() throws Exception {
        VerificationResponse r = parse("""
                {"issue_class":"SINGLE_COMPANY_EVENT","verified":false,
                 "match_path":null,"confidence":null,"rationale_en":null,"rationale_ko":null}
                """);
        assertThat(r.verified()).isFalse();
        assertThat(r.matchPath()).isNull();
        assertThat(r.rationaleKo()).isNull();
    }

    @Test
    void verified_false_인데_필드가_null_아니면_위반() {
        assertThatThrownBy(() -> parse("""
                {"issue_class":"SINGLE_COMPANY_EVENT","verified":false,
                 "match_path":"REGION","confidence":null,"rationale_en":null,"rationale_ko":null}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("null 아님");
    }

    @Test
    void issue_class_enum_밖이면_위반() {
        assertThatThrownBy(() -> parse("""
                {"issue_class":"OTHER","verified":false,
                 "match_path":null,"confidence":null,"rationale_en":null,"rationale_ko":null}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("issue_class");
    }

    @Test
    void match_path_enum_밖이면_위반() {
        assertThatThrownBy(() -> parse("""
                {"issue_class":"SECTOR_OR_REGION_EVENT","verified":true,
                 "match_path":"COMPETITOR","confidence":"weak",
                 "rationale_en":"x","rationale_ko":"y"}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("match_path");
    }

    @Test
    void 키가_빠지면_위반() {
        assertThatThrownBy(() -> parse("""
                {"issue_class":"SECTOR_OR_REGION_EVENT","verified":true,
                 "match_path":"REGION","confidence":"strong","rationale_en":"x"}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("키 불일치");
    }

    @Test
    void verified_true_인데_rationale_가_비면_위반() {
        assertThatThrownBy(() -> parse("""
                {"issue_class":"SECTOR_OR_REGION_EVENT","verified":true,
                 "match_path":"REGION","confidence":"strong",
                 "rationale_en":"x","rationale_ko":"  "}
                """))
                .isInstanceOf(SchemaViolationException.class)
                .hasMessageContaining("rationale_ko");
    }
}
