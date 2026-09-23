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

    /**
     * LLM 입력 규칙 버전 (WP-213). 검증·요약 재사용 키에 들어간다.
     *
     * <p>🔴 입력 규칙을 바꾸면 이 값을 올린다. 재사용 키는 프롬프트·모델만 보던 터라 입력만 바뀌면
     * 앞 N문장으로 만든 옛 판정·요약이 <b>조용히 재사용</b>되고, 고친 게 안 고쳐진 것처럼 보인다.
     */
    public static final String LLM_INPUT_VERSION = "lead1";

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

    /**
     * LLM 검증·요약 입력 — 문서마다 <b>도입부 전체</b> (WP-213).
     *
     * <p>{@link #build} 는 앞 N문장만 쓰는데, 위키 도입부는 "정의 → 역사 → 최근 사건" 순서라
     * <b>이슈가 된 사건이 도입부 맨 끝</b>에 붙는다. 2026-07-25 {@code Norfolk Southern Railway}
     * 는 합병 문장이 16조각 중 14번째, {@code The Odyssey (2026 film)} 는 IMAX 가 10번째였다 —
     * 4문장·6문장 모두 잘린다. LLM 은 긴 맥락에서 필요한 문장을 골라 읽으므로 다 준다.
     *
     * <p>🔴 임베딩은 여전히 {@link #build} 다 — 길면 벡터가 흐려진다(명세 §6.2 실측).
     *
     * <p>상한을 넘으면 도입부가 있는 문서끼리 균등하게 나눈다. 한 문서가 제 몫을 넘으면
     * <b>첫 문장 + 도입부 끝</b>을 남긴다({@link #fitLead}) — 앞에서 자르면 사건 문장이 또 잘린다.
     *
     * @param members  급등도 내림차순 멤버. 도입부가 빈 문서는 줄에서 빠진다
     * @param maxChars 전체 상한. 0 이하면 상한 없음
     */
    public static String buildFullLead(List<Member> members, int maxChars) {
        if (members == null || members.isEmpty()) {
            return "";
        }
        List<Member> valid = new ArrayList<>();
        for (Member m : members) {
            String flat = flatten(m.intro());
            if (!flat.isEmpty()) {
                valid.add(new Member(m.title(), flat));
            }
        }
        if (valid.isEmpty()) {
            return "";
        }
        // 줄바꿈 몫을 빼고 나눈다 — 안 빼면 합이 상한을 조금 넘는다.
        int share = maxChars > 0 ? (maxChars - (valid.size() - 1)) / valid.size() : 0;
        List<String> lines = new ArrayList<>(valid.size());
        for (Member m : valid) {
            String prefix = m.title() + ": ";
            String body = maxChars > 0 ? fitLead(m.intro(), share - prefix.length()) : m.intro();
            if (!body.isEmpty()) {
                lines.add(prefix + body);
            }
        }
        return String.join("\n", lines);
    }

    /**
     * 도입부를 {@code budget} 글자 안에 맞춘다. 들어가면 그대로, 넘치면 첫 문장 + " … " + 끝 문장들.
     *
     * <p>첫 문장은 "이 문서가 무엇인가"(정의), 끝 문장들은 "지금 무슨 일인가"(최근 사건)다. 가운데
     * 역사 서술이 가장 버리기 싸다. 첫 문장만으로 넘치면 앞에서 자른다.
     */
    static String fitLead(String lead, int budget) {
        if (budget <= 0) {
            return "";
        }
        if (lead.length() <= budget) {
            return lead;
        }
        String[] parts = lead.split("\\. ");
        String head = parts[0].strip();
        if (!head.endsWith(".")) {
            head = head + ".";
        }
        String gap = " … ";
        if (head.length() + gap.length() >= budget || parts.length < 2) {
            return lead.substring(0, budget);
        }
        int room = budget - head.length() - gap.length();
        List<String> tail = new ArrayList<>();
        int used = 0;
        for (int i = parts.length - 1; i >= 1; i--) {
            String sentence = parts[i].strip();
            if (!sentence.endsWith(".")) {
                sentence = sentence + ".";
            }
            int cost = sentence.length() + (tail.isEmpty() ? 0 : 1);
            if (used + cost > room) {
                break;
            }
            tail.add(0, sentence);
            used += cost;
        }
        if (tail.isEmpty()) {
            // 마지막 문장 하나도 안 들어가면 그 문장의 끝부분이라도 — 사건은 끝에 있다.
            String last = parts[parts.length - 1].strip();
            return head + gap + last.substring(Math.max(0, last.length() - room));
        }
        return head + gap + String.join(" ", tail);
    }

    private static String flatten(String text) {
        return text == null ? "" : text.replace('\n', ' ').strip();
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
