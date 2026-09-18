package io.wikipulse.backend.common;

import java.util.List;
import java.util.Set;

/** 쿼리 파라미터 검증·파싱. API 명세 v0.3 §1.2·§1.4. 범위 밖은 INVALID_QUERY. */
public final class QueryParams {

    private QueryParams() {
    }

    public static final Set<String> ISSUE_STATUSES =
            Set.of("DETECTED", "VERIFYING", "CONFIRMED", "DISCARDED");
    public static final Set<String> SOURCES = Set.of("live", "replay");

    // 목록 기본은 DISCARDED 제외 (명세 §2).
    public static final List<String> DEFAULT_STATUSES =
            List.of("DETECTED", "VERIFYING", "CONFIRMED");

    public static int offset(Integer offset) {
        int v = offset == null ? 0 : offset;
        if (v < 0) {
            throw ApiException.invalidQuery("offset must be >= 0");
        }
        return v;
    }

    public static int limit(Integer limit) {
        int v = limit == null ? 50 : limit;
        if (v < 1 || v > 100) {
            throw ApiException.invalidQuery("limit must be 1..100");
        }
        return v;
    }

    /** 쉼표 목록 status 를 검증해 리스트로. null·빈값이면 기본 목록. */
    public static List<String> statuses(String status) {
        if (status == null || status.isBlank()) {
            return DEFAULT_STATUSES;
        }
        List<String> parsed = List.of(status.split(","));
        for (String s : parsed) {
            if (!ISSUE_STATUSES.contains(s)) {
                throw ApiException.invalidQuery("unknown status: " + s);
            }
        }
        return parsed;
    }

    public static String source(String source) {
        if (source == null) {
            return null;
        }
        if (!SOURCES.contains(source)) {
            throw ApiException.invalidQuery("source must be live or replay");
        }
        return source;
    }

    /** 부분 일치 LIKE 패턴. null·빈값이면 null(필터 안 함). */
    public static String likePattern(String q) {
        if (q == null || q.isBlank()) {
            return null;
        }
        return "%" + q.toLowerCase().trim() + "%";
    }
}
