package io.wikipulse.backend.common;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 성공 응답 봉투. API 명세 v0.2 §1.1.
 *
 * <p>{@code {data, meta}} 형태. 목록은 data 가 배열, 단건은 객체.
 * meta 가 없으면 통째로 생략한다(JsonInclude.NON_NULL).
 *
 * @param data 실제 페이로드 (배열 또는 객체)
 * @param meta endpoint 가 정의한 것만. 없으면 null → 직렬화에서 빠짐
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiResponse<T>(T data, Object meta) {

    public static <T> ApiResponse<T> of(T data) {
        return new ApiResponse<>(data, null);
    }

    public static <T> ApiResponse<T> of(T data, Object meta) {
        return new ApiResponse<>(data, meta);
    }
}
