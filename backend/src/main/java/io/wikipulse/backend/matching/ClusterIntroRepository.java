package io.wikipulse.backend.matching;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * 대표 텍스트(명세 §6.2)를 시점에 맞게 만들기 위한 DB 접근 (WP-129).
 *
 * <p>여태 후보·검증 워커는 멤버 <b>제목</b>만 읽어 현재 Wikipedia 도입부를 가져왔다. 시점
 * 계약이 생기면서 두 가지가 더 필요해졌다: 그 클러스터가 LIVE 인지 리플레이인지
 * ({@code issue_cluster.source}), 그리고 어느 시점인지({@code snapshot_ts}).
 */
@Repository
public class ClusterIntroRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public ClusterIntroRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 대표 텍스트를 만들 때 필요한 클러스터 정보. 멤버는 급등도 내림차순(명세 §6.2). */
    public record ClusterContext(String source, OffsetDateTime snapshotTs, List<Member> members) {

        /** 멤버 한 명. {@code pageId} 는 우리 {@code wiki_page.id} 다. */
        public record Member(long pageId, String title) {
        }

        /** 리플레이면 도입부를 {@code snapshotTs} 이하 revision 에서 고정해야 한다. */
        public boolean isReplay() {
            return "replay".equals(source);
        }
    }

    /**
     * 클러스터의 출처·시점과 멤버 목록. 클러스터가 없으면 {@link Optional#empty()}.
     *
     * <p>멤버 정렬은 {@code CandidateRepository.memberTitlesByPulse} 와 같다 —
     * 급등도 내림차순, NULL 은 뒤, 동률은 엣지 가중치.
     */
    public Optional<ClusterContext> context(long clusterId) {
        var params = new MapSqlParameterSource("cid", clusterId);
        List<Object[]> rows = jdbc.query("""
                SELECT c.source AS source, c.snapshot_ts AS snapshot_ts,
                       cm.page_id AS page_id, wp.title AS title
                  FROM issue_cluster c
                  JOIN cluster_member cm ON cm.cluster_id = c.id
                  JOIN wiki_page wp ON wp.id = cm.page_id
                 WHERE c.id = :cid
                 ORDER BY cm.spike_score DESC NULLS LAST, cm.weight DESC
                """, params, (rs, rowNum) -> new Object[] {
                rs.getString("source"),
                rs.getObject("snapshot_ts", OffsetDateTime.class),
                rs.getLong("page_id"),
                rs.getString("title"),
        });
        if (rows.isEmpty()) {
            return Optional.empty();
        }
        List<ClusterContext.Member> members = rows.stream()
                .map(r -> new ClusterContext.Member((Long) r[2], (String) r[3]))
                .toList();
        return Optional.of(new ClusterContext(
                (String) rows.get(0)[0], (OffsetDateTime) rows.get(0)[1], members));
    }

    /**
     * {@code asOf} 이하 마지막 revision 의 도입부 (명세 §6.2 리플레이 출처).
     *
     * <p>🔴 비었다고 현재 도입부로 대체하지 않는다. 호출자가 그 revision 을 받아 와
     * {@link #saveIntro} 로 고정한 뒤 다시 읽는다.
     */
    public Optional<String> introAsOf(long pageId, OffsetDateTime asOf) {
        var params = new MapSqlParameterSource()
                .addValue("pid", pageId)
                .addValue("as_of", asOf);
        return jdbc.query("""
                SELECT intro
                  FROM page_intro
                 WHERE page_id = :pid AND rev_ts <= :as_of
                 ORDER BY rev_ts DESC
                 LIMIT 1
                """, params, (rs, rowNum) -> rs.getString("intro"))
                .stream().findFirst();
    }

    /**
     * 받아 온 시점 도입부를 고정한다. 같은 revision 을 다시 받으면 본문만 갱신한다 —
     * 다른 스냅샷이 같은 revision 으로 귀결되는 일이 흔하다.
     */
    public void saveIntro(long pageId, WikipediaExtractClient.Revision revision, String intro) {
        var params = new MapSqlParameterSource()
                .addValue("pid", pageId)
                .addValue("rev_id", revision.revId())
                .addValue("rev_ts", revision.revTs())
                .addValue("wiki_page_id", revision.wikiPageId())
                .addValue("intro", intro);
        jdbc.update("""
                INSERT INTO page_intro (page_id, rev_id, rev_ts, wiki_page_id, intro)
                VALUES (:pid, :rev_id, :rev_ts, :wiki_page_id, :intro)
                ON CONFLICT (page_id, rev_id) DO UPDATE
                   SET intro = EXCLUDED.intro,
                       rev_ts = EXCLUDED.rev_ts,
                       wiki_page_id = EXCLUDED.wiki_page_id,
                       fetched_at = now()
                """, params);
    }
}
