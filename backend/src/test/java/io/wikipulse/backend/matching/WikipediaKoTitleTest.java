package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.entry;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/**
 * {@code prop=langlinks&lllang=ko} 응답 해석 (표시용 한국어 제목, V20).
 *
 * <p>여기 JSON 은 2026-09-22 에 실제 {@code en.wikipedia.org/w/api.php} 응답에서 뜬 모양 그대로다
 * ({@code formatversion=2} — {@code query.pages} 가 배열).
 */
class WikipediaKoTitleTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static JsonNode json(String raw) {
        try {
            return MAPPER.readTree(raw);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    @Test
    void ko_대응이_있으면_영문제목으로_매핑된다() {
        JsonNode root = json("""
                {"batchcomplete":true,"query":{"pages":[
                  {"pageid":29005,"ns":0,"title":"Strait of Hormuz",
                   "langlinks":[{"lang":"ko","title":"호르무즈 해협"}]},
                  {"pageid":78046814,"ns":0,"title":"Hurricane Milton",
                   "langlinks":[{"lang":"ko","title":"허리케인 밀턴"}]}]}}
                """);

        assertThat(WikipediaExtractClient.parseKoTitles(
                root, List.of("Strait of Hormuz", "Hurricane Milton")))
                .containsExactly(
                        entry("Strait of Hormuz", "호르무즈 해협"),
                        entry("Hurricane Milton", "허리케인 밀턴"));
    }

    @Test
    void ko_문서가_없으면_키_자체가_없다() {
        // 실측: Duke Energy·Generac·Florida Power & Light 처럼 ko 판이 없는 중형 기업이 흔하다.
        // 후보 200건 무작위 표본에서 ko 있음은 49.5% 였다 — 미스가 정상 경로다.
        JsonNode root = json("""
                {"query":{"pages":[{"pageid":1,"ns":0,"title":"Duke Energy"}]}}
                """);

        assertThat(WikipediaExtractClient.parseKoTitles(root, List.of("Duke Energy"))).isEmpty();
    }

    @Test
    void 없는_문서는_미스다() {
        JsonNode root = json("""
                {"query":{"pages":[{"ns":0,"title":"Nonexistent Page Zzzq","missing":true}]}}
                """);

        assertThat(WikipediaExtractClient.parseKoTitles(root, List.of("Nonexistent Page Zzzq")))
                .isEmpty();
    }

    /**
     * 🔴 이 변경에서 조용히 틀릴 수 있는 유일한 자리다.
     *
     * <p>{@code redirects=1} 을 주면 응답의 {@code pages[].title} 이 <b>목적지</b>가 된다.
     * 2026-09-22 실측:
     * <pre>
     *   Effects of Hurricane Milton in Florida        → Hurricane Milton  ("허리케인 밀턴")
     *   2025 Iran threat of Strait of Hormuz closure  → Twelve-Day War    ("12일 전쟁")
     * </pre>
     * 그대로 저장하면 A 문서에 B 문서의 한국어 이름이 붙고, 값이 그럴듯해서 화면만 봐서는
     * 틀린 줄 모른다.
     *
     * <p>파라미터를 빼면 리다이렉트 문서는 langlinks 없이 돌아온다 — 아래 JSON 이 그 응답이다.
     * MVP 는 미스로 두고 영문으로 떨어진다.
     */
    @Test
    void 리다이렉트_문서는_붙이지_않고_미스로_둔다() {
        JsonNode root = json("""
                {"query":{"pages":[
                  {"pageid":2,"ns":0,"title":"Effects of Hurricane Milton in Florida"},
                  {"pageid":3,"ns":0,"title":"2025 Iran threat of Strait of Hormuz closure"}]}}
                """);

        assertThat(WikipediaExtractClient.parseKoTitles(root, List.of(
                "Effects of Hurricane Milton in Florida",
                "2025 Iran threat of Strait of Hormuz closure"))).isEmpty();
    }

    @Test
    void 목적지_제목이_섞여_와도_보낸_제목에만_매핑한다() {
        // 방어선. 누가 redirects=1 을 되살려도 보낸 적 없는 제목은 결과에 안 들어간다.
        JsonNode root = json("""
                {"query":{"redirects":[{"from":"Effects of Hurricane Milton in Florida",
                                        "to":"Hurricane Milton"}],
                          "pages":[{"pageid":78046814,"ns":0,"title":"Hurricane Milton",
                                    "langlinks":[{"lang":"ko","title":"허리케인 밀턴"}]}]}}
                """);

        assertThat(WikipediaExtractClient.parseKoTitles(
                root, List.of("Effects of Hurricane Milton in Florida"))).isEmpty();
    }

    @Test
    void 정규화는_되짚어_매핑한다() {
        // ⚠️ MediaWiki 는 redirects 와 무관하게 표기 정규화는 한다(Hurricane_Milton → 공백형).
        //    같은 문서를 가리키는 표기 차이라 안전하다 — 리다이렉트와 다르다.
        JsonNode root = json("""
                {"query":{"normalized":[{"fromencoded":false,"from":"Hurricane_Milton",
                                         "to":"Hurricane Milton"}],
                          "pages":[{"pageid":78046814,"ns":0,"title":"Hurricane Milton",
                                    "langlinks":[{"lang":"ko","title":"허리케인 밀턴"}]}]}}
                """);

        assertThat(WikipediaExtractClient.parseKoTitles(root, List.of("Hurricane_Milton")))
                .containsExactly(
                        entry("Hurricane_Milton", "허리케인 밀턴"));
    }

    @Test
    void 빈_ko_제목은_버린다() {
        // 빈 문자열이 저장되면 화면에 빈 제목이 뜬다. DB CHECK 도 막지만 여기서 먼저 끊는다.
        JsonNode root = json("""
                {"query":{"pages":[{"pageid":1,"ns":0,"title":"A",
                                    "langlinks":[{"lang":"ko","title":"  "}]}]}}
                """);

        assertThat(WikipediaExtractClient.parseKoTitles(root, List.of("A"))).isEmpty();
    }

    @Test
    void 응답이_없으면_빈_결과다() {
        assertThat(WikipediaExtractClient.parseKoTitles(null, List.of("A"))).isEmpty();
        assertThat(WikipediaExtractClient.parseKoTitles(json("{}"), List.of("A"))).isEmpty();
    }

    @Test
    void 제목_50개까지만_받는다() {
        // 🔴 51개부터는 잘림이 아니라 toomanyvalues 에러라 결과가 통째로 0이 된다(2026-09-22 실측).
        //    호출 전에 끊어야 한 폴이 통으로 날아가지 않는다.
        List<String> tooMany = IntStream.rangeClosed(0, WikipediaExtractClient.TITLES_PER_REQUEST)
                .mapToObj(i -> "T" + i).toList();

        assertThatThrownBy(() -> new WikipediaExtractClient(new CandidateProperties())
                .koTitles(tooMany))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("50");
    }
}
