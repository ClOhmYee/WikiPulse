package io.wikipulse.backend.page;

import io.wikipulse.backend.matching.WikipediaExtractClient;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 클러스터에 편입된 문서의 ko.wikipedia 대응 제목을 1회 조회해 {@code wiki_page.title_ko} 에 채운다.
 *
 * <p>🔴 <b>표시명만 바꾼다.</b> {@code wiki_page.title}(영문)은 (wiki, title) 자연키이자
 * Wikipedia 링크·Clickstream 조인·클러스터링 키다 — 이 서비스는 그 컬럼을 읽기만 한다.
 *
 * <p><b>한 폴의 흐름</b>
 * <ol>
 *   <li>아직 조회 안 한 문서를 {@code batchSize} 만큼 집는다(LIVE·replay 구분 없음).</li>
 *   <li>{@value WikipediaExtractClient#TITLES_PER_REQUEST} 개씩 쪼개 langlinks 를 부른다 —
 *       🔴 51개부터는 잘림이 아니라 {@code toomanyvalues} 에러라 결과가 통째로 0이 된다
 *       (2026-09-22 실측).</li>
 *   <li>응답을 받은 청크는 <b>ko 를 못 찾은 문서까지</b> 기록한다(음성 캐시).</li>
 * </ol>
 *
 * <p>⚠️ 전송 실패({@link io.wikipulse.backend.matching.UpstreamUnavailableException})는 잡지 않고
 * 전파한다. 여기서 삼켜 "ko 없음"으로 기록하면 위키 일시 장애 구간을 지나간 문서가 영구히
 * 영문으로 굳는다 — 에러 없이 조용히 틀리는 쪽이다. 이미 성공한 앞 청크는 커밋된 채 남고
 * 나머지는 다음 폴이 이어받는다({@code @Transactional} 을 걸지 않는 이유 — 매칭 워커들과 같은 관습).
 */
@Service
public class PageTitleService {

    private static final Logger log = LoggerFactory.getLogger(PageTitleService.class);

    private final PageTitleRepository repository;
    private final WikipediaExtractClient wikipedia;
    private final AzureTranslatorClient translator;
    private final PageTitleProperties props;

    public PageTitleService(PageTitleRepository repository, WikipediaExtractClient wikipedia,
                            AzureTranslatorClient translator, PageTitleProperties props) {
        this.repository = repository;
        this.wikipedia = wikipedia;
        this.translator = translator;
        this.props = props;
    }

    /**
     * 처리 결과. {@code checked} 는 조회를 마친 문서 수, {@code resolved} 는 그중 ko 를 찾은 수다.
     * 둘의 차이가 "한국어 문서가 없어 영문으로 표시될 문서" 이며, 그건 결함이 아니라 정상이다.
     */
    public record Result(int checked, int resolved) {

        static final Result NOTHING = new Result(0, 0);
    }

    /** 번역 단계 결과. {@code attempted} 는 번역을 시도해 기록까지 끝낸 수. */
    public record TranslationResult(int attempted, int translated) {

        static final TranslationResult NOTHING = new TranslationResult(0, 0);
    }

    /**
     * 한 폴 전체 — 1단 langlinks, 2단 Azure 번역.
     *
     * <p>🔴 <b>두 단계를 따로 감싼다.</b> Azure 가 죽었다고 langlinks 까지 멈추면 1단 폴백마저
     * 못 채운다. 번역 실패는 여기서 잡아 로그만 남기고, 위키 실패는 그대로 전파해 워커가
     * 다음 폴에 재시도하게 한다.
     */
    public Result enrichAll(int limit) {
        Result wiki = enrich(limit);
        try {
            translateMissing(props.getAzure().getBatchSize());
        } catch (RuntimeException e) {
            // 🔴 삼키는 것은 "이번 폴의 번역"뿐이다. 기록을 안 했으므로 대상은 그대로 남아
            //    다음 폴에서 다시 집힌다. langlinks 결과는 이미 커밋돼 있다.
            log.warn("Azure 번역 단계 실패 — langlinks 결과는 유지하고 다음 폴에서 재시도한다: {}",
                    e.toString());
        }
        return wiki;
    }

    /**
     * ko.wikipedia 대응이 없는 문서를 기계 번역해 2단 폴백을 채운다.
     *
     * <p>🔴 <b>langlinks 를 끝낸 문서만</b> 대상이다(질의 조건). 정식 제목이 있을 수 있는 문서를
     * 먼저 번역해 버리면 쿼터를 낭비하고, 나중에 정식 제목이 와도 이미 번역이 붙어 있다.
     *
     * @throws io.wikipulse.backend.matching.UpstreamUnavailableException Azure 전송 실패 —
     *         그 청크는 기록하지 않고 다음 폴에서 다시 집힌다
     */
    public TranslationResult translateMissing(int limit) {
        if (!translator.isConfigured()) {
            // 키가 없으면 조용히 건너뛴다 — 기능이 깨지는 게 아니라 영문으로 표시될 뿐이다.
            log.debug("Azure 키 미설정 — 번역 단계 건너뜀 (영문 표시 유지)");
            return TranslationResult.NOTHING;
        }
        List<PageTitleRepository.PendingPage> pending = repository.findTranslatePending(limit);
        if (pending.isEmpty()) {
            return TranslationResult.NOTHING;
        }

        int attempted = 0;
        int translated = 0;
        for (List<PageTitleRepository.PendingPage> chunk : chunked(pending)) {
            Map<String, String> byTitle =
                    translator.translate(chunk.stream().map(PageTitleRepository.PendingPage::title).toList());

            // 🔴 번역이 안 나온 문서도 담는다 — null 이면 "번역했고 결과 없음"(음성 캐시)이다.
            Map<Long, String> updates = new LinkedHashMap<>();
            for (PageTitleRepository.PendingPage page : chunk) {
                updates.put(page.id(), byTitle.get(page.title()));
            }
            repository.recordTranslations(updates);

            attempted += chunk.size();
            translated += byTitle.size();
        }

        log.info("Azure 번역 {}건 중 {}건 확보 (나머지는 영문 표시)", attempted, translated);
        return new TranslationResult(attempted, translated);
    }

    private static List<List<PageTitleRepository.PendingPage>> chunked(
            List<PageTitleRepository.PendingPage> pages) {
        List<List<PageTitleRepository.PendingPage>> chunks = new java.util.ArrayList<>();
        int size = AzureTranslatorClient.TEXTS_PER_REQUEST;
        for (int from = 0; from < pages.size(); from += size) {
            chunks.add(pages.subList(from, Math.min(from + size, pages.size())));
        }
        return chunks;
    }

    /**
     * 미조회 문서를 최대 {@code limit} 건 채운다 (1단 langlinks 전용).
     *
     * @throws io.wikipulse.backend.matching.UpstreamUnavailableException 위키 전송 실패 —
     *         그 청크는 기록하지 않고 다음 폴에서 다시 집힌다
     */
    public Result enrich(int limit) {
        List<PageTitleRepository.PendingPage> pending = repository.findPending(limit);
        if (pending.isEmpty()) {
            return Result.NOTHING;
        }

        int checked = 0;
        int resolved = 0;
        for (int from = 0; from < pending.size(); from += WikipediaExtractClient.TITLES_PER_REQUEST) {
            List<PageTitleRepository.PendingPage> chunk = pending.subList(
                    from, Math.min(from + WikipediaExtractClient.TITLES_PER_REQUEST, pending.size()));

            // 같은 제목이 두 id 로 존재할 수는 없지만(자연키 UNIQUE), 질의는 제목 목록이라
            // 순서를 유지한 채 그대로 넘긴다.
            Map<String, String> koByTitle =
                    wikipedia.koTitles(chunk.stream().map(PageTitleRepository.PendingPage::title).toList());

            // 🔴 ko 를 못 찾은 문서도 담는다 — 값이 null 이면 "조회했고 없음" 으로 기록된다.
            //    Map.of 는 null 값을 못 담아 LinkedHashMap 을 쓴다.
            Map<Long, String> updates = new LinkedHashMap<>();
            for (PageTitleRepository.PendingPage page : chunk) {
                updates.put(page.id(), koByTitle.get(page.title()));
            }
            repository.record(updates);

            checked += chunk.size();
            resolved += koByTitle.size();
        }

        log.info("ko 제목 조회 {}건 중 {}건 확보 (나머지는 한국어 문서 없음 — 영문 표시)",
                checked, resolved);
        return new Result(checked, resolved);
    }
}
