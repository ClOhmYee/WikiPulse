package io.wikipulse.backend.page;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.stereotype.Repository;

/**
 * 표시용 한국어 제목(`wiki_page.title_ko`)의 DB 접근 (V15).
 *
 * <p>백엔드는 스키마를 소유하지 않는다. 이 SQL 의 실 DB 검증은 {@code db/tests/test_schema_v15.py}
 * 몫이다({@code IssueSummaryRepository} 와 같은 관습).
 */
@Repository
public class PageTitleRepository {

    /**
     * 조회 대상 위키. langlinks 는 {@code en.wikipedia.org} 에 물어보므로 enwiki 만 의미가 있다
     * ({@code CandidateProperties.Wikipedia.apiUrl}).
     */
    static final String WIKI = "enwiki";

    /**
     * 아직 조회하지 않은 문서.
     *
     * <p>🔴 <b>{@code wiki_page} 전수가 아니라 {@code cluster_member} 에서 출발한다.</b>
     * {@code wiki_page} 행은 조회수 시간별 덤프 적재가 만들어 수백만 규모다 — 거길 훑으면
     * 화면에 한 번도 안 나올 문서 때문에 위키미디어를 그만큼 때린다. 실제로 화면에 뜨는 것은
     * 클러스터에 편입된 문서뿐이고 그건 스냅샷당 수천 건이다.
     *
     * <p>{@code DISTINCT} 가 필요하다 — 같은 문서가 여러 스냅샷·여러 클러스터의 멤버다.
     * 출처(live/replay)를 가리지 않으므로 같은 enrichment 가 양쪽에 동일하게 걸린다(계약).
     */
    private static final String PENDING_SQL = """
            SELECT DISTINCT p.id AS id, p.title AS title
              FROM cluster_member cm
              JOIN wiki_page p ON p.id = cm.page_id
             WHERE p.wiki = :wiki AND p.title_ko_checked_at IS NULL
             ORDER BY p.id
             LIMIT :limit
            """;

    /**
     * 조회 결과 기록.
     *
     * <p>🔴 ko 가 <b>없어도</b> {@code checked_at} 을 찍는다 — 그게 음성 캐시다. 실측상 ko 대응이
     * 없는 문서가 절반이라(2026-09-22, 후보 200건 중 49.5% 만 있음) 이걸 안 찍으면 매 폴마다
     * 같은 문서를 다시 물어본다.
     *
     * <p>⚠️ 반대로 <b>전송 실패에는 이 UPDATE 를 부르지 않는다.</b> 부르면 위키가 잠깐 죽은
     * 사이 지나간 문서가 "ko 없음"으로 굳어 영구히 영문이 된다. 호출자({@link PageTitleService})가
     * 응답을 받은 청크에 대해서만 부른다.
     */
    private static final String RECORD_SQL = """
            UPDATE wiki_page
               SET title_ko = :titleKo, title_ko_checked_at = now()
             WHERE id = :id AND wiki = :wiki
            """;

    private final NamedParameterJdbcTemplate jdbc;

    public PageTitleRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 조회 대상 문서 한 건. {@code title} 은 영문 원문 제목이며 langlinks 질의 키다. */
    public record PendingPage(long id, String title) {
    }

    /** 아직 조회하지 않은, 클러스터에 편입된 enwiki 문서. 최대 {@code limit} 건. */
    public List<PendingPage> findPending(int limit) {
        return jdbc.query(PENDING_SQL,
                new MapSqlParameterSource().addValue("wiki", WIKI).addValue("limit", limit),
                (rs, n) -> new PendingPage(rs.getLong("id"), rs.getString("title")));
    }

    /**
     * 조회 결과를 한 번에 기록한다.
     *
     * @param koByPageId 문서 id → ko 제목. <b>값이 null 이면 "조회했고 ko 없음"</b> 으로 기록된다
     *                   — 키가 없는 문서는 아예 건드리지 않는다
     * @return 실제로 갱신된 행 수
     */
    public int record(Map<Long, String> koByPageId) {
        if (koByPageId.isEmpty()) {
            return 0;
        }
        SqlParameterSource[] batch = koByPageId.entrySet().stream()
                .map(e -> (SqlParameterSource) new MapSqlParameterSource()
                        .addValue("id", e.getKey())
                        .addValue("titleKo", e.getValue())
                        .addValue("wiki", WIKI))
                .toArray(SqlParameterSource[]::new);
        int updated = 0;
        for (int rows : jdbc.batchUpdate(RECORD_SQL, batch)) {
            updated += rows;
        }
        return updated;
    }
}
