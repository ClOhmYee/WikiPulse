package io.wikipulse.backend.page;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.entry;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/**
 * Azure Translator v3 응답 해석.
 *
 * <p>여기 JSON 은 Translator v3 {@code /translate} 의 실제 모양이다 — 요청과 <b>같은 순서</b>의
 * 배열이고 각 항목에 {@code translations[0].text} 가 들어 있다. 제목은 순서로만 짝지어지므로
 * 길이가 어긋나면 통째로 버리는 것이 이 클래스의 핵심 계약이다.
 */
class AzureTranslatorClientTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static JsonNode json(String raw) {
        try {
            return MAPPER.readTree(raw);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    @Test
    void 순서대로_짝지어_매핑한다() {
        // 실제 운영 제목 10건 중 3건 (2026-09-22 측정값 그대로).
        JsonNode root = json("""
                [{"translations":[{"text":"잭슨 다트","to":"ko"}]},
                 {"translations":[{"text":"2026년 코핫 공격","to":"ko"}]},
                 {"translations":[{"text":"마크 우드 (크리켓 선수)","to":"ko"}]}]
                """);

        assertThat(AzureTranslatorClient.parse(root, List.of(
                "Jaxson Dart", "2026 Kohat attack", "Mark Wood (cricketer)")))
                .containsExactly(
                        entry("Jaxson Dart", "잭슨 다트"),
                        entry("2026 Kohat attack", "2026년 코핫 공격"),
                        entry("Mark Wood (cricketer)", "마크 우드 (크리켓 선수)"));
    }

    @Test
    void 응답_길이가_다르면_통째로_버린다() {
        // 🔴 여기서 일부만 취하면 어느 항목이 밀렸는지 모른 채 A 제목에 B 번역이 붙는다.
        //    번역문은 그럴듯해서 화면만 봐서는 틀린 줄 모른다 — 조용히 틀리는 쪽이다.
        JsonNode root = json("""
                [{"translations":[{"text":"잭슨 다트","to":"ko"}]}]
                """);

        assertThat(AzureTranslatorClient.parse(root, List.of("Jaxson Dart", "Rishikanth")))
                .isEmpty();
    }

    @Test
    void 빈_번역은_버린다() {
        JsonNode root = json("""
                [{"translations":[{"text":"  ","to":"ko"}]},
                 {"translations":[{"text":"콘스탄틴 폴레자예프","to":"ko"}]}]
                """);

        assertThat(AzureTranslatorClient.parse(root, List.of("A", "Konstantin Polezhayev")))
                .containsExactly(entry("Konstantin Polezhayev", "콘스탄틴 폴레자예프"));
    }

    @Test
    void 배열이_아니거나_비면_빈_결과다() {
        // Azure 가 오류를 객체로 돌려주는 경우 — 파싱에서 조용히 끊는다.
        assertThat(AzureTranslatorClient.parse(json("{\"error\":{\"code\":401000}}"), List.of("A")))
                .isEmpty();
        assertThat(AzureTranslatorClient.parse(null, List.of("A"))).isEmpty();
    }

    @Test
    void 키가_없으면_설정되지_않은_것으로_본다() {
        PageTitleProperties props = new PageTitleProperties();
        AzureTranslatorClient client = new AzureTranslatorClient(props);

        assertThat(client.isConfigured()).isFalse();
        // 설정 전에는 호출해도 빈 결과 — 예외가 아니다. 화면은 영문으로 떨어질 뿐이다.
        assertThat(client.translate(List.of("Jaxson Dart"))).isEmpty();
    }

    @Test
    void 제목_50개까지만_받는다() {
        PageTitleProperties props = new PageTitleProperties();
        props.getAzure().setKey("dummy-not-a-real-key");
        List<String> tooMany = IntStream.rangeClosed(0, AzureTranslatorClient.TEXTS_PER_REQUEST)
                .mapToObj(i -> "T" + i).toList();

        assertThatThrownBy(() -> new AzureTranslatorClient(props).translate(tooMany))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("50");
    }

    @Test
    void 청크는_상한_단위로_쪼갠다() {
        List<String> titles = IntStream.rangeClosed(1, 120).mapToObj(i -> "T" + i).toList();

        assertThat(AzureTranslatorClient.chunk(titles).stream().map(List::size))
                .containsExactly(50, 50, 20);
    }
}
