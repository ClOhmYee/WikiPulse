package io.wikipulse.backend.matching;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 리드 섹션 HTML → 평문 (WP-129).
 *
 * <p>과거 시점 도입부는 {@code action=parse&oldid=&section=0&prop=text} 로만 얻을 수 있어
 * HTML 이 온다. LIVE 경로가 쓰는 {@code prop=extracts&explaintext} 처럼 평문을 주는 API 가
 * 과거 revision 에는 없다.
 *
 * <p>🔴 <b>{@code prop=extracts} 에 {@code revids} 를 줘도 과거 도입부가 안 온다</b>
 * (2026-09-18 실측). 2015년 revision id 로 물었는데 "46th president of the United States from
 * 2021 to 2025" 로 시작하는 <b>현재</b> 도입부가 200 으로 돌아왔다. 오류가 아니라 그럴듯한
 * 문단이라 결과만 봐서는 시점이 섞인 걸 알 수 없다 — 그래서 이 경로를 따로 만들었다.
 *
 * <p>순수 함수다. 네트워크를 모른다.
 *
 * <h2>무엇을 버리는가</h2>
 * <ul>
 *   <li>{@code <table>} — infobox·navbox. 본문이 아니라 속성 나열이라 임베딩 입력에 넣으면
 *       문서마다 같은 필드명이 반복돼 유사도가 그쪽으로 끌린다
 *   <li>{@code <style>}·{@code <figure>}·{@code <sup>} — CSS 원문, 캡션, 각주 번호([1])
 *   <li>{@code <p>} 밖의 것 — hatnote({@code <div role="note">})·좌표·경고 상자
 * </ul>
 * 남은 {@code <p>} 안의 태그는 걷어내고 엔티티만 되돌린다.
 */
public final class LeadSectionText {

    private LeadSectionText() {
    }

    private static final Pattern DROP_BLOCKS =
            Pattern.compile("(?is)<(table|style|figure|sup)\\b[^>]*>.*?</\\1>");
    private static final Pattern PARAGRAPH = Pattern.compile("(?is)<p\\b[^>]*>(.*?)</p>");
    private static final Pattern TAG = Pattern.compile("(?s)<[^>]+>");
    private static final Pattern SPACES = Pattern.compile("\\s+");

    /**
     * 리드 섹션 HTML 에서 문단 평문을 뽑는다. 문단이 하나도 없으면 빈 문자열.
     *
     * <p>문단은 개행으로 잇는다 — {@link IssueRepresentativeText#firstSentences} 가 개행을
     * 공백으로 바꾸고 ". " 로 쪼개므로 LIVE 평문과 같은 취급을 받는다.
     */
    public static String fromHtml(String html) {
        if (html == null || html.isBlank()) {
            return "";
        }
        String cleaned = DROP_BLOCKS.matcher(html).replaceAll(" ");
        List<String> paragraphs = new java.util.ArrayList<>();
        Matcher m = PARAGRAPH.matcher(cleaned);
        while (m.find()) {
            String text = unescape(SPACES.matcher(TAG.matcher(m.group(1)).replaceAll("")).replaceAll(" "))
                    .strip();
            if (!text.isEmpty()) {
                paragraphs.add(text);
            }
        }
        return String.join("\n", paragraphs).strip();
    }

    /**
     * MediaWiki 출력에 실제로 나오는 엔티티만 되돌린다. 전체 HTML 엔티티 표를 들일 만큼
     * 종류가 많지 않고, 들이면 라이브러리 의존이 하나 늘어난다.
     *
     * <p>{@code &amp;} 를 마지막에 푸는 건 {@code &amp;lt;} 가 {@code <} 로 바뀌지 않게 하려는 것이다.
     */
    private static String unescape(String text) {
        return text.replace("&nbsp;", " ")
                .replace("&quot;", "\"")
                .replace("&#039;", "'")
                .replace("&#39;", "'")
                .replace("&apos;", "'")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&amp;", "&");
    }
}
