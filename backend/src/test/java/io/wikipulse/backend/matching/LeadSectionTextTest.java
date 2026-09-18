package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * 리드 섹션 HTML → 평문 (WP-129).
 *
 * <p>과거 도입부는 {@code action=parse&oldid=&section=0} 의 HTML 로만 얻을 수 있어
 * ({@code prop=extracts} 는 revids 를 줘도 현재 도입부를 준다) 평문화를 우리가 한다.
 * LIVE 경로의 {@code explaintext} 결과와 같은 모양이어야 대표 텍스트 규칙(§6.2)이 두 경로에서
 * 같게 돈다.
 */
class LeadSectionTextTest {

    @Test
    void 문단_텍스트만_남긴다() {
        String html = "<div class=\"mw-parser-output\"><p>Joe Biden is a politician.</p></div>";
        assertThat(LeadSectionText.fromHtml(html)).isEqualTo("Joe Biden is a politician.");
    }

    @Test
    void infobox_표는_버린다() {
        // 표를 남기면 문서마다 같은 필드명(Born·Died·Operator)이 반복돼 임베딩이 그쪽으로 끌린다.
        String html = "<table class=\"infobox\"><tr><td>Born</td><td>1942</td></tr></table>"
                + "<p>He served as vice president.</p>";
        assertThat(LeadSectionText.fromHtml(html)).isEqualTo("He served as vice president.");
    }

    @Test
    void 각주_번호와_스타일은_버린다() {
        String html = "<style>.mw-ref{}</style><p>The flight crashed<sup class=\"reference\">[1]</sup>"
                + " after takeoff.</p>";
        assertThat(LeadSectionText.fromHtml(html)).isEqualTo("The flight crashed after takeoff.");
    }

    @Test
    void 문단_밖의_hatnote는_안_들어간다() {
        String html = "<div role=\"note\" class=\"hatnote\">Not to be confused with X.</div>"
                + "<p>Real lead sentence.</p>";
        assertThat(LeadSectionText.fromHtml(html)).isEqualTo("Real lead sentence.");
    }

    @Test
    void 여러_문단은_개행으로_잇는다() {
        // IssueRepresentativeText.firstSentences 가 개행을 공백으로 바꾸므로 LIVE 평문과 같은 취급이 된다.
        String html = "<p>First para.</p><p>Second para.</p>";
        assertThat(LeadSectionText.fromHtml(html)).isEqualTo("First para.\nSecond para.");
        assertThat(IssueRepresentativeText.firstSentences(LeadSectionText.fromHtml(html), 2))
                .isEqualTo("First para. Second para.");
    }

    @Test
    void 엔티티를_되돌린다() {
        String html = "<p>Tom &amp; Jerry said &quot;hi&quot;&nbsp;today.</p>";
        assertThat(LeadSectionText.fromHtml(html)).isEqualTo("Tom & Jerry said \"hi\" today.");
    }

    @Test
    void 이중_이스케이프는_한_번만_푼다() {
        // &amp;lt; 는 문서에 그대로 "&lt;" 라고 쓰인 것이다 — "<" 로 바꾸면 원문이 훼손된다.
        assertThat(LeadSectionText.fromHtml("<p>a &amp;lt; b</p>")).isEqualTo("a &lt; b");
    }

    @Test
    void 문단이_없으면_빈_문자열() {
        assertThat(LeadSectionText.fromHtml("<table><tr><td>only a table</td></tr></table>")).isEmpty();
        assertThat(LeadSectionText.fromHtml("")).isEmpty();
        assertThat(LeadSectionText.fromHtml(null)).isEmpty();
    }
}
