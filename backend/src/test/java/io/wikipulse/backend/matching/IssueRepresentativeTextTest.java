package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;

import io.wikipulse.backend.matching.IssueRepresentativeText.Member;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * 이슈 대표 텍스트 규칙 (명세 §6.2). {@code ai/issue-text-poc} 변형 D 와 같은 결과여야 한다.
 */
class IssueRepresentativeTextTest {

    @Test
    void 문서_수로_문장_수가_정해진다() {
        assertThat(IssueRepresentativeText.sentencesPerDoc(1)).isEqualTo(6);
        assertThat(IssueRepresentativeText.sentencesPerDoc(2)).isEqualTo(4);
        assertThat(IssueRepresentativeText.sentencesPerDoc(3)).isEqualTo(4);
        assertThat(IssueRepresentativeText.sentencesPerDoc(4)).isEqualTo(2);
        assertThat(IssueRepresentativeText.sentencesPerDoc(10)).isEqualTo(2);
    }

    @Test
    void 앞_n문장만_자르고_마침표를_하나로_맞춘다() {
        String text = "First one. Second two. Third three. Fourth four.";
        assertThat(IssueRepresentativeText.firstSentences(text, 2)).isEqualTo("First one. Second two.");
    }

    @Test
    void 문장이_n보다_적으면_있는_만큼만() {
        assertThat(IssueRepresentativeText.firstSentences("Only one sentence.", 6))
                .isEqualTo("Only one sentence.");
    }

    @Test
    void 마침표_없는_한_덩이도_한_문장으로() {
        assertThat(IssueRepresentativeText.firstSentences("No trailing period here", 2))
                .isEqualTo("No trailing period here.");
    }

    @Test
    void 개행은_공백으로_바꾼다() {
        assertThat(IssueRepresentativeText.firstSentences("Line one.\nLine two.", 2))
                .isEqualTo("Line one. Line two.");
    }

    @Test
    void 빈_도입부는_빈_문자열() {
        assertThat(IssueRepresentativeText.firstSentences("", 2)).isEmpty();
        assertThat(IssueRepresentativeText.firstSentences("   ", 2)).isEmpty();
        assertThat(IssueRepresentativeText.firstSentences(null, 2)).isEmpty();
    }

    @Test
    void 단일_문서는_제목과_도입부_6문장을_한_줄로() {
        String text = IssueRepresentativeText.build(
                List.of(new Member("Nvidia", "S1. S2. S3. S4. S5. S6. S7. S8.")), 2000);
        assertThat(text).isEqualTo("Nvidia: S1. S2. S3. S4. S5. S6.");
    }

    @Test
    void 여러_문서는_제목_도입부를_줄바꿈으로_잇는다() {
        String text = IssueRepresentativeText.build(List.of(
                new Member("Hurricane Milton", "A big storm. It hit Florida. Power went out."),
                new Member("Florida", "A US state. It has coastlines. It gets hurricanes.")), 2000);
        // 2개 문서 → per-doc 4, 각 도입부는 3문장뿐이라 다 담긴다
        assertThat(text).isEqualTo(
                "Hurricane Milton: A big storm. It hit Florida. Power went out.\n"
                        + "Florida: A US state. It has coastlines. It gets hurricanes.");
    }

    @Test
    void 도입부가_빈_문서는_줄에서_빼되_문서_수에는_센다() {
        // 4개 문서 → per-doc 2. 빈 도입부 하나는 줄에서 빠져 3줄이 된다.
        String text = IssueRepresentativeText.build(List.of(
                new Member("A", "A1. A2. A3."),
                new Member("B", ""),
                new Member("C", "C1. C2. C3."),
                new Member("D", "D1. D2. D3.")), 2000);
        assertThat(text).isEqualTo("A: A1. A2.\nC: C1. C2.\nD: D1. D2.");
    }

    @Test
    void 상한을_넘으면_뒤를_자른다() {
        // 단일 문서 → 6문장 선택 후 "T: word. word. word. word. word. word." = 38자.
        // 상한 20 을 넘으므로 20자로 잘린다.
        String longIntro = "word. ".repeat(200);
        String text = IssueRepresentativeText.build(List.of(new Member("T", longIntro)), 20);
        assertThat(text).hasSize(20).isEqualTo("T: word. word. word.");
    }

    @Test
    void 멤버가_없거나_전부_비면_빈_문자열() {
        assertThat(IssueRepresentativeText.build(List.of(), 2000)).isEmpty();
        assertThat(IssueRepresentativeText.build(
                List.of(new Member("A", ""), new Member("B", "   ")), 2000)).isEmpty();
    }
}
