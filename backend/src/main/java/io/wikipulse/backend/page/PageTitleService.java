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

    public PageTitleService(PageTitleRepository repository, WikipediaExtractClient wikipedia) {
        this.repository = repository;
        this.wikipedia = wikipedia;
    }

    /**
     * 처리 결과. {@code checked} 는 조회를 마친 문서 수, {@code resolved} 는 그중 ko 를 찾은 수다.
     * 둘의 차이가 "한국어 문서가 없어 영문으로 표시될 문서" 이며, 그건 결함이 아니라 정상이다.
     */
    public record Result(int checked, int resolved) {

        static final Result NOTHING = new Result(0, 0);
    }

    /**
     * 미조회 문서를 최대 {@code limit} 건 채운다.
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
