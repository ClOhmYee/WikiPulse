package io.wikipulse.backend.account;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.PageMeta;
import io.wikipulse.backend.common.QueryParams;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SavedService {
    private final JdbcTemplate db;
    public SavedService(JdbcTemplate db) { this.db = db; }
    public record SavedState(List<String> issueIds, List<String> tickers) {}
    public SavedState state(long member) {
        return new SavedState(db.queryForList("SELECT cluster_id::text FROM issue_bookmark WHERE member_id=? ORDER BY added_at DESC, cluster_id", String.class, member),
            db.queryForList("SELECT ticker FROM watchlist WHERE member_id=? ORDER BY added_at DESC, ticker", String.class, member));
    }
    @Transactional
    public void issue(long member, long cluster, boolean save) {
        if (!save) { db.update("DELETE FROM issue_bookmark WHERE member_id=? AND cluster_id=?", member, cluster); return; }
        // Lock the target against concurrent deletion until its FK row is inserted.
        if (db.queryForList("SELECT id FROM issue_cluster WHERE id=? FOR KEY SHARE", Long.class, cluster).isEmpty())
            throw ApiException.notFound("issue not found");
        db.update("INSERT INTO issue_bookmark(member_id,cluster_id) VALUES (?,?) ON CONFLICT DO NOTHING", member, cluster);
    }
    @Transactional
    public void stock(long member, String ticker, boolean save) {
        if (!save) { db.update("DELETE FROM watchlist WHERE member_id=? AND ticker=?", member, ticker); return; }
        if (db.queryForList("SELECT ticker FROM stock WHERE ticker=? FOR KEY SHARE", String.class, ticker).isEmpty())
            throw ApiException.notFound("stock not found");
        db.update("INSERT INTO watchlist(member_id,ticker) VALUES (?,?) ON CONFLICT DO NOTHING", member, ticker);
    }
    @Transactional(readOnly = true, isolation = org.springframework.transaction.annotation.Isolation.REPEATABLE_READ)
    public ApiResponse<?> list(long member, boolean issues, String query, Integer offset, Integer limit) {
        int from = QueryParams.offset(offset), size = QueryParams.limit(limit == null ? 20 : limit);
        if (query.length() > 200) throw ApiException.invalidQuery("q must be at most 200 characters");
        String q = query.trim();
        // position() implements literal substring search (%, _ are not wildcard operators).
        String joins = issues
            ? " FROM issue_bookmark b JOIN issue_cluster c ON c.id=b.cluster_id LEFT JOIN issue_report r ON r.cluster_id=c.id WHERE b.member_id=? AND position(lower(?) in lower(coalesce(c.label,'') || ' ' || coalesce(r.summary,'')))>0"
            : " FROM watchlist b JOIN stock s ON s.ticker=b.ticker WHERE b.member_id=? AND position(lower(?) in lower(s.ticker || ' ' || s.name))>0";
        long count = db.queryForObject("SELECT count(*)" + joins, Long.class, member, q);
        String columns = issues ? """
            SELECT c.id, c.label, r.summary, c.pulse_score AS "pulseScore", c.status, c.source,
              c.snapshot_ts AS "snapshotTs", b.added_at AS "addedAt",
              (SELECT count(*) FROM cluster_member cm WHERE cm.cluster_id=c.id) AS "memberCount",
              (SELECT count(*) FROM cluster_stock cs WHERE cs.cluster_id=c.id AND cs.verified) AS "stockCount"
            """ : """
            SELECT s.ticker, s.name, s.exchange, s.sector, b.added_at AS "addedAt",
              (SELECT count(*) FROM cluster_stock cs JOIN issue_cluster c ON c.id=cs.cluster_id
                WHERE cs.ticker=s.ticker AND cs.verified AND c.status<>'DISCARDED') AS "issueCount"
            """;
        List<Map<String,Object>> rows = db.queryForList(columns + joins
            + " ORDER BY b.added_at DESC, " + (issues ? "c.id" : "s.ticker") + " LIMIT ? OFFSET ?", member, q, size, from);
        // JDBC timestamps must use the same ISO UTC representation as public data endpoints.
        for (var row : rows) {
            for (String field : List.of("snapshotTs", "addedAt")) {
                if (row.get(field) instanceof java.sql.Timestamp time) row.put(field, time.toInstant().toString());
            }
        }
        return ApiResponse.of(rows, PageMeta.of(PageMeta.Pagination.of(from, size, count, rows.size())));
    }
}
