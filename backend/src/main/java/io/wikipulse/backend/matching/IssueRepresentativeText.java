package io.wikipulse.backend.matching;

import java.util.ArrayList;
import java.util.List;

/**
 * 클러스터(문서 여러 개)를 임베딩 입력 한 덩이로 바꾸는 규칙 (명세 §6.2, 확정 2026-09-08).
 *
 * <pre>
 * {문서 제목}: {도입부 앞 N문장}
 * {문서 제목}: {도입부 앞 N문장}
 * ...
 * </pre>
 *
 * <ul>
 *   <li>N = 클러스터 문서 1개면 6, 2~3개면 4, 4개 이상이면 2 (변형 D). 전체 상한 2,000자
 *   <li>문서 순서는 급등도 내림차순 — 호출자가 정렬해 넘긴다(cluster_member.spike_score)
 *   <li>🔴 텍스트는 영어로 유지한다. 한국어로 만들면 종목 설명(영어)과 언어 불일치만으로
 *       코사인이 절반이 된다(정답 평균 0.160 → 0.081, 명세 §11)
 * </ul>
 *
 * <p>도입부가 빈 문서는 줄에서 뺀다 — "제목: ." 같은 노이즈를 임베딩에 넣지 않는다.
 * 단, N 은 클러스터 전체 문서 수로 정한다(명세 문구 그대로) — 빈 도입부도 문서 수에는 센다.
 * 순수 함수다. 네트워크·DB 를 모른다 — 그래서 단위 테스트가 쉽다.
 * 근거: {@code ai/issue-text-poc/} (변형 D), RESULT.md.
 */
public final class IssueRepresentativeText {

    private IssueRepresentativeText() {
    }

    /** 제목과 그 도입부 평문 한 쌍. 도입부는 Wikipedia extracts 원문(리다이렉트 추적 후). */
    public record Member(String title, String intro) {
    }

    /**
     * 대표 텍스트를 만든다. 급등도 내림차순으로 정렬된 멤버를 받는다.
     *
     * @param members  급등도 내림차순 멤버. 도입부가 비어도 무방(줄에서 빠진다)
     * @param maxChars 전체 상한. 넘으면 뒤를 자른다
     * @return 대표 텍스트. 유효한 도입부가 하나도 없으면 빈 문자열
     */
    public static String build(List<Member> members, int maxChars) {
        if (members == null || members.isEmpty()) {
            return "";
        }
        int perDoc = sentencesPerDoc(members.size());
        List<String> lines = new ArrayList<>();
        for (Member m : members) {
            String sentences = firstSentences(m.intro(), perDoc);
            if (sentences.isEmpty()) {
                continue;
            }
            lines.add(m.title() + ": " + sentences);
        }
        String text = String.join("\n", lines);
        if (maxChars > 0 && text.length() > maxChars) {
            text = text.substring(0, maxChars);
        }
        return text;
    }

    /** N 규칙: 문서 1개면 6, 2~3개면 4, 4개 이상이면 2 (명세 §6.2). */
    public static int sentencesPerDoc(int documentCount) {
        if (documentCount <= 1) {
            return 6;
        }
        return documentCount <= 3 ? 4 : 2;
    }

    /**
     * 도입부 앞 n문장. {@code ai/issue-text-poc} 의 {@code first_sentences} 를 그대로 옮긴다:
     * 개행을 공백으로 바꾸고 ". " 로 쪼갠 뒤 앞 n조각을 ". " 로 잇고, 끝 마침표를 정리해 하나만 붙인다.
     */
    public static String firstSentences(String text, int n) {
        if (text == null || n <= 0) {
            return "";
        }
        String flat = text.replace('\n', ' ').strip();
        if (flat.isEmpty()) {
            return "";
        }
        String[] parts = flat.split("\\. ");
        int take = Math.min(n, parts.length);
        List<String> picked = new ArrayList<>(take);
        for (int i = 0; i < take; i++) {
            picked.add(parts[i]);
        }
        String joined = String.join(". ", picked).strip();
        joined = joined.replaceAll("\\.+$", "");
        return joined.isEmpty() ? "" : joined + ".";
    }
}
