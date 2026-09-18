package io.wikipulse.backend.common;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 목록 응답의 meta. API 명세 v0.3 §1.2.
 *
 * <p>{@code meta.pagination} 과 목록별 추가 필드(snapshotTs 등)를 담는다.
 * total 은 자르기 이전 조건 일치 개수, hasMore = offset + 반환 개수 < total.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record PageMeta(Pagination pagination, String snapshotTs) {

    public record Pagination(int offset, int limit, long total, boolean hasMore) {
        public static Pagination of(int offset, int limit, long total, int returned) {
            return new Pagination(offset, limit, total, offset + returned < total);
        }
    }

    public static PageMeta of(Pagination pagination) {
        return new PageMeta(pagination, null);
    }

    public static PageMeta of(Pagination pagination, String snapshotTs) {
        return new PageMeta(pagination, snapshotTs);
    }
}
